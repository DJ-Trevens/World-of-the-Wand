# app.py

import eventlet
eventlet.monkey_patch() # Should be the very first non-import line

import os
import random
from flask import Flask, render_template, request, Blueprint
from flask_socketio import SocketIO, emit as emit_ctx
import time
import traceback

# --- Game Settings ---
GRID_WIDTH, GRID_HEIGHT, GAME_TICK_RATE, SHOUT_MANA_COST, MAX_VIEW_DISTANCE = 20, 15, 0.75, 5, 8
_game_loop_started_in_this_process = False
DESTROY_WALL_MANA_COST = 10
INITIAL_WALL_ITEMS = 777

# Tile Types (for server-side representation)
TILE_FLOOR = 0
TILE_WALL = 1
TILE_WATER = 2 # New tile type

# Server-side Weather State
SERVER_IS_RAINING = True # Start with rain for testing, can be made dynamic

def get_player_name(sid): return f"Wizard-{sid[:4]}"

# --- Core Game Classes ---
class Player:
    def __init__(self, sid, name):
        self.id = sid
        self.name = name
        self.scene_x = 0
        self.scene_y = 0
        self.x = GRID_WIDTH // 2
        self.y = GRID_HEIGHT // 2
        self.char = random.choice(['^', 'v', '<', '>'])

        self.max_health = 100
        self.current_health = 100
        self.max_mana = 175
        self.current_mana = 175
        self.potions = 7
        self.gold = 0
        self.walls = INITIAL_WALL_ITEMS
        
        self.is_wet = False # New attribute
        self.time_became_wet = 0 # To potentially handle drying off later

    def update_position(self, dx, dy, new_char, game_manager, socketio_instance):
        old_scene_x, old_scene_y = self.scene_x, self.scene_y
        original_x_tile, original_y_tile = self.x, self.y

        scene_changed_flag = False
        transition_key = None

        nx, ny = self.x + dx, self.y + dy

        if nx < 0:
            self.scene_x -= 1; self.x = GRID_WIDTH - 1; scene_changed_flag = True
            transition_key = 'LORE.SCENE_TRANSITION_WEST'
        elif nx >= GRID_WIDTH:
            self.scene_x += 1; self.x = 0; scene_changed_flag = True
            transition_key = 'LORE.SCENE_TRANSITION_EAST'
        else:
            self.x = nx

        if ny < 0:
            self.scene_y -= 1; self.y = GRID_HEIGHT - 1; scene_changed_flag = True
            if not transition_key: transition_key = 'LORE.SCENE_TRANSITION_NORTH'
        elif ny >= GRID_HEIGHT:
            self.scene_y += 1; self.y = 0; scene_changed_flag = True
            if not transition_key: transition_key = 'LORE.SCENE_TRANSITION_SOUTH'
        else:
            self.y = ny

        self.char = new_char

        if scene_changed_flag:
            game_manager.handle_player_scene_change(self, old_scene_x, old_scene_y)
            if transition_key:
                socketio_instance.emit('lore_message', {
                    'messageKey': transition_key,
                    'placeholders': {'scene_x': self.scene_x, 'scene_y': self.scene_y},
                    'type': 'system'
                }, room=self.id)
        
        return scene_changed_flag or (self.x != original_x_tile or self.y != original_y_tile)

    def drink_potion(self, socketio_instance):
        if self.potions > 0:
            self.potions -= 1
            self.current_health = min(self.max_health, self.current_health + 15)
            socketio_instance.emit('lore_message', {'messageKey': 'LORE.POTION_DRINK_SUCCESS', 'type': 'event-good'}, room=self.id)
            return True
        else:
            socketio_instance.emit('lore_message', {'messageKey': 'LORE.POTION_DRINK_FAIL_EMPTY', 'type': 'event-bad'}, room=self.id)
            return False

    def can_afford_mana(self, cost): return self.current_mana >= cost
    def spend_mana(self, cost):
        if self.can_afford_mana(cost): self.current_mana -= cost; return True
        return False
    def has_wall_items(self): return self.walls > 0
    def use_wall_item(self):
        if self.has_wall_items(): self.walls -= 1; return True
        return False
    def add_wall_item(self): self.walls += 1
    
    def set_wet_status(self, status, socketio_instance, reason="unknown"):
        if self.is_wet != status:
            self.is_wet = status
            if status:
                self.time_became_wet = time.time()
                if reason == "water_tile":
                    # Emit a specific event for client-side sound hook
                    socketio_instance.emit('player_event', {'type': 'stepped_in_water', 'sid': self.id}, room=self.id)
                    socketio_instance.emit('lore_message', {'messageKey': 'LORE.BECAME_WET_WATER', 'type': 'system'}, room=self.id)
                elif reason == "rain":
                     socketio_instance.emit('lore_message', {'messageKey': 'LORE.BECAME_WET_RAIN', 'type': 'system'}, room=self.id)
            else: # Became dry
                socketio_instance.emit('lore_message', {'messageKey': 'LORE.BECAME_DRY', 'type': 'system'}, room=self.id)
                # TODO: Logic for drying (e.g. after time, or by going indoors)

    def get_public_data(self):
        return {'id': self.id, 'name': self.name, 'x': self.x, 'y': self.y,
                'char': self.char, 'scene_x': self.scene_x, 'scene_y': self.scene_y,
                'is_wet': self.is_wet} # Added is_wet

    def get_full_data(self):
        return {'id': self.id, 'name': self.name, 'scene_x': self.scene_x, 'scene_y': self.scene_y,
                'x': self.x, 'y': self.y, 'char': self.char,
                'max_health': self.max_health, 'current_health': self.current_health,
                'max_mana': self.max_mana, 'current_mana': self.current_mana,
                'potions': self.potions, 'gold': self.gold, 'walls': self.walls,
                'is_wet': self.is_wet} # Added is_wet

class Scene:
    def __init__(self, scene_x, scene_y, name_generator_func=None):
        self.scene_x = scene_x
        self.scene_y = scene_y
        self.name = f"Area ({scene_x},{scene_y})"
        if name_generator_func: self.name = name_generator_func(scene_x, scene_y)
        self.players_sids = set()
        self.terrain_grid = [[TILE_FLOOR for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
        self.is_indoors = False # New property, default to outdoors

    def add_player(self, player_sid): self.players_sids.add(player_sid)
    def remove_player(self, player_sid): self.players_sids.discard(player_sid)
    def get_player_sids(self): return list(self.players_sids)

    def get_tile_type(self, x, y):
        if 0 <= y < GRID_HEIGHT and 0 <= x < GRID_WIDTH: return self.terrain_grid[y][x]
        return None

    def set_tile_type(self, x, y, tile_type):
        if 0 <= y < GRID_HEIGHT and 0 <= x < GRID_WIDTH:
            self.terrain_grid[y][x] = tile_type
            return True
        return False

    def get_terrain_for_payload(self):
        """ Returns lists of coordinates for different terrain types """
        terrain_data = {'walls': [], 'water': []}
        for r_idx, row in enumerate(self.terrain_grid):
            for c_idx, tile_type in enumerate(row):
                if tile_type == TILE_WALL:
                    terrain_data['walls'].append({'x': c_idx, 'y': r_idx})
                elif tile_type == TILE_WATER:
                    terrain_data['water'].append({'x': c_idx, 'y': r_idx})
        return terrain_data

class GameManager:
    def __init__(self, socketio_instance):
        self.players = {}
        self.scenes = {}
        self.queued_actions = {}
        self.socketio = socketio_instance
        self.server_is_raining = SERVER_IS_RAINING # Initialize server rain state

    def setup_spawn_shrine(self, scene_obj):
        # Simple shrine: a 5x5 hollow square in the middle
        mid_x, mid_y = GRID_WIDTH // 2, GRID_HEIGHT // 2
        shrine_size = 2 # half-size, so 2 means 5x5 (center +- 2)
        
        # Walls
        for i in range(-shrine_size, shrine_size + 1):
            scene_obj.set_tile_type(mid_x + i, mid_y - shrine_size, TILE_WALL) # Top row
            scene_obj.set_tile_type(mid_x + i, mid_y + shrine_size, TILE_WALL) # Bottom row
            if abs(i) < shrine_size : # Avoid doubling corners
                scene_obj.set_tile_type(mid_x - shrine_size, mid_y + i, TILE_WALL) # Left col (excl. top/bottom corners)
                scene_obj.set_tile_type(mid_x + shrine_size, mid_y + i, TILE_WALL) # Right col (excl. top/bottom corners)
        
        # Entrance to the south
        scene_obj.set_tile_type(mid_x, mid_y + shrine_size, TILE_FLOOR)

        # Some water puddles for testing, outside the shrine
        scene_obj.set_tile_type(mid_x - (shrine_size + 2), mid_y, TILE_WATER)
        scene_obj.set_tile_type(mid_x - (shrine_size + 2), mid_y + 1, TILE_WATER)
        scene_obj.set_tile_type(mid_x + (shrine_size + 2), mid_y -1, TILE_WATER)


    def get_or_create_scene(self, scene_x, scene_y):
        scene_coords = (scene_x, scene_y)
        if scene_coords not in self.scenes:
            new_scene = Scene(scene_x, scene_y)
            if scene_x == 0 and scene_y == 0: # Spawn scene
                self.setup_spawn_shrine(new_scene)
                # Example: Make spawn scene indoors to avoid rain at spawn
                # new_scene.is_indoors = True 
            self.scenes[scene_coords] = new_scene
        return self.scenes[scene_coords]

    def add_player(self, sid):
        name = get_player_name(sid)
        player = Player(sid, name)
        self.players[sid] = player
        scene = self.get_or_create_scene(player.scene_x, player.scene_y)
        scene.add_player(sid)
        new_player_public_data = player.get_public_data()
        for other_sid_in_scene in scene.get_player_sids():
            if other_sid_in_scene != sid:
                self.socketio.emit('player_entered_your_scene', new_player_public_data, room=other_sid_in_scene)
        return player

    def remove_player(self, sid):
        player = self.players.pop(sid, None)
        if sid in self.queued_actions: del self.queued_actions[sid]
        if player:
            old_scene_coords = (player.scene_x, player.scene_y)
            if old_scene_coords in self.scenes:
                scene = self.scenes[old_scene_coords]
                scene.remove_player(sid)
                for other_sid_in_scene in scene.get_player_sids():
                    self.socketio.emit('player_exited_your_scene', {'id': sid, 'name': player.name}, room=other_sid_in_scene)
            return player
        return None

    def get_player(self, sid): return self.players.get(sid)

    def handle_player_scene_change(self, player, old_scene_x, old_scene_y):
        old_scene_coords = (old_scene_x, old_scene_y)
        new_scene_coords = (player.scene_x, player.scene_y)
        if old_scene_coords != new_scene_coords:
            if old_scene_coords in self.scenes:
                old_scene_obj = self.scenes[old_scene_coords]
                old_scene_obj.remove_player(player.id)
                for other_sid in old_scene_obj.get_player_sids():
                    self.socketio.emit('player_exited_your_scene', {'id': player.id, 'name': player.name}, room=other_sid)
            new_scene_obj = self.get_or_create_scene(player.scene_x, player.scene_y)
            new_scene_obj.add_player(player.id)
            player_public_data_for_new_scene = player.get_public_data()
            for other_sid in new_scene_obj.get_player_sids():
                if other_sid != player.id:
                    self.socketio.emit('player_entered_your_scene', player_public_data_for_new_scene, room=other_sid)

    def is_player_visible_to_observer(self, observer_player, target_player):
        if not observer_player or not target_player: return False
        if observer_player.id == target_player.id: return False
        if observer_player.scene_x != target_player.scene_x or \
           observer_player.scene_y != target_player.scene_y:
            return False
        return abs(observer_player.x - target_player.x) <= MAX_VIEW_DISTANCE and \
               abs(observer_player.y - target_player.y) <= MAX_VIEW_DISTANCE


    def get_visible_players_for_observer(self, observer_player):
        visible_others = []
        observer_scene_coords = (observer_player.scene_x, observer_player.scene_y)
        if observer_scene_coords in self.scenes:
            scene = self.scenes[observer_scene_coords]
            for target_sid in scene.get_player_sids():
                if target_sid == observer_player.id:
                    continue
                target_player = self.get_player(target_sid)
                if target_player and self.is_player_visible_to_observer(observer_player, target_player):
                    visible_others.append(target_player.get_public_data())
        return visible_others

    def get_target_coordinates(self, player, dx, dy):
        return player.x + dx, player.y + dy

    def process_actions(self):
        current_actions_to_process = dict(self.queued_actions)
        self.queued_actions.clear()
        processed_sids = set()

        for sid_action, action_data in current_actions_to_process.items():
            if sid_action in processed_sids : continue
            player = self.get_player(sid_action)
            if not player: continue
            action_type = action_data.get('type')
            details = action_data.get('details', {})

            if action_type == 'move' or action_type == 'look':
                dx, dy = details.get('dx', 0), details.get('dy', 0)
                new_char_for_player = details.get('newChar', player.char)
                
                player_moved_location = False
                if action_type == 'move' and (dx != 0 or dy != 0):
                    target_x, target_y = player.x + dx, player.y + dy
                    scene_of_player = self.get_or_create_scene(player.scene_x, player.scene_y)
                    
                    can_move_to_tile = True
                    if 0 <= target_x < GRID_WIDTH and 0 <= target_y < GRID_HEIGHT:
                        tile_type_at_target = scene_of_player.get_tile_type(target_x, target_y)
                        if tile_type_at_target == TILE_WALL:
                            self.socketio.emit('lore_message', {'messageKey': 'LORE.ACTION_BLOCKED_WALL', 'type': 'event-bad'}, room=player.id)
                            can_move_to_tile = False
                        elif tile_type_at_target == TILE_WATER:
                            player.set_wet_status(True, self.socketio, reason="water_tile")
                    
                    if can_move_to_tile:
                        player_moved_location = player.update_position(dx, dy, new_char_for_player, self, self.socketio)
                    elif player.char != new_char_for_player :
                         player.char = new_char_for_player
                else: 
                    player.update_position(dx, dy, new_char_for_player, self, self.socketio)

            elif action_type == 'build_wall':
                dx, dy = details.get('dx', 0), details.get('dy', 0)
                target_x, target_y = self.get_target_coordinates(player, dx, dy)
                scene = self.get_or_create_scene(player.scene_x, player.scene_y)
                if not (0 <= target_x < GRID_WIDTH and 0 <= target_y < GRID_HEIGHT):
                    self.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_FAIL_OUT_OF_BOUNDS', 'type': 'event-bad'}, room=player.id)
                elif scene.get_tile_type(target_x, target_y) != TILE_FLOOR:
                    self.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_FAIL_OBSTRUCTED', 'type': 'event-bad'}, room=player.id)
                elif not player.has_wall_items():
                    self.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_FAIL_NO_MATERIALS', 'type': 'event-bad'}, room=player.id)
                else:
                    player.use_wall_item()
                    scene.set_tile_type(target_x, target_y, TILE_WALL)
                    self.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_SUCCESS', 'placeholders': {'walls': player.walls}, 'type': 'event-good'}, room=player.id)


            elif action_type == 'destroy_wall':
                dx, dy = details.get('dx', 0), details.get('dy', 0)
                target_x, target_y = self.get_target_coordinates(player, dx, dy)
                scene = self.get_or_create_scene(player.scene_x, player.scene_y)
                if not (0 <= target_x < GRID_WIDTH and 0 <= target_y < GRID_HEIGHT):
                    self.socketio.emit('lore_message', {'messageKey': 'LORE.DESTROY_FAIL_OUT_OF_BOUNDS', 'type': 'event-bad'}, room=player.id)
                elif scene.get_tile_type(target_x, target_y) != TILE_WALL:
                    self.socketio.emit('lore_message', {'messageKey': 'LORE.DESTROY_FAIL_NO_WALL', 'type': 'event-bad'}, room=player.id)
                elif not player.can_afford_mana(DESTROY_WALL_MANA_COST):
                    self.socketio.emit('lore_message', {'messageKey': 'LORE.DESTROY_FAIL_NO_MANA', 'placeholders': {'manaCost': DESTROY_WALL_MANA_COST}, 'type': 'event-bad'}, room=player.id)
                else:
                    player.spend_mana(DESTROY_WALL_MANA_COST)
                    player.add_wall_item() 
                    scene.set_tile_type(target_x, target_y, TILE_FLOOR)
                    self.socketio.emit('lore_message', {'messageKey': 'LORE.DESTROY_SUCCESS', 'placeholders': {'walls': player.walls, 'manaCost': DESTROY_WALL_MANA_COST}, 'type': 'event-good'}, room=player.id)

            elif action_type == 'drink_potion': player.drink_potion(self.socketio)
            elif action_type == 'say':
                message_text = details.get('message', '')
                if message_text:
                    chat_data = { 'sender_id': player.id, 'sender_name': player.name, 'message': message_text, 
                                  'type': 'say', 'scene_coords': f"({player.scene_x},{player.scene_y})" }
                    player_scene_coords = (player.scene_x, player.scene_y)
                    if player_scene_coords in self.scenes:
                        scene = self.scenes[player_scene_coords]
                        for target_sid in scene.get_player_sids():
                            self.socketio.emit('chat_message', chat_data, room=target_sid)
            elif action_type == 'shout':
                message_text = details.get('message', '')
                if message_text:
                    if player.spend_mana(SHOUT_MANA_COST):
                        chat_data = { 'sender_id': player.id, 'sender_name': player.name, 'message': message_text, 
                                      'type': 'shout', 'scene_coords': f"({player.scene_x},{player.scene_y})" }
                        for target_player_obj in list(self.players.values()):
                            if abs(target_player_obj.scene_x - player.scene_x) <= 1 and \
                               abs(target_player_obj.scene_y - player.scene_y) <= 1:
                                self.socketio.emit('chat_message', chat_data, room=target_player_obj.id)
                        self.socketio.emit('lore_message', {'messageKey': 'LORE.VOICE_BOOM_SHOUT', 
                                                            'placeholders': {'manaCost': SHOUT_MANA_COST}, 
                                                            'type': 'system'}, room=player.id)
                    else:
                        self.socketio.emit('lore_message', {'messageKey': 'LORE.LACK_MANA_SHOUT', 
                                                            'placeholders': {'manaCost': SHOUT_MANA_COST}, 
                                                            'type': 'event-bad'}, room=player.id)
            processed_sids.add(sid_action)

# --- App Setup & SocketIO ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev_security_key')
GAME_PATH_PREFIX = '/world-of-the-wand'
sio = SocketIO(logger=True, engineio_logger=True, async_mode="eventlet")
game_manager = GameManager(socketio_instance=sio)
sio.init_app(app, path=f"{GAME_PATH_PREFIX}/socket.io")
game_blueprint = Blueprint('game', __name__, template_folder='templates', static_folder='static', static_url_path='/static/game')
@game_blueprint.route('/')
def index_route(): return render_template('index.html')
app.register_blueprint(game_blueprint, url_prefix=GAME_PATH_PREFIX)
@app.route('/')
def health_check_route(): return "OK", 200

# --- Game Loop ---
def game_loop():
    my_pid = os.getpid()
    print(f">>>> [{my_pid}] game_loop THREAD ENTERED (Tick rate: {GAME_TICK_RATE}s) <<<<")
    loop_count = 0
    try:
        while True:
            loop_start_time = time.time()
            loop_count += 1
            if loop_count % 20 == 1:
                 print(f"---- [{my_pid}] Tick {loop_count} ---- Players: {len(game_manager.players)} ---- Actions: {len(game_manager.queued_actions)} ---- Rain: {game_manager.server_is_raining} ----")

            game_manager.process_actions()

            if game_manager.server_is_raining:
                for player_obj in list(game_manager.players.values()): 
                    player_scene = game_manager.get_or_create_scene(player_obj.scene_x, player_obj.scene_y)
                    if not player_scene.is_indoors: 
                        if not player_obj.is_wet: 
                             player_obj.set_wet_status(True, sio, reason="rain")
            
            for player_obj in list(game_manager.players.values()):
                player_scene = game_manager.get_or_create_scene(player_obj.scene_x, player_obj.scene_y)
                if player_scene.is_indoors and player_obj.is_wet:
                    player_obj.set_wet_status(False, sio, reason="indoors")


            if game_manager.players:
                current_players_snapshot = list(game_manager.players.values())
                num_updates_sent_successfully = 0
                for recipient_player in current_players_snapshot:
                    if recipient_player.id not in game_manager.players: continue
                    self_data_payload = recipient_player.get_full_data()
                    visible_others_payload = game_manager.get_visible_players_for_observer(recipient_player)
                    current_scene_obj = game_manager.get_or_create_scene(recipient_player.scene_x, recipient_player.scene_y)
                    visible_terrain_payload = current_scene_obj.get_terrain_for_payload() 

                    payload_for_client = {
                        'self_player_data': self_data_payload,
                        'visible_other_players': visible_others_payload,
                        'visible_terrain': visible_terrain_payload, 
                    }
                    try:
                        sio.emit('game_update', payload_for_client, room=recipient_player.id)
                        num_updates_sent_successfully +=1
                    except Exception as e_emit:
                        print(f"!!! [{my_pid}] Tick {loop_count}: ERROR during sio.emit for SID {recipient_player.id}: {e_emit}")
                        traceback.print_exc()
                if num_updates_sent_successfully > 0 and loop_count % 10 == 1:
                     print(f"[{my_pid}] Tick {loop_count}: Completed sending 'game_update' to {num_updates_sent_successfully} players.")
            
            elapsed_time = time.time() - loop_start_time
            sleep_duration = GAME_TICK_RATE - elapsed_time
            if sleep_duration > 0: sio.sleep(sleep_duration)
            elif sleep_duration < -0.05:
                print(f"!!! [{my_pid}] GAME LOOP OVERRUN: Tick {loop_count} took {elapsed_time:.4f}s (ran over by {-sleep_duration:.4f}s).")
    except Exception as e_loop:
        print(f"!!!!!!!! [{my_pid}] FATAL ERROR IN GAME_LOOP (PID: {my_pid}): {e_loop} !!!!!!!!")
        traceback.print_exc()

# --- SocketIO Event Handlers ---
@sio.on('connect')
def handle_connect_event(auth=None):
    sid, pid = request.sid, os.getpid()
    player = game_manager.add_player(sid)
    player_full_data = player.get_full_data()
    visible_to_new_player = game_manager.get_visible_players_for_observer(player)
    emit_ctx('initial_game_data', {
        'player_data': player_full_data,
        'other_players_in_scene': visible_to_new_player,
        'grid_width': GRID_WIDTH, 'grid_height': GRID_HEIGHT, 'tick_rate': GAME_TICK_RATE
    })
    print(f"[{pid}] Connect: {player.name} ({sid}). Players: {len(game_manager.players)}")

@sio.on('disconnect')
def handle_disconnect_event():
    sid, pid = request.sid, os.getpid()
    player_left = game_manager.remove_player(sid)
    if player_left: print(f"[{pid}] Disconnect: {player_left.name} ({sid}). Players: {len(game_manager.players)}")
    else: print(f"[{pid}] Disconnect for SID {sid} (player not found or already removed by GameManager).")

@sio.on('queue_player_action')
def handle_queue_player_action(data):
    sid, pid = request.sid, os.getpid()
    player = game_manager.get_player(sid)
    if not player:
        emit_ctx('action_feedback', {'success': False, 'message': "Player not recognized."})
        return
    action_type = data.get('type')
    valid_actions = ['move', 'look', 'drink_potion', 'say', 'shout', 'build_wall', 'destroy_wall']
    if action_type not in valid_actions:
        emit_ctx('action_feedback', {'success': False, 'messageKey': 'ACTION_SENT_FEEDBACK.ACTION_FAILED_UNKNOWN_COMMAND', 'placeholders': {'actionWord': action_type}})
        return
    game_manager.queued_actions[sid] = data
    emit_ctx('action_feedback', {'success': True, 'messageKey': 'ACTION_SENT_FEEDBACK.ACTION_QUEUED'})

# --- Game Loop Startup ---
def start_game_loop_for_worker():
    global _game_loop_started_in_this_process
    my_pid = os.getpid()
    if not _game_loop_started_in_this_process:
        print(f"[{my_pid}] Worker: Attempting to start game_loop task...")
        try:
            sio.start_background_task(target=game_loop)
            _game_loop_started_in_this_process = True
            sio.sleep(0.01)
            print(f"[{my_pid}] Worker: Game loop task started successfully via sio.start_background_task.")
        except Exception as e:
            print(f"!!! [{my_pid}] Worker: FAILED TO START GAME LOOP: {e} !!!"); traceback.print_exc()
    else: print(f"[{my_pid}] Worker: Game loop already marked as started in this process.")

# --- Main Execution ---
if __name__ == '__main__':
    print(f"[{os.getpid()}] Starting Flask-SocketIO server for LOCAL DEVELOPMENT...")
    start_game_loop_for_worker()
    sio.run(app, debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), use_reloader=False)
else:
    print(f"[{os.getpid()}] App module loaded by Gunicorn. Game loop is intended to start via post_fork hook.")
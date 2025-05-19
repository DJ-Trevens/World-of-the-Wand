import eventlet
eventlet.monkey_patch() # Should be the very first non-import line

import os
import random
from flask import Flask, render_template, request, Blueprint
from flask_socketio import SocketIO, emit as emit_ctx # emit_ctx can be used as 'emit' in handlers
import time
import traceback

# --- Game Settings ---
GRID_WIDTH, GRID_HEIGHT, GAME_TICK_RATE, SHOUT_MANA_COST, MAX_VIEW_DISTANCE = 20, 15, 0.75, 5, 8
_game_loop_started_in_this_process = False 

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

    def update_position(self, dx, dy, new_char, game_manager, socketio_instance):
        old_scene_x, old_scene_y = self.scene_x, self.scene_y
        original_x_tile, original_y_tile = self.x, self.y # For checking if actual tile position changed
        
        scene_changed_flag = False
        transition_key = None

        nx, ny = self.x + dx, self.y + dy # Target coordinates based on current position + delta
        
        # Handle X movement and scene transitions
        if nx < 0:
            self.scene_x -= 1
            self.x = GRID_WIDTH - 1
            scene_changed_flag = True
            transition_key = 'LORE.SCENE_TRANSITION_WEST'
        elif nx >= GRID_WIDTH:
            self.scene_x += 1
            self.x = 0
            scene_changed_flag = True
            transition_key = 'LORE.SCENE_TRANSITION_EAST'
        else:
            self.x = nx

        # Handle Y movement and scene transitions
        if ny < 0:
            self.scene_y -= 1
            self.y = GRID_HEIGHT - 1
            scene_changed_flag = True
            if not transition_key: transition_key = 'LORE.SCENE_TRANSITION_NORTH'
        elif ny >= GRID_HEIGHT:
            self.scene_y += 1
            self.y = 0
            scene_changed_flag = True
            if not transition_key: transition_key = 'LORE.SCENE_TRANSITION_SOUTH'
        else:
            self.y = ny # Assign new y if it's within current scene bounds
            
        self.char = new_char # Update character regardless of movement

        if scene_changed_flag:
            game_manager.handle_player_scene_change(self, old_scene_x, old_scene_y) # Notifies other players
            if transition_key: # Send lore message to the player who transitioned
                socketio_instance.emit('lore_message', {
                    'messageKey': transition_key,
                    'placeholders': {'scene_x': self.scene_x, 'scene_y': self.scene_y},
                    'message': f"You arrive in area ({self.scene_x},{self.scene_y}).", # Fallback
                    'type': 'system'
                }, room=self.id)
        
        # Return true if tile position or scene changed. Char change alone (look) doesn't count as "moved".
        return scene_changed_flag or (self.x != original_x_tile or self.y != original_y_tile)

    def drink_potion(self, socketio_instance):
        if self.potions > 0:
            self.potions -= 1
            self.current_health = min(self.max_health, self.current_health + 15)
            socketio_instance.emit('lore_message', {'messageKey': 'LORE.POTION_DRINK_SUCCESS', 'type': 'event-good', 'message': "Potion consumed!"}, room=self.id)
            return True
        else:
            socketio_instance.emit('lore_message', {'messageKey': 'LORE.POTION_DRINK_FAIL_EMPTY', 'type': 'event-bad', 'message': "No potions!"}, room=self.id)
            return False

    def can_afford_mana(self, cost):
        return self.current_mana >= cost

    def spend_mana(self, cost):
        if self.can_afford_mana(cost):
            self.current_mana -= cost
            return True
        return False

    def get_public_data(self):
        """Data safe to send to other clients."""
        return {'id': self.id, 'name': self.name, 'x': self.x, 'y': self.y, 
                'char': self.char, 'scene_x': self.scene_x, 'scene_y': self.scene_y}

    def get_full_data(self):
        """All data for the player themselves."""
        return {'id': self.id, 'name': self.name, 'scene_x': self.scene_x, 'scene_y': self.scene_y, 
                'x': self.x, 'y': self.y, 'char': self.char, 
                'max_health': self.max_health, 'current_health': self.current_health,
                'max_mana': self.max_mana, 'current_mana': self.current_mana, 
                'potions': self.potions, 'gold': self.gold}

class Scene:
    def __init__(self, scene_x, scene_y, name_generator_func=None):
        self.scene_x = scene_x
        self.scene_y = scene_y
        # Simple name generation for now, can be expanded
        self.name = f"Area ({scene_x},{scene_y})" 
        if name_generator_func:
            self.name = name_generator_func(scene_x, scene_y)
        self.players_sids = set() # Set of player sids

    def add_player(self, player_sid):
        self.players_sids.add(player_sid)

    def remove_player(self, player_sid):
        self.players_sids.discard(player_sid)

    def get_player_sids(self):
        return list(self.players_sids) # Return a copy

class GameManager:
    def __init__(self, socketio_instance):
        self.players = {}  # sid: Player_object
        self.scenes = {}   # (scene_x, scene_y): Scene_object
        self.queued_actions = {} # sid: action_data
        self.socketio = socketio_instance # Store socketio instance

    def get_or_create_scene(self, scene_x, scene_y):
        scene_coords = (scene_x, scene_y)
        if scene_coords not in self.scenes:
            self.scenes[scene_coords] = Scene(scene_x, scene_y)
        return self.scenes[scene_coords]

    def add_player(self, sid):
        name = get_player_name(sid)
        player = Player(sid, name)
        self.players[sid] = player
        
        scene = self.get_or_create_scene(player.scene_x, player.scene_y)
        scene.add_player(sid)
        
        # Announce to others in the new scene (already existing players)
        new_player_public_data = player.get_public_data()
        for other_sid_in_scene in scene.get_player_sids():
            if other_sid_in_scene != sid: # Don't announce to self
                self.socketio.emit('player_entered_your_scene', new_player_public_data, room=other_sid_in_scene)
        
        # print(f"[{os.getpid()}] GM: Added {name}({sid}) to scene ({player.scene_x},{player.scene_y}). Players: {len(self.players)}")
        return player

    def remove_player(self, sid):
        player = self.players.pop(sid, None)
        if sid in self.queued_actions: # Clean up any pending actions for this player
            del self.queued_actions[sid]
            
        if player:
            old_scene_coords = (player.scene_x, player.scene_y)
            if old_scene_coords in self.scenes:
                scene = self.scenes[old_scene_coords]
                scene.remove_player(sid)
                # Announce to others in the old scene
                for other_sid_in_scene in scene.get_player_sids(): # Should be empty if player was last one
                    self.socketio.emit('player_exited_your_scene', {'id': sid, 'name': player.name}, room=other_sid_in_scene)
                # Optional: Clean up empty scenes
                # if not scene.get_player_sids():
                #     del self.scenes[old_scene_coords]
                #     print(f"[{os.getpid()}] GM: Cleaned up empty scene {old_scene_coords}")
            # print(f"[{os.getpid()}] GM: Removed {player.name}({sid}). Players: {len(self.players)}")
            return player
        return None

    def get_player(self, sid):
        return self.players.get(sid)

    def handle_player_scene_change(self, player, old_scene_x, old_scene_y):
        old_scene_coords = (old_scene_x, old_scene_y)
        new_scene_coords = (player.scene_x, player.scene_y)

        if old_scene_coords != new_scene_coords:
            # Remove from old scene and notify its occupants
            if old_scene_coords in self.scenes:
                old_scene_obj = self.scenes[old_scene_coords]
                old_scene_obj.remove_player(player.id)
                for other_sid in old_scene_obj.get_player_sids(): # Players remaining in old scene
                    self.socketio.emit('player_exited_your_scene', {'id': player.id, 'name': player.name}, room=other_sid)

            # Add to new scene and notify its occupants
            new_scene_obj = self.get_or_create_scene(player.scene_x, player.scene_y)
            new_scene_obj.add_player(player.id)
            player_public_data_for_new_scene = player.get_public_data() # Ensure data is current for new scene
            for other_sid in new_scene_obj.get_player_sids(): # Players already in new scene
                if other_sid != player.id: # Don't notify self
                    self.socketio.emit('player_entered_your_scene', player_public_data_for_new_scene, room=other_sid)
            
            # print(f"[{os.getpid()}] GM: Player {player.name} moved from {old_scene_coords} to {new_scene_coords}")

    def is_player_visible_to_observer(self, observer_player, target_player):
        if not observer_player or not target_player: return False
        if observer_player.id == target_player.id: return False # Not visible to self in this context
        if observer_player.scene_x != target_player.scene_x or \
           observer_player.scene_y != target_player.scene_y:
            return False
        return abs(observer_player.x - target_player.x) <= MAX_VIEW_DISTANCE and \
               abs(observer_player.y - target_player.y) <= MAX_VIEW_DISTANCE

    def get_visible_players_for_observer(self, observer_player):
        visible_others = []
        # Only check players in the same scene as the observer
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

    def process_actions(self):
        # Make a copy because players might disconnect during processing, modifying self.players or actions
        current_actions_to_process = dict(self.queued_actions) 
        self.queued_actions.clear() # Clear original immediately
        processed_sids = set() # Keep track of sids whose actions are processed

        for sid_action, action_data in current_actions_to_process.items():
            if sid_action in processed_sids : continue # Should not happen if we clear original and copy

            player = self.get_player(sid_action)
            if not player:
                # print(f"[{os.getpid()}] GM: Action for non-existent player {sid_action}. Action: {action_data.get('type')}")
                continue
            
            action_type = action_data.get('type')
            details = action_data.get('details', {})
            # print(f"[{os.getpid()}] GM: Processing action '{action_type}' for {player.name}")

            if action_type == 'move' or action_type == 'look':
                dx, dy = details.get('dx', 0), details.get('dy', 0)
                new_char = details.get('newChar', player.char)
                # Player.update_position handles scene changes and emits lore for it
                player.update_position(dx, dy, new_char, self, self.socketio)
            
            elif action_type == 'drink_potion':
                player.drink_potion(self.socketio) # Emits lore from within
            
            elif action_type == 'say':
                message_text = details.get('message', '')
                if message_text:
                    chat_data = { 'sender_id': player.id, 'sender_name': player.name, 'message': message_text, 
                                  'type': 'say', 'scene_coords': f"({player.scene_x},{player.scene_y})" }
                    
                    player_scene_coords = (player.scene_x, player.scene_y)
                    if player_scene_coords in self.scenes:
                        scene = self.scenes[player_scene_coords]
                        for target_sid in scene.get_player_sids(): # Send to everyone in the same scene
                            self.socketio.emit('chat_message', chat_data, room=target_sid)
            
            elif action_type == 'shout':
                message_text = details.get('message', '')
                if message_text:
                    if player.spend_mana(SHOUT_MANA_COST):
                        chat_data = { 'sender_id': player.id, 'sender_name': player.name, 'message': message_text, 
                                      'type': 'shout', 'scene_coords': f"({player.scene_x},{player.scene_y})" }
                        
                        # Iterate over all players and check scene proximity
                        for target_player_obj in list(self.players.values()): # Iterate a copy
                            if abs(target_player_obj.scene_x - player.scene_x) <= 1 and \
                               abs(target_player_obj.scene_y - player.scene_y) <= 1:
                                self.socketio.emit('chat_message', chat_data, room=target_player_obj.id)
                        
                        self.socketio.emit('lore_message', {'messageKey': 'LORE.VOICE_BOOM_SHOUT', 
                                                            'placeholders': {'manaCost': SHOUT_MANA_COST}, 
                                                            'type': 'system', 
                                                            'message': f"Voice booms, cost {SHOUT_MANA_COST} mana!"}, 
                                           room=player.id)
                    else:
                        self.socketio.emit('lore_message', {'messageKey': 'LORE.LACK_MANA_SHOUT', 
                                                            'placeholders': {'manaCost': SHOUT_MANA_COST}, 
                                                            'type': 'event-bad', 
                                                            'message': "Not enough mana to shout."}, 
                                           room=player.id)
            processed_sids.add(sid_action) # Mark as processed

# --- App Setup & SocketIO ---
app = Flask(__name__)
# SECRET_KEY must be set before SocketIO if it uses session-based features, though not strictly necessary for this game's current auth.
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev_security_key')
GAME_PATH_PREFIX = '/world-of-the-wand'

# Create SocketIO instance first
sio = SocketIO(logger=True, engineio_logger=True, async_mode="eventlet")

# Instantiate GameManager and pass the SocketIO instance
game_manager = GameManager(socketio_instance=sio)

# Now initialize SocketIO with the app and path
sio.init_app(app, path=f"{GAME_PATH_PREFIX}/socket.io")

# Setup blueprint
game_blueprint = Blueprint('game', __name__, template_folder='templates', static_folder='static', static_url_path='/static/game')
@game_blueprint.route('/')
def index_route(): return render_template('index.html')
app.register_blueprint(game_blueprint, url_prefix=GAME_PATH_PREFIX)

@app.route('/') # Health check for root path
def health_check_route(): return "OK", 200

# --- Game Loop (Refactored) ---
def game_loop():
    my_pid = os.getpid()
    print(f">>>> [{my_pid}] game_loop THREAD ENTERED (Tick rate: {GAME_TICK_RATE}s) <<<<")
    loop_count = 0
    try:
        while True:
            loop_start_time = time.time()
            loop_count += 1
            
            if loop_count % 20 == 1: # Less frequent top-of-loop log
                 print(f"---- [{my_pid}] Tick {loop_count} ---- Players: {len(game_manager.players)} ---- Actions: {len(game_manager.queued_actions)} ----")

            game_manager.process_actions() # Centralized action processing

            if game_manager.players:
                # Create a snapshot of players to iterate over, in case of disconnects during emit
                current_players_snapshot = list(game_manager.players.values())
                num_updates_sent_successfully = 0

                for recipient_player in current_players_snapshot:
                    # Ensure player still exists (might have disconnected)
                    if recipient_player.id not in game_manager.players:
                        continue
                    
                    # Get data for the recipient
                    self_data_payload = recipient_player.get_full_data()
                    
                    # Get data for other visible players
                    visible_others_payload = game_manager.get_visible_players_for_observer(recipient_player)
                    
                    payload_for_client = {
                        'self_player_data': self_data_payload,
                        'visible_other_players': visible_others_payload,
                    }
                    
                    try:
                        sio.emit('game_update', payload_for_client, room=recipient_player.id) # Use sio instance
                        num_updates_sent_successfully +=1
                    except Exception as e_emit:
                        print(f"!!! [{my_pid}] Tick {loop_count}: ERROR during sio.emit for SID {recipient_player.id}: {e_emit}")
                        traceback.print_exc()
                
                if num_updates_sent_successfully > 0 and loop_count % 10 == 1 : # Less frequent success log
                     print(f"[{my_pid}] Tick {loop_count}: Completed sending 'game_update' to {num_updates_sent_successfully} players.")
            # else:
            #     if loop_count % 60 == 1 :print(f"[{my_pid}] Tick {loop_count}: No players to send updates to this tick.") # Can be noisy
            
            elapsed_time = time.time() - loop_start_time
            sleep_duration = GAME_TICK_RATE - elapsed_time
            if sleep_duration > 0:
                sio.sleep(sleep_duration) # Use sio instance for eventlet-friendly sleep
            elif sleep_duration < -0.05: # Allow for small fluctuations
                print(f"!!! [{my_pid}] GAME LOOP OVERRUN: Tick {loop_count} took {elapsed_time:.4f}s (ran over by {-sleep_duration:.4f}s).")
    except Exception as e_loop: 
        print(f"!!!!!!!! [{my_pid}] FATAL ERROR IN GAME_LOOP (PID: {my_pid}): {e_loop} !!!!!!!!")
        traceback.print_exc()

# --- SocketIO Event Handlers (Refactored) ---
@sio.on('connect') # Use sio instance for decorators
def handle_connect_event(auth=None):
    sid, pid = request.sid, os.getpid()
    player = game_manager.add_player(sid) # Handles creation, adding to scene, and notifying others
    
    # Prepare initial data for the connecting player
    player_full_data = player.get_full_data()
    visible_to_new_player = game_manager.get_visible_players_for_observer(player)

    # Send initial_game_data to the new player
    # emit_ctx (or just 'emit') is context-aware and fine here
    emit_ctx('initial_game_data', {
        'player_data': player_full_data,
        'other_players_in_scene': visible_to_new_player, 
        'grid_width': GRID_WIDTH, 
        'grid_height': GRID_HEIGHT, 
        'tick_rate': GAME_TICK_RATE
    })
    print(f"[{pid}] Connect: {player.name} ({sid}). Players: {len(game_manager.players)}")

@sio.on('disconnect') # Use sio instance
def handle_disconnect_event():
    sid, pid = request.sid, os.getpid()
    player_left = game_manager.remove_player(sid) # Handles removal from scene and notifying others
    
    if player_left:
        print(f"[{pid}] Disconnect: {player_left.name} ({sid}). Players: {len(game_manager.players)}")
    else:
        # This can happen if disconnect occurs before player was fully added or if already removed
        print(f"[{pid}] Disconnect for SID {sid} (player not found or already removed by GameManager).")

@sio.on('queue_player_action') # Use sio instance
def handle_queue_player_action(data):
    sid, pid = request.sid, os.getpid()
    player = game_manager.get_player(sid)
    if not player: 
        emit_ctx('action_feedback', {'success': False, 'message': "Player not recognized."})
        return

    action_type = data.get('type')
    # Consider making valid_actions a class member of GameManager or a constant
    valid_actions = ['move', 'look', 'drink_potion', 'say', 'shout'] 
    if action_type not in valid_actions:
        emit_ctx('action_feedback', {'success': False, 'messageKey': 'ACTION_SENT_FEEDBACK.ACTION_FAILED_UNKNOWN_COMMAND', 'placeholders': {'actionWord': action_type}, 'message': f"Unknown action: {action_type}."})
        return
    
    game_manager.queued_actions[sid] = data 
    emit_ctx('action_feedback', {'success': True, 'messageKey': 'ACTION_SENT_FEEDBACK.ACTION_QUEUED', 'message': "Your will is noted..."})
    # print(f"[{pid}] Action queued for {player.name} ({sid}): {data.get('type', 'N/A')}") # Slightly less verbose log

# --- Game Loop Startup ---
def start_game_loop_for_worker():
    global _game_loop_started_in_this_process
    my_pid = os.getpid()
    if not _game_loop_started_in_this_process:
        print(f"[{my_pid}] Worker: Attempting to start game_loop task...")
        try:
            sio.start_background_task(target=game_loop) # Use sio instance
            _game_loop_started_in_this_process = True
            sio.sleep(0.01) # Yield control briefly to allow the task to actually start
            print(f"[{my_pid}] Worker: Game loop task started successfully via sio.start_background_task.")
        except Exception as e:
            print(f"!!! [{my_pid}] Worker: FAILED TO START GAME LOOP: {e} !!!"); traceback.print_exc()
    else: print(f"[{my_pid}] Worker: Game loop already marked as started in this process.")

# --- Main Execution ---
if __name__ == '__main__':
    print(f"[{os.getpid()}] Starting Flask-SocketIO server for LOCAL DEVELOPMENT...")
    start_game_loop_for_worker() 
    sio.run(app, debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), use_reloader=False) # Use sio instance
else: # Gunicorn
    # When Gunicorn imports this module, GameManager is instantiated with `sio`.
    # The `post_fork` hook in `gunicorn_config.py` will call `start_game_loop_for_worker`.
    print(f"[{os.getpid()}] App module loaded by Gunicorn. Game loop is intended to start via post_fork hook.")
# app.py

import eventlet
eventlet.monkey_patch() # Should be the very first non-import line

import os
import random
from flask import Flask, render_template, request, Blueprint
from flask_socketio import SocketIO, emit as emit_ctx
import time
import traceback
import uuid # For NPC IDs

# --- Game Settings ---
GRID_WIDTH, GRID_HEIGHT, GAME_TICK_RATE, SHOUT_MANA_COST, MAX_VIEW_DISTANCE = 20, 15, 0.75, 5, 8
_game_loop_started_in_this_process = False
DESTROY_WALL_MANA_COST = 10
INITIAL_WALL_ITEMS = 777

# Tile Types (for server-side representation)
TILE_FLOOR = 0
TILE_WALL = 1
TILE_WATER = 2

# Server-side Weather State
SERVER_IS_RAINING = True 

# NPC Settings
PIXIE_CHAR = '*' # Or any other character you prefer
PIXIE_MANA_REGEN_BOOST = 1 # Extra mana per tick per nearby pixie
PIXIE_PROXIMITY_FOR_BOOST = 3 # Manhattan distance for pixie to boost mana
BASE_MANA_REGEN_PER_TICK = 0.5 # Base mana regen (can be float, applied over time)
TICKS_PER_MANA_REGEN_CYCLE = 3 # Regen mana every N game ticks

def get_player_name(sid): return f"Wizard-{sid[:4]}"

# --- Core Game Classes ---

class ManaPixie:
    def __init__(self, scene_x, scene_y, initial_x=None, initial_y=None):
        self.id = str(uuid.uuid4())
        self.char = PIXIE_CHAR
        self.scene_x = scene_x
        self.scene_y = scene_y
        
        if initial_x is None:
            self.x = random.randint(0, GRID_WIDTH - 1)
        else:
            self.x = initial_x
        
        if initial_y is None:
            self.y = random.randint(0, GRID_HEIGHT - 1)
        else:
            self.y = initial_y
        
        self.name = f"Pixie-{self.id[:4]}" # Simple name

    def get_public_data(self):
        return {
            'id': self.id,
            'name': self.name,
            'char': self.char,
            'x': self.x,
            'y': self.y,
            'scene_x': self.scene_x,
            'scene_y': self.scene_y
        }

    def wander(self, scene): # scene is a Scene object
        if random.random() < 0.3: # 30% chance to attempt a move
            dx = random.choice([-1, 0, 1])
            dy = random.choice([-1, 0, 1])
            if dx == 0 and dy == 0:
                return

            new_x, new_y = self.x + dx, self.y + dy

            if 0 <= new_x < GRID_WIDTH and 0 <= new_y < GRID_HEIGHT:
                tile_type = scene.get_tile_type(new_x, new_y)
                # Pixies can fly over water, but not walls. They also avoid other NPCs for wandering.
                if tile_type != TILE_WALL and not scene.is_npc_at(new_x, new_y, exclude_id=self.id):
                    self.x = new_x
                    self.y = new_y
    
    def attempt_evade(self, player_x, player_y, scene):
        """Try to move to an adjacent empty tile, away from player if possible."""
        # Simplified evasion: try random adjacent non-wall/non-npc spots
        possible_moves = []
        for dx_evade in [-1, 0, 1]:
            for dy_evade in [-1, 0, 1]:
                if dx_evade == 0 and dy_evade == 0:
                    continue
                
                evade_x, evade_y = self.x + dx_evade, self.y + dy_evade
                if 0 <= evade_x < GRID_WIDTH and 0 <= evade_y < GRID_HEIGHT:
                    tile_type = scene.get_tile_type(evade_x, evade_y)
                    if tile_type != TILE_WALL and not scene.is_npc_at(evade_x, evade_y, exclude_id=self.id) and not scene.is_player_at(evade_x, evade_y): # Pixies avoid players too when evading
                        possible_moves.append((evade_x, evade_y))
        
        if possible_moves:
            # Optional: prioritize moves further from player_x, player_y
            # For now, just pick a random valid one
            self.x, self.y = random.choice(possible_moves)
            return True
        return False


class Player:
    def __init__(self, sid, name):
        self.id = sid
        self.name = name
        self.scene_x = 0
        self.scene_y = 0
        self.x = GRID_WIDTH // 2
        self.y = GRID_HEIGHT // 2
        self.char = random.choice(['^', 'v', '<', '>'])

        self.max_health = 100 # Fixed
        self.current_health = 100
        self.max_mana = 175 # Can be increased by leveling up later
        self.current_mana = 175.0 # Use float for fractional regen
        self.potions = 7
        self.gold = 0
        self.walls = INITIAL_WALL_ITEMS
        
        self.is_wet = False 
        self.time_became_wet = 0 
        self.mana_regen_accumulator = 0.0 # For fractional mana regen

    def update_position(self, dx, dy, new_char, game_manager, socketio_instance):
        # ... (same as before)
        old_scene_x, old_scene_y = self.scene_x, self.scene_y
        original_x_tile, original_y_tile = self.x, self.y
        scene_changed_flag = False
        transition_key = None
        nx, ny = self.x + dx, self.y + dy
        if nx < 0: self.scene_x -= 1; self.x = GRID_WIDTH - 1; scene_changed_flag = True; transition_key = 'LORE.SCENE_TRANSITION_WEST'
        elif nx >= GRID_WIDTH: self.scene_x += 1; self.x = 0; scene_changed_flag = True; transition_key = 'LORE.SCENE_TRANSITION_EAST'
        else: self.x = nx
        if ny < 0: self.scene_y -= 1; self.y = GRID_HEIGHT - 1; scene_changed_flag = True;
            if not transition_key: transition_key = 'LORE.SCENE_TRANSITION_NORTH'
        elif ny >= GRID_HEIGHT: self.scene_y += 1; self.y = 0; scene_changed_flag = True;
            if not transition_key: transition_key = 'LORE.SCENE_TRANSITION_SOUTH'
        else: self.y = ny
        self.char = new_char
        if scene_changed_flag:
            game_manager.handle_player_scene_change(self, old_scene_x, old_scene_y)
            if transition_key: socketio_instance.emit('lore_message', {'messageKey': transition_key, 'placeholders': {'scene_x': self.scene_x, 'scene_y': self.scene_y}, 'type': 'system'}, room=self.id)
        return scene_changed_flag or (self.x != original_x_tile or self.y != original_y_tile)

    def drink_potion(self, socketio_instance):
        # ... (same as before)
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
        # ... (same as before)
        if self.is_wet != status:
            self.is_wet = status
            if status:
                self.time_became_wet = time.time()
                if reason == "water_tile":
                    socketio_instance.emit('player_event', {'type': 'stepped_in_water', 'sid': self.id}, room=self.id)
                    socketio_instance.emit('lore_message', {'messageKey': 'LORE.BECAME_WET_WATER', 'type': 'system'}, room=self.id)
                elif reason == "rain":
                     socketio_instance.emit('lore_message', {'messageKey': 'LORE.BECAME_WET_RAIN', 'type': 'system'}, room=self.id)
            else: 
                socketio_instance.emit('lore_message', {'messageKey': 'LORE.BECAME_DRY', 'type': 'system'}, room=self.id)

    def regenerate_mana(self, base_regen_amount, pixie_boost_total, socketio_instance):
        total_regen_this_cycle = base_regen_amount + pixie_boost_total
        self.mana_regen_accumulator += total_regen_this_cycle
        
        if self.mana_regen_accumulator >= 1.0:
            mana_to_add = int(self.mana_regen_accumulator)
            self.current_mana = min(self.max_mana, self.current_mana + mana_to_add)
            self.mana_regen_accumulator -= mana_to_add # Keep the fractional part
            
            if pixie_boost_total > 0 and mana_to_add > 0: # Only message if pixies actually contributed to this regen instance
                 socketio_instance.emit('lore_message', {'messageKey': 'LORE.PIXIE_MANA_BOOST', 'type': 'event-good', 'placeholders': {'amount': mana_to_add}}, room=self.id)


    def get_public_data(self):
        return {'id': self.id, 'name': self.name, 'x': self.x, 'y': self.y,
                'char': self.char, 'scene_x': self.scene_x, 'scene_y': self.scene_y,
                'is_wet': self.is_wet}

    def get_full_data(self):
        return {'id': self.id, 'name': self.name, 'scene_x': self.scene_x, 'scene_y': self.scene_y,
                'x': self.x, 'y': self.y, 'char': self.char,
                'max_health': self.max_health, 'current_health': self.current_health,
                'max_mana': self.max_mana, 'current_mana': int(self.current_mana), # Send int to client
                'potions': self.potions, 'gold': self.gold, 'walls': self.walls,
                'is_wet': self.is_wet}

class Scene:
    def __init__(self, scene_x, scene_y, name_generator_func=None):
        self.scene_x = scene_x
        self.scene_y = scene_y
        self.name = f"Area ({scene_x},{scene_y})"
        if name_generator_func: self.name = name_generator_func(scene_x, scene_y)
        self.players_sids = set()
        self.npc_ids = set() # Store IDs of NPCs in this scene
        self.terrain_grid = [[TILE_FLOOR for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
        self.is_indoors = False

    def add_player(self, player_sid): self.players_sids.add(player_sid)
    def remove_player(self, player_sid): self.players_sids.discard(player_sid)
    def get_player_sids(self): return list(self.players_sids)

    def add_npc(self, npc_id): self.npc_ids.add(npc_id)
    def remove_npc(self, npc_id): self.npc_ids.discard(npc_id)
    def get_npc_ids(self): return list(self.npc_ids)

    def get_tile_type(self, x, y):
        if 0 <= y < GRID_HEIGHT and 0 <= x < GRID_WIDTH: return self.terrain_grid[y][x]
        return None

    def set_tile_type(self, x, y, tile_type):
        if 0 <= y < GRID_HEIGHT and 0 <= x < GRID_WIDTH:
            self.terrain_grid[y][x] = tile_type; return True
        return False

    def get_terrain_for_payload(self):
        terrain_data = {'walls': [], 'water': []}
        for r_idx, row in enumerate(self.terrain_grid):
            for c_idx, tile_type in enumerate(row):
                if tile_type == TILE_WALL: terrain_data['walls'].append({'x': c_idx, 'y': r_idx})
                elif tile_type == TILE_WATER: terrain_data['water'].append({'x': c_idx, 'y': r_idx})
        return terrain_data
    
    def is_npc_at(self, x, y, exclude_id=None):
        """Checks if an NPC (optionally excluding one) is at the given coordinates."""
        # This requires access to the global NPC list from GameManager, or pass it in.
        # For simplicity, GameManager will call this with npc_list.
        # This method isn't strictly needed on Scene if GameManager handles NPC lookups.
        pass # Will be handled by GameManager

    def is_player_at(self, x, y):
        # This also requires access to player objects via GameManager
        pass # Will be handled by GameManager


class GameManager:
    def __init__(self, socketio_instance):
        self.players = {}
        self.scenes = {}
        self.npcs = {} # npc_id: NPC_Object (global list)
        self.queued_actions = {}
        self.socketio = socketio_instance
        self.server_is_raining = SERVER_IS_RAINING
        self.ticks_until_mana_regen = TICKS_PER_MANA_REGEN_CYCLE

    def spawn_initial_npcs(self):
        # Spawn a few pixies in scene (0,0)
        scene_0_0 = self.get_or_create_scene(0,0)
        for i in range(3): # Spawn 3 pixies
            # Try to spawn them not on walls of the shrine
            px, py = random.randint(0, GRID_WIDTH-1), random.randint(0, GRID_HEIGHT-1)
            while scene_0_0.get_tile_type(px,py) == TILE_WALL or self.get_npc_at(px,py,0,0) is not None:
                 px, py = random.randint(0, GRID_WIDTH-1), random.randint(0, GRID_HEIGHT-1)

            pixie = ManaPixie(0, 0, initial_x=px, initial_y=py)
            self.npcs[pixie.id] = pixie
            scene_0_0.add_npc(pixie.id)
            print(f"Spawned pixie {pixie.name} at ({pixie.scene_x},{pixie.scene_y}) tile ({pixie.x},{pixie.y})")


    def setup_spawn_shrine(self, scene_obj):
        # ... (same as before)
        mid_x, mid_y = GRID_WIDTH // 2, GRID_HEIGHT // 2
        shrine_size = 2 
        for i in range(-shrine_size, shrine_size + 1):
            scene_obj.set_tile_type(mid_x + i, mid_y - shrine_size, TILE_WALL) 
            scene_obj.set_tile_type(mid_x + i, mid_y + shrine_size, TILE_WALL) 
            if abs(i) < shrine_size : 
                scene_obj.set_tile_type(mid_x - shrine_size, mid_y + i, TILE_WALL) 
                scene_obj.set_tile_type(mid_x + shrine_size, mid_y + i, TILE_WALL) 
        scene_obj.set_tile_type(mid_x, mid_y + shrine_size, TILE_FLOOR)
        scene_obj.set_tile_type(mid_x - (shrine_size + 2), mid_y, TILE_WATER)
        scene_obj.set_tile_type(mid_x - (shrine_size + 2), mid_y + 1, TILE_WATER)
        scene_obj.set_tile_type(mid_x + (shrine_size + 2), mid_y -1, TILE_WATER)


    def get_or_create_scene(self, scene_x, scene_y):
        scene_coords = (scene_x, scene_y)
        if scene_coords not in self.scenes:
            new_scene = Scene(scene_x, scene_y)
            if scene_x == 0 and scene_y == 0: 
                self.setup_spawn_shrine(new_scene)
            self.scenes[scene_coords] = new_scene
        return self.scenes[scene_coords]

    def add_player(self, sid):
        # ... (same as before)
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
        # ... (same as before)
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
    def get_npc(self, npc_id): return self.npcs.get(npc_id)

    def get_npc_at(self, x, y, scene_x, scene_y):
        for npc in self.npcs.values():
            if npc.scene_x == scene_x and npc.scene_y == scene_y and npc.x == x and npc.y == y:
                return npc
        return None
        
    def get_player_at(self, x, y, scene_x, scene_y):
        for player in self.players.values():
            if player.scene_x == scene_x and player.scene_y == scene_y and player.x == x and player.y == y:
                return player
        return None

    def handle_player_scene_change(self, player, old_scene_x, old_scene_y):
        # ... (same as before)
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


    def handle_npc_scene_change(self, npc, old_scene_x, old_scene_y): # If NPCs could change scenes
        # Similar to player scene change, remove from old scene.npc_ids, add to new.
        pass


    def is_player_visible_to_observer(self, observer_player, target_player):
        # ... (same as before)
        if not observer_player or not target_player: return False
        if observer_player.id == target_player.id: return False
        if observer_player.scene_x != target_player.scene_x or \
           observer_player.scene_y != target_player.scene_y:
            return False
        return abs(observer_player.x - target_player.x) <= MAX_VIEW_DISTANCE and \
               abs(observer_player.y - target_player.y) <= MAX_VIEW_DISTANCE


    def get_visible_players_for_observer(self, observer_player):
        # ... (same as before)
        visible_others = []
        observer_scene_coords = (observer_player.scene_x, observer_player.scene_y)
        if observer_scene_coords in self.scenes:
            scene = self.scenes[observer_scene_coords]
            for target_sid in scene.get_player_sids():
                if target_sid == observer_player.id: continue
                target_player = self.get_player(target_sid)
                if target_player and self.is_player_visible_to_observer(observer_player, target_player):
                    visible_others.append(target_player.get_public_data())
        return visible_others

    def get_visible_npcs_for_observer(self, observer_player):
        visible_npcs_data = []
        # Only check NPCs in the same scene as the observer
        observer_scene_coords = (observer_player.scene_x, observer_player.scene_y)
        if observer_scene_coords in self.scenes:
            scene = self.scenes[observer_scene_coords]
            for npc_id in scene.get_npc_ids(): # Iterate NPCs in that scene
                npc = self.get_npc(npc_id)
                if npc:
                    # Use similar visibility logic as for players
                    if abs(observer_player.x - npc.x) <= MAX_VIEW_DISTANCE and \
                       abs(observer_player.y - npc.y) <= MAX_VIEW_DISTANCE:
                       visible_npcs_data.append(npc.get_public_data())
        return visible_npcs_data


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
                
                if action_type == 'move' and (dx != 0 or dy != 0):
                    target_x, target_y = player.x + dx, player.y + dy
                    scene_of_player = self.get_or_create_scene(player.scene_x, player.scene_y)
                    
                    can_move_to_tile = True
                    if 0 <= target_x < GRID_WIDTH and 0 <= target_y < GRID_HEIGHT: # Check within current scene bounds
                        tile_type_at_target = scene_of_player.get_tile_type(target_x, target_y)
                        npc_at_target = self.get_npc_at(target_x, target_y, player.scene_x, player.scene_y)

                        if tile_type_at_target == TILE_WALL:
                            self.socketio.emit('lore_message', {'messageKey': 'LORE.ACTION_BLOCKED_WALL', 'type': 'event-bad'}, room=player.id)
                            can_move_to_tile = False
                        elif npc_at_target and isinstance(npc_at_target, ManaPixie):
                            if npc_at_target.attempt_evade(player.x, player.y, scene_of_player):
                                self.socketio.emit('lore_message', {'messageKey': 'LORE.PIXIE_MOVED_AWAY', 'type': 'system', 'placeholders':{'pixieName': npc_at_target.name}}, room=player.id)
                                # Player can move, pixie moved
                            else:
                                self.socketio.emit('lore_message', {'messageKey': 'LORE.PIXIE_BLOCKED_PATH', 'type': 'event-bad', 'placeholders':{'pixieName': npc_at_target.name}}, room=player.id)
                                can_move_to_tile = False # Pixie couldn't evade
                        elif tile_type_at_target == TILE_WATER:
                            player.set_wet_status(True, self.socketio, reason="water_tile")
                    
                    if can_move_to_tile:
                        player.update_position(dx, dy, new_char_for_player, self, self.socketio)
                    elif player.char != new_char_for_player : 
                         player.char = new_char_for_player
                else: 
                    player.update_position(dx, dy, new_char_for_player, self, self.socketio)

            elif action_type == 'build_wall':
                # ... (same as before)
                dx, dy = details.get('dx', 0), details.get('dy', 0)
                target_x, target_y = self.get_target_coordinates(player, dx, dy)
                scene = self.get_or_create_scene(player.scene_x, player.scene_y)
                if not (0 <= target_x < GRID_WIDTH and 0 <= target_y < GRID_HEIGHT): self.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_FAIL_OUT_OF_BOUNDS', 'type': 'event-bad'}, room=player.id)
                elif scene.get_tile_type(target_x, target_y) != TILE_FLOOR: self.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_FAIL_OBSTRUCTED', 'type': 'event-bad'}, room=player.id)
                elif self.get_npc_at(target_x, target_y, player.scene_x, player.scene_y) or self.get_player_at(target_x, target_y, player.scene_x, player.scene_y): self.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_FAIL_OBSTRUCTED', 'type': 'event-bad'}, room=player.id) # Cannot build on NPCs/Players
                elif not player.has_wall_items(): self.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_FAIL_NO_MATERIALS', 'type': 'event-bad'}, room=player.id)
                else:
                    player.use_wall_item()
                    scene.set_tile_type(target_x, target_y, TILE_WALL)
                    self.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_SUCCESS', 'placeholders': {'walls': player.walls}, 'type': 'event-good'}, room=player.id)

            elif action_type == 'destroy_wall':
                # ... (same as before)
                dx, dy = details.get('dx', 0), details.get('dy', 0)
                target_x, target_y = self.get_target_coordinates(player, dx, dy)
                scene = self.get_or_create_scene(player.scene_x, player.scene_y)
                if not (0 <= target_x < GRID_WIDTH and 0 <= target_y < GRID_HEIGHT): self.socketio.emit('lore_message', {'messageKey': 'LORE.DESTROY_FAIL_OUT_OF_BOUNDS', 'type': 'event-bad'}, room=player.id)
                elif scene.get_tile_type(target_x, target_y) != TILE_WALL: self.socketio.emit('lore_message', {'messageKey': 'LORE.DESTROY_FAIL_NO_WALL', 'type': 'event-bad'}, room=player.id)
                elif not player.can_afford_mana(DESTROY_WALL_MANA_COST): self.socketio.emit('lore_message', {'messageKey': 'LORE.DESTROY_FAIL_NO_MANA', 'placeholders': {'manaCost': DESTROY_WALL_MANA_COST}, 'type': 'event-bad'}, room=player.id)
                else:
                    player.spend_mana(DESTROY_WALL_MANA_COST); player.add_wall_item() 
                    scene.set_tile_type(target_x, target_y, TILE_FLOOR)
                    self.socketio.emit('lore_message', {'messageKey': 'LORE.DESTROY_SUCCESS', 'placeholders': {'walls': player.walls, 'manaCost': DESTROY_WALL_MANA_COST}, 'type': 'event-good'}, room=player.id)

            elif action_type == 'drink_potion': player.drink_potion(self.socketio)
            elif action_type == 'say':
                # ... (same as before)
                message_text = details.get('message', '')
                if message_text:
                    chat_data = { 'sender_id': player.id, 'sender_name': player.name, 'message': message_text, 'type': 'say', 'scene_coords': f"({player.scene_x},{player.scene_y})" }
                    player_scene_coords = (player.scene_x, player.scene_y)
                    if player_scene_coords in self.scenes:
                        scene = self.scenes[player_scene_coords]
                        for target_sid in scene.get_player_sids(): self.socketio.emit('chat_message', chat_data, room=target_sid)
            elif action_type == 'shout':
                # ... (same as before)
                message_text = details.get('message', '')
                if message_text:
                    if player.spend_mana(SHOUT_MANA_COST):
                        chat_data = { 'sender_id': player.id, 'sender_name': player.name, 'message': message_text, 'type': 'shout', 'scene_coords': f"({player.scene_x},{player.scene_y})" }
                        for target_player_obj in list(self.players.values()):
                            if abs(target_player_obj.scene_x - player.scene_x) <= 1 and abs(target_player_obj.scene_y - player.scene_y) <= 1:
                                self.socketio.emit('chat_message', chat_data, room=target_player_obj.id)
                        self.socketio.emit('lore_message', {'messageKey': 'LORE.VOICE_BOOM_SHOUT', 'placeholders': {'manaCost': SHOUT_MANA_COST}, 'type': 'system'}, room=player.id)
                    else: self.socketio.emit('lore_message', {'messageKey': 'LORE.LACK_MANA_SHOUT', 'placeholders': {'manaCost': SHOUT_MANA_COST}, 'type': 'event-bad'}, room=player.id)
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
    game_manager.spawn_initial_npcs() # Spawn NPCs once when loop starts
    loop_count = 0
    try:
        while True:
            loop_start_time = time.time()
            loop_count += 1
            game_manager.ticks_until_mana_regen -=1

            if loop_count % 20 == 1:
                 print(f"---- [{my_pid}] Tick {loop_count} ---- Players: {len(game_manager.players)} NPCs: {len(game_manager.npcs)} Actions: {len(game_manager.queued_actions)} Rain: {game_manager.server_is_raining} ----")

            # NPC actions (wandering)
            for npc in list(game_manager.npcs.values()): # Iterate copy
                if isinstance(npc, ManaPixie):
                    scene_of_npc = game_manager.get_or_create_scene(npc.scene_x, npc.scene_y)
                    npc.wander(scene_of_npc)
            
            game_manager.process_actions()

            # Mana Regeneration Cycle
            if game_manager.ticks_until_mana_regen <= 0:
                for player_obj in list(game_manager.players.values()):
                    pixie_boost_for_player = 0
                    player_scene_obj = game_manager.get_or_create_scene(player_obj.scene_x, player_obj.scene_y)
                    for npc_id in player_scene_obj.get_npc_ids():
                        npc = game_manager.get_npc(npc_id)
                        if npc and isinstance(npc, ManaPixie):
                            dist = abs(player_obj.x - npc.x) + abs(player_obj.y - npc.y)
                            if dist <= PIXIE_PROXIMITY_FOR_BOOST:
                                pixie_boost_for_player += PIXIE_MANA_REGEN_BOOST
                    
                    player_obj.regenerate_mana(BASE_MANA_REGEN_PER_TICK, pixie_boost_for_player, sio)
                game_manager.ticks_until_mana_regen = TICKS_PER_MANA_REGEN_CYCLE


            if game_manager.server_is_raining:
                for player_obj in list(game_manager.players.values()): 
                    player_scene = game_manager.get_or_create_scene(player_obj.scene_x, player_obj.scene_y)
                    if not player_scene.is_indoors: 
                        if not player_obj.is_wet: 
                             player_obj.set_wet_status(True, sio, reason="rain")
            
            for player_obj in list(game_manager.players.values()):
                player_scene = game_manager.get_or_create_scene(player_obj.scene_x, player_obj.scene_y)
                if player_scene.is_indoors and player_obj.is_wet: # Example drying logic
                    player_obj.set_wet_status(False, sio, reason="indoors")


            if game_manager.players:
                current_players_snapshot = list(game_manager.players.values())
                num_updates_sent_successfully = 0
                for recipient_player in current_players_snapshot:
                    if recipient_player.id not in game_manager.players: continue
                    self_data_payload = recipient_player.get_full_data()
                    visible_others_payload = game_manager.get_visible_players_for_observer(recipient_player)
                    visible_npcs_payload = game_manager.get_visible_npcs_for_observer(recipient_player)
                    current_scene_obj = game_manager.get_or_create_scene(recipient_player.scene_x, recipient_player.scene_y)
                    visible_terrain_payload = current_scene_obj.get_terrain_for_payload() 

                    payload_for_client = {
                        'self_player_data': self_data_payload,
                        'visible_other_players': visible_others_payload,
                        'visible_npcs': visible_npcs_payload, # Added NPCs
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
    visible_npcs_to_new_player = game_manager.get_visible_npcs_for_observer(player) # Send NPCs on connect too
    emit_ctx('initial_game_data', {
        'player_data': player_full_data,
        'other_players_in_scene': visible_to_new_player,
        'visible_npcs': visible_npcs_to_new_player, # Added
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
# app.py

import eventlet
eventlet.monkey_patch() # Essential for cooperative multitasking

import os
import random
from flask import Flask, render_template, request, Blueprint, current_app
from flask_socketio import SocketIO, emit as emit_ctx
import time
import traceback
import uuid
import logging # For a more robust logging setup
import math # For FOV calculations

# --- Game Settings (Consider moving to a config file/env vars later) ---
GRID_WIDTH, GRID_HEIGHT, GAME_HEARTBEAT_RATE, SHOUT_MANA_COST, MAX_VIEW_DISTANCE = 20, 15, 0.75, 5, 8
_game_loop_started_in_this_process = False # Global flag to ensure loop starts once per process
DESTROY_WALL_MANA_COST = 10
INITIAL_WALL_ITEMS = 77
INITIAL_POTIONS = 77

TILE_FLOOR = 0
TILE_WALL = 1
TILE_WATER = 2

SERVER_IS_RAINING = True
DEFAULT_RAIN_INTENSITY = 0.25

PIXIE_CHAR = '*'
PIXIE_MANA_REGEN_BOOST = 1
PIXIE_PROXIMITY_FOR_BOOST = 3
BASE_MANA_REGEN_PER_HEARTBEAT_CYCLE = 0.5
HEARTBEATS_PER_MANA_REGEN_CYCLE = 3

SENSE_SIGHT_RANGE = MAX_VIEW_DISTANCE # This will be the default FOV radius
SENSE_SOUND_RANGE_MAX = 8
SENSE_SMELL_RANGE_MAX = 6
SENSE_MAGIC_RANGE_MAX = 5

# --- App Setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'a_deep_and_binding_secret_for_dev')
GAME_PATH_PREFIX = '/world-of-the-wand' # Or from env var

# --- Logging Configuration ---
if not app.debug or "gunicorn" in os.environ.get("SERVER_SOFTWARE", "").lower():
    log_level = logging.INFO
else:
    log_level = logging.DEBUG
if not app.logger.handlers:
    stream_handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(module)s:%(lineno)d PID:%(process)d] %(message)s')
    stream_handler.setFormatter(formatter)
    app.logger.addHandler(stream_handler)
app.logger.setLevel(log_level)
app.logger.info(f"Logger configured at level: {logging.getLevelName(log_level)}")


# --- SocketIO Setup ---
sio = SocketIO(logger=False, engineio_logger=False, async_mode="eventlet")


def get_player_name(sid): return f"Wizard-{sid[:4]}"

class ManaPixie:
    def __init__(self, scene_x, scene_y, initial_x=None, initial_y=None):
        self.id = str(uuid.uuid4())
        self.char = PIXIE_CHAR
        self.scene_x = scene_x
        self.scene_y = scene_y
        self.x = initial_x if initial_x is not None else random.randint(0, GRID_WIDTH - 1)
        self.y = initial_y if initial_y is not None else random.randint(0, GRID_HEIGHT - 1)
        self.name = f"Pixie-{self.id[:4]}"
        self.sensory_cues = {
            'sight': [('SENSORY.PIXIE_SIGHT_SHIMMER', 0.8, SENSE_SIGHT_RANGE), ('SENSORY.PIXIE_SIGHT_DART', 0.6, SENSE_SIGHT_RANGE)],
            'sound': [('SENSORY.PIXIE_SOUND_CHIME', 0.7, 5), ('SENSORY.PIXIE_SOUND_WINGS', 0.4, 3)],
            'smell': [('SENSORY.PIXIE_SMELL_OZONE', 0.3, 2)],
            'magic': [('SENSORY.PIXIE_MAGIC_AURA', 0.9, 4)]
        }
        self.is_hidden = False

    def get_public_data(self):
        return {'id': self.id, 'name': self.name, 'char': self.char, 'x': self.x, 'y': self.y,
                'scene_x': self.scene_x, 'scene_y': self.scene_y}

    def wander(self, scene):
        if random.random() < 0.3:
            dx, dy = random.choice([-1, 0, 1]), random.choice([-1, 0, 1])
            if dx == 0 and dy == 0: return
            new_x, new_y = self.x + dx, self.y + dy
            if scene.is_walkable(new_x, new_y) and not scene.is_npc_at(new_x, new_y, exclude_id=self.id):
                self.x, self.y = new_x, new_y

    def attempt_evade(self, player_x, player_y, scene):
        possible_moves = []
        for dx_evade in [-1, 0, 1]:
            for dy_evade in [-1, 0, 1]:
                if dx_evade == 0 and dy_evade == 0: continue
                evade_x, evade_y = self.x + dx_evade, self.y + dy_evade
                if scene.is_walkable(evade_x, evade_y) and \
                   not scene.is_npc_at(evade_x, evade_y, exclude_id=self.id) and \
                   not scene.is_player_at(evade_x, evade_y):
                    possible_moves.append((evade_x, evade_y))
        if possible_moves:
            self.x, self.y = random.choice(possible_moves); return True
        return False

class Player:
    def __init__(self, sid, name):
        self.id = sid; self.name = name; self.scene_x = 0; self.scene_y = 0
        self.x = GRID_WIDTH // 2; self.y = GRID_HEIGHT // 2
        self.char = random.choice(['^', 'v', '<', '>'])
        self.max_health = 100; self.current_health = 100
        self.max_mana = 175; self.current_mana = 175.0
        self.potions = INITIAL_POTIONS; self.gold = 0; self.walls = INITIAL_WALL_ITEMS
        self.is_wet = False; self.time_became_wet = 0
        self.mana_regen_accumulator = 0.0
        self.visible_tiles_cache = set() # Cache for FOV results

    def update_position(self, dx, dy, new_char, game_manager, socketio_instance):
        old_scene_x, old_scene_y = self.scene_x, self.scene_y
        original_x_tile, original_y_tile = self.x, self.y
        scene_changed_flag = False; transition_key = None
        nx, ny = self.x + dx, self.y + dy

        if nx < 0:
            self.scene_x -= 1; self.x = GRID_WIDTH - 1; scene_changed_flag = True
            transition_key = 'LORE.SCENE_TRANSITION_WEST'
        elif nx >= GRID_WIDTH:
            self.scene_x += 1; self.x = 0; scene_changed_flag = True
            transition_key = 'LORE.SCENE_TRANSITION_EAST'
        else: self.x = nx

        if ny < 0:
            self.scene_y -= 1; self.y = GRID_HEIGHT - 1; scene_changed_flag = True
            if not transition_key: transition_key = 'LORE.SCENE_TRANSITION_NORTH'
        elif ny >= GRID_HEIGHT:
            self.scene_y += 1; self.y = 0; scene_changed_flag = True
            if not transition_key: transition_key = 'LORE.SCENE_TRANSITION_SOUTH'
        else: self.y = ny

        self.char = new_char
        if scene_changed_flag:
            game_manager.handle_player_scene_change(self, old_scene_x, old_scene_y)
            if transition_key: socketio_instance.emit('lore_message', {'messageKey': transition_key, 'placeholders': {'scene_x': self.scene_x, 'scene_y': self.scene_y}, 'type': 'system'}, room=self.id)
        
        # FOV needs to be recalculated if position or scene changes
        if scene_changed_flag or self.x != original_x_tile or self.y != original_y_tile:
            current_scene = game_manager.get_or_create_scene(self.scene_x, self.scene_y)
            self.visible_tiles_cache = game_manager.calculate_fov(self.x, self.y, current_scene, SENSE_SIGHT_RANGE)

        return scene_changed_flag or (self.x != original_x_tile or self.y != original_y_tile)


    def drink_potion(self, socketio_instance):
        if self.potions > 0: self.potions -= 1; self.current_health = min(self.max_health, self.current_health + 15); socketio_instance.emit('lore_message', {'messageKey': 'LORE.POTION_DRINK_SUCCESS', 'type': 'event-good'}, room=self.id); return True
        else: socketio_instance.emit('lore_message', {'messageKey': 'LORE.POTION_DRINK_FAIL_EMPTY', 'type': 'event-bad'}, room=self.id); return False

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
                if reason == "water_tile": socketio_instance.emit('player_event', {'type': 'stepped_in_water', 'sid': self.id}, room=self.id); socketio_instance.emit('lore_message', {'messageKey': 'LORE.BECAME_WET_WATER', 'type': 'system'}, room=self.id)
                elif reason == "rain": socketio_instance.emit('lore_message', {'messageKey': 'LORE.BECAME_WET_RAIN', 'type': 'system'}, room=self.id)
            else: socketio_instance.emit('lore_message', {'messageKey': 'LORE.BECAME_DRY', 'type': 'system'}, room=self.id)

    def regenerate_mana(self, base_regen_amount, pixie_boost_total, socketio_instance):
        total_regen_this_cycle = base_regen_amount + pixie_boost_total
        self.mana_regen_accumulator += total_regen_this_cycle
        if self.mana_regen_accumulator >= 1.0:
            mana_to_add = int(self.mana_regen_accumulator)
            self.current_mana = min(self.max_mana, self.current_mana + mana_to_add)
            self.mana_regen_accumulator -= mana_to_add
            if pixie_boost_total > 0 and mana_to_add > 0: socketio_instance.emit('lore_message', {'messageKey': 'LORE.PIXIE_MANA_BOOST', 'type': 'event-good', 'placeholders': {'amount': mana_to_add}}, room=self.id)

    def get_public_data(self):
        return {'id': self.id, 'name': self.name, 'x': self.x, 'y': self.y, 'char': self.char,
                'scene_x': self.scene_x, 'scene_y': self.scene_y, 'is_wet': self.is_wet}

    def get_full_data(self):
        return {'id': self.id, 'name': self.name, 'scene_x': self.scene_x, 'scene_y': self.scene_y,
                'x': self.x, 'y': self.y, 'char': self.char, 'max_health': self.max_health,
                'current_health': self.current_health, 'max_mana': self.max_mana,
                'current_mana': int(self.current_mana), 'potions': self.potions, 'gold': self.gold,
                'walls': self.walls, 'is_wet': self.is_wet}

class Scene:
    def __init__(self, scene_x, scene_y, name_generator_func=None):
        self.scene_x = scene_x; self.scene_y = scene_y
        self.name = f"Area ({scene_x},{scene_y})"
        if name_generator_func: self.name = name_generator_func(scene_x, scene_y)
        self.players_sids = set(); self.npc_ids = set()
        self.terrain_grid = [[TILE_FLOOR for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
        self.is_indoors = False
        self.game_manager_ref = None

    def add_player(self, player_sid): self.players_sids.add(player_sid)
    def remove_player(self, player_sid): self.players_sids.discard(player_sid)
    def get_player_sids(self): return list(self.players_sids)
    def add_npc(self, npc_id): self.npc_ids.add(npc_id)
    def remove_npc(self, npc_id): self.npc_ids.discard(npc_id)
    def get_npc_ids(self): return list(self.npc_ids)
    
    def get_tile_type(self, x, y):
        if 0 <= y < GRID_HEIGHT and 0 <= x < GRID_WIDTH: return self.terrain_grid[y][x]
        return TILE_WALL # Treat out-of-bounds as opaque walls for FOV

    def is_transparent(self, x, y):
        """Checks if a tile at (x,y) allows light to pass through."""
        if not (0 <= x < GRID_WIDTH and 0 <= y < GRID_HEIGHT):
            return False # Out of bounds blocks light
        tile_type = self.terrain_grid[y][x]
        return tile_type == TILE_FLOOR or tile_type == TILE_WATER # Example: Walls block light

    def is_walkable(self, x, y):
        """Checks if a tile at (x,y) can be walked on."""
        if not (0 <= x < GRID_WIDTH and 0 <= y < GRID_HEIGHT):
            return False
        tile_type = self.terrain_grid[y][x]
        return tile_type == TILE_FLOOR or tile_type == TILE_WATER

    def set_tile_type(self, x, y, tile_type):
        if 0 <= y < GRID_HEIGHT and 0 <= x < GRID_WIDTH: self.terrain_grid[y][x] = tile_type; return True
        return False
    
    def get_terrain_for_payload(self, visible_tiles=None):
        terrain_data = {'walls': [], 'water': []}
        # If visible_tiles is provided, only include terrain within that set
        if visible_tiles:
            for r_idx, row in enumerate(self.terrain_grid):
                for c_idx, tile_type in enumerate(row):
                    if (c_idx, r_idx) in visible_tiles:
                        if tile_type == TILE_WALL: terrain_data['walls'].append({'x': c_idx, 'y': r_idx})
                        elif tile_type == TILE_WATER: terrain_data['water'].append({'x': c_idx, 'y': r_idx})
        else: # Fallback to sending all (e.g., for a map editor or admin view)
            for r_idx, row in enumerate(self.terrain_grid):
                for c_idx, tile_type in enumerate(row):
                    if tile_type == TILE_WALL: terrain_data['walls'].append({'x': c_idx, 'y': r_idx})
                    elif tile_type == TILE_WATER: terrain_data['water'].append({'x': c_idx, 'y': r_idx})
        return terrain_data

    def is_npc_at(self, x, y, exclude_id=None):
        if not self.game_manager_ref: app.logger.warning(f"Scene ({self.scene_x},{self.scene_y}) checking is_npc_at without game_manager_ref!"); return False
        for npc_id_in_scene in self.npc_ids:
            if exclude_id and npc_id_in_scene == exclude_id: continue
            npc = self.game_manager_ref.get_npc(npc_id_in_scene)
            if npc and npc.x == x and npc.y == y: return True
        return False
    def is_player_at(self, x, y, player_id_to_check=None):
        if not self.game_manager_ref: app.logger.warning(f"Scene ({self.scene_x},{self.scene_y}) checking is_player_at without game_manager_ref!"); return False
        for player_sid_in_scene in self.players_sids:
            player = self.game_manager_ref.get_player(player_sid_in_scene)
            if player and player.x == x and player.y == y: return True
        return False

class GameManager:
    def __init__(self, socketio_instance):
        self.players = {}; self.scenes = {}; self.npcs = {}
        self.queued_actions = {}; self.socketio = socketio_instance
        self.server_is_raining = SERVER_IS_RAINING
        self.heartbeats_until_mana_regen = HEARTBEATS_PER_MANA_REGEN_CYCLE
        self.loop_is_actually_running_flag = False
        self.game_loop_greenlet = None
        self.loop_iteration_count = 0
        # Multipliers for transforming coordinates to octants for FOV
        self._fov_octant_transforms = [
            (1,  0,  0,  1), (0,  1,  1,  0), (0, -1,  1,  0), (-1,  0,  0,  1),
            (-1,  0,  0, -1), (0, -1, -1,  0), (0,  1, -1,  0), (1,  0,  0, -1)
        ]


    def calculate_fov(self, observer_x, observer_y, scene, radius):
        """Calculates Field of View using Recursive Shadowcasting for a given observer and scene."""
        visible_tiles = set()
        visible_tiles.add((observer_x, observer_y)) # Observer's own tile is always visible

        for octant in range(8):
            self._cast_light_octant(observer_x, observer_y, radius, 1, 1.0, 0.0, octant, scene, visible_tiles)
        return visible_tiles

    def _cast_light_octant(self, cx, cy, radius, row_depth, start_slope, end_slope, octant, scene, visible_tiles):
        xx, xy, yx, yy = self._fov_octant_transforms[octant]
        radius_squared = radius * radius

        if start_slope < end_slope:
            return

        for i in range(row_depth, radius + 1):
            blocked_for_row = False
            dx, dy = -i, -i # Start at the top-left of the bounding box for the row in this octant

            while dx <= 0:
                dx += 1
                # Transform cell coordinates from relative to octant to absolute map coordinates
                map_x = cx + dx * xx + dy * xy
                map_y = cy + dx * yx + dy * yy

                # Check if the cell is within bounds of the grid
                if not (0 <= map_x < GRID_WIDTH and 0 <= map_y < GRID_HEIGHT):
                    continue

                # Calculate slopes for the current cell
                # Slopes are calculated from the perspective of the observer at (0,0)
                # The dx, dy are relative to the observer within the transformed octant
                # Using cell centers for more accuracy
                left_slope = (dx - 0.5) / (dy + 0.5)
                right_slope = (dx + 0.5) / (dy - 0.5)

                if start_slope < right_slope: # If the start_slope is to the right of our cell's right_slope, skip
                    continue
                elif end_slope > left_slope: # If the end_slope is to the left of our cell's left_slope, this row is done
                    break

                # Check if the tile is within the circular radius
                if (dx * dx + dy * dy) < radius_squared:
                    visible_tiles.add((map_x, map_y))

                if not scene.is_transparent(map_x, map_y): # Current cell blocks light
                    if blocked_for_row: # Already in a shadow
                        continue # Stay in shadow, don't recurse
                    else: # Wall starts here
                        blocked_for_row = True
                        # Shadow begins to the right of this cell, recurse for the part of the row to the left
                        self._cast_light_octant(cx, cy, radius, i + 1, start_slope, left_slope, octant, scene, visible_tiles)
                        # The new scan for the remainder of this shadow starts from the right of this cell
                        start_slope = right_slope # Continue scan to the right of this shadow
                else: # Current cell is transparent
                    if blocked_for_row: # We were in a shadow, but this cell is clear
                        blocked_for_row = False
                        start_slope = right_slope # Start a new scan from this cell's right edge
            
            if blocked_for_row: # The entire rest of this row was blocked
                break


    def spawn_initial_npcs(self):
        scene_0_0 = self.get_or_create_scene(0,0)
        for i in range(3):
            px, py = random.randint(0, GRID_WIDTH-1), random.randint(0, GRID_HEIGHT-1)
            while not scene_0_0.is_walkable(px,py) or self.get_npc_at(px,py,0,0) is not None:
                 px, py = random.randint(0, GRID_WIDTH-1), random.randint(0, GRID_HEIGHT-1)
            pixie = ManaPixie(0, 0, initial_x=px, initial_y=py)
            self.npcs[pixie.id] = pixie; scene_0_0.add_npc(pixie.id)
            app.logger.info(f"Spawned pixie {pixie.name} at ({pixie.scene_x},{pixie.scene_y}) tile ({pixie.x},{pixie.y})")

    def setup_spawn_shrine(self, scene_obj):
        mid_x, mid_y = GRID_WIDTH // 2, GRID_HEIGHT // 2; shrine_size = 2
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
            new_scene.game_manager_ref = self
            if scene_x == 0 and scene_y == 0:
                self.setup_spawn_shrine(new_scene)
            self.scenes[scene_coords] = new_scene
            app.logger.info(f"Created new scene at ({scene_x},{scene_y}): {new_scene.name}")
        return self.scenes[scene_coords]

    def add_player(self, sid):
        name = get_player_name(sid); player = Player(sid, name)
        app.logger.info(f"GM Add Player: Creating player {name} ({sid}).")
        self.players[sid] = player
        scene = self.get_or_create_scene(player.scene_x, player.scene_y); scene.add_player(sid)
        
        # Initial FOV calculation for the new player
        player.visible_tiles_cache = self.calculate_fov(player.x, player.y, scene, SENSE_SIGHT_RANGE)
        
        app.logger.info(f"GM Add Player: Added {name} to scene ({player.scene_x},{player.scene_y}). Total players: {len(self.players)}")

        new_player_public_data = player.get_public_data()
        for other_sid_in_scene in scene.get_player_sids():
            if other_sid_in_scene != sid:
                other_player = self.get_player(other_sid_in_scene)
                if other_player and self.is_player_visible_to_observer(other_player, player): # Check if new player is visible to existing
                     self.socketio.emit('player_entered_your_scene', new_player_public_data, room=other_sid_in_scene)
        return player

    def remove_player(self, sid):
        player = self.players.pop(sid, None)
        if sid in self.queued_actions: del self.queued_actions[sid]
        if player:
            old_scene_coords = (player.scene_x, player.scene_y)
            if old_scene_coords in self.scenes:
                scene = self.scenes[old_scene_coords]; scene.remove_player(sid)
                app.logger.info(f"Removed {player.name} from scene {old_scene_coords}. Players in scene: {len(scene.get_player_sids())}")
                for other_sid_in_scene in scene.get_player_sids():
                     self.socketio.emit('player_exited_your_scene', {'id': sid, 'name': player.name}, room=other_sid_in_scene) # No visibility check needed for exit
            return player
        return None

    def get_player(self, sid): return self.players.get(sid)
    def get_npc(self, npc_id): return self.npcs.get(npc_id)
    def get_npc_at(self, x, y, scene_x, scene_y):
        for npc_id, npc_obj in self.npcs.items():
            if npc_obj.scene_x == scene_x and npc_obj.scene_y == scene_y and npc_obj.x == x and npc_obj.y == y:
                return npc_obj
        return None
    def get_player_at(self, x, y, scene_x, scene_y):
        for player_obj in self.players.values():
            if player_obj.scene_x == scene_x and player_obj.scene_y == scene_y and player_obj.x == x and player_obj.y == y:
                return player_obj
        return None

    def handle_player_scene_change(self, player, old_scene_x, old_scene_y):
        old_scene_coords = (old_scene_x, old_scene_y); new_scene_coords = (player.scene_x, player.scene_y)
        if old_scene_coords != new_scene_coords:
            if old_scene_coords in self.scenes:
                old_scene_obj = self.scenes[old_scene_coords]; old_scene_obj.remove_player(player.id)
                app.logger.info(f"Player {player.name} left scene {old_scene_coords}.")
                for other_sid in old_scene_obj.get_player_sids():
                    self.socketio.emit('player_exited_your_scene', {'id': player.id, 'name': player.name}, room=other_sid)

            new_scene_obj = self.get_or_create_scene(player.scene_x, player.scene_y); new_scene_obj.add_player(player.id)
            player.visible_tiles_cache = self.calculate_fov(player.x, player.y, new_scene_obj, SENSE_SIGHT_RANGE) # Update FOV for new scene
            
            app.logger.info(f"Player {player.name} entered scene {new_scene_coords}. Terrain: {new_scene_obj.name}")
            player_public_data_for_new_scene = player.get_public_data()
            for other_sid in new_scene_obj.get_player_sids():
                if other_sid != player.id:
                    other_player = self.get_player(other_sid)
                    if other_player and self.is_player_visible_to_observer(other_player, player):
                        self.socketio.emit('player_entered_your_scene', player_public_data_for_new_scene, room=other_sid)


    def is_player_visible_to_observer(self, obs_p, target_p):
        if not obs_p or not target_p: return False
        if obs_p.id == target_p.id: return False
        if obs_p.scene_x != target_p.scene_x or obs_p.scene_y != target_p.scene_y: return False
        # Use FOV cache of the observer
        return (target_p.x, target_p.y) in obs_p.visible_tiles_cache

    def is_npc_visible_to_observer(self, obs_p, target_npc):
        if not obs_p or not target_npc: return False
        if obs_p.scene_x != target_npc.scene_x or obs_p.scene_y != target_npc.scene_y: return False
        # Use FOV cache of the observer
        return (target_npc.x, target_npc.y) in obs_p.visible_tiles_cache


    def get_visible_players_for_observer(self, observer_player):
        visible_others = []
        # FOV is already calculated and cached on player move/scene change.
        # If not, it should be calculated here or ensured it's up-to-date.
        # For simplicity, assume player.visible_tiles_cache is current.
        
        scene = self.get_or_create_scene(observer_player.scene_x, observer_player.scene_y)
        for target_sid in scene.get_player_sids():
            if target_sid == observer_player.id: continue
            target_player = self.get_player(target_sid)
            if target_player and (target_player.x, target_player.y) in observer_player.visible_tiles_cache:
                visible_others.append(target_player.get_public_data())
        return visible_others

    def get_visible_npcs_for_observer(self, observer_player):
        visible_npcs_data = []
        # Assume player.visible_tiles_cache is current.
        scene = self.get_or_create_scene(observer_player.scene_x, observer_player.scene_y)
        for npc_id in scene.get_npc_ids():
            npc = self.get_npc(npc_id)
            if npc and (npc.x, npc.y) in observer_player.visible_tiles_cache:
                   visible_npcs_data.append(npc.get_public_data())
        return visible_npcs_data

    def get_target_coordinates(self, player, dx, dy): return player.x + dx, player.y + dy

    def get_general_direction(self, observer, target):
        dx = target.x - observer.x; dy = target.y - observer.y
        if abs(dx) > abs(dy): return "to the east" if dx > 0 else "to the west"
        elif abs(dy) > abs(dx): return "to the south" if dy > 0 else "to the north"
        else:
            if dx == 0 and dy == 0: return "right here"
            if dx > 0 and dy > 0: return "to the southeast"
            elif dx < 0 and dy > 0: return "to the southwest"
            elif dx > 0 and dy < 0: return "to the northeast"
            elif dx < 0 and dy < 0: return "to the northwest"
            return "nearby"

    def process_sensory_perception(self, player, scene):
        perceived_cues_this_tick = set()
        # Ensure player's FOV cache is up-to-date if it wasn't updated by a move.
        # For a 'look' action, this might be the place to explicitly recalculate.
        # player.visible_tiles_cache = self.calculate_fov(player.x, player.y, scene, SENSE_SIGHT_RANGE)

        for npc_id in scene.get_npc_ids():
            npc = self.get_npc(npc_id)
            if not npc or npc.is_hidden: continue

            is_visible_flag = (npc.x, npc.y) in player.visible_tiles_cache
            distance = abs(player.x - npc.x) + abs(player.y - npc.y)

            if is_visible_flag:
                for cue_key, relevance, _ in npc.sensory_cues.get('sight', []):
                    if random.random() < (relevance * 0.05) and cue_key not in perceived_cues_this_tick:
                        self.socketio.emit('lore_message', {'messageKey': cue_key, 'placeholders': {'npcName': npc.name}, 'type': 'sensory-sight'}, room=player.id)
                        perceived_cues_this_tick.add(cue_key); break
            else: # NPC not in FOV, rely on other senses
                for sense_type in ['sound', 'smell', 'magic']:
                    for cue_key, relevance, cue_range in npc.sensory_cues.get(sense_type, []):
                        if distance <= cue_range:
                            perception_chance = relevance * (1 - (distance / (cue_range + 1.0))) * 0.5
                            if random.random() < perception_chance and cue_key not in perceived_cues_this_tick:
                                self.socketio.emit('lore_message', {'messageKey': cue_key, 'placeholders': {'npcName': npc.name, 'direction': self.get_general_direction(player, npc)}, 'type': f'sensory-{sense_type}'}, room=player.id)
                                perceived_cues_this_tick.add(cue_key); break
                        if cue_key in perceived_cues_this_tick: break

    def process_actions(self):
        current_actions_to_process = dict(self.queued_actions); self.queued_actions.clear(); processed_sids = set()
        for sid_action, action_data in current_actions_to_process.items():
            if sid_action in processed_sids : continue
            player = self.get_player(sid_action);
            if not player: app.logger.warning(f"Action from non-existent player SID {sid_action}"); continue

            action_type = action_data.get('type'); details = action_data.get('details', {})
            app.logger.debug(f"Processing action for {player.name}: {action_type} with details {details}")
            scene_of_player = self.get_or_create_scene(player.scene_x, player.scene_y) # Get current scene for player

            if action_type == 'move' or action_type == 'look':
                dx, dy = details.get('dx', 0), details.get('dy', 0)
                new_char_for_player = details.get('newChar', player.char)
                
                position_or_char_changed = False
                if action_type == 'move' and (dx != 0 or dy != 0):
                    target_x, target_y = player.x + dx, player.y + dy
                    can_move_to_tile = True
                    
                    if 0 <= target_x < GRID_WIDTH and 0 <= target_y < GRID_HEIGHT:
                        tile_type_at_target = scene_of_player.get_tile_type(target_x, target_y)
                        npc_at_target = self.get_npc_at(target_x, target_y, player.scene_x, player.scene_y)
                        
                        if not scene_of_player.is_walkable(target_x, target_y): # Check general walkability first
                            self.socketio.emit('lore_message', {'messageKey': 'LORE.ACTION_BLOCKED_WALL', 'type': 'event-bad'}, room=player.id); can_move_to_tile = False
                        elif npc_at_target and isinstance(npc_at_target, ManaPixie):
                            if npc_at_target.attempt_evade(player.x, player.y, scene_of_player):
                                self.socketio.emit('lore_message', {'messageKey': 'LORE.PIXIE_MOVED_AWAY', 'type': 'system', 'placeholders':{'pixieName': npc_at_target.name}}, room=player.id)
                            else:
                                self.socketio.emit('lore_message', {'messageKey': 'LORE.PIXIE_BLOCKED_PATH', 'type': 'event-bad', 'placeholders':{'pixieName': npc_at_target.name}}, room=player.id); can_move_to_tile = False
                        elif tile_type_at_target == TILE_WATER:
                            player.set_wet_status(True, self.socketio, reason="water_tile")
                            
                    if can_move_to_tile:
                        if player.update_position(dx, dy, new_char_for_player, self, self.socketio):
                            position_or_char_changed = True
                    elif player.char != new_char_for_player :
                        player.char = new_char_for_player
                        position_or_char_changed = True
                
                elif action_type == 'look': # Or move with dx=0, dy=0 but char changes
                    if player.char != new_char_for_player:
                        player.char = new_char_for_player # Just update char, position update not needed for turn only
                        position_or_char_changed = True
                    # For 'look', explicitly recalculate FOV and process sensory perception
                    player.visible_tiles_cache = self.calculate_fov(player.x, player.y, scene_of_player, SENSE_SIGHT_RANGE)
                    self.process_sensory_perception(player, scene_of_player)
                
                if position_or_char_changed and action_type != 'look': # FOV is updated in player.update_position for move
                    # For 'look' with char change, FOV also needs update if not done by explicit look logic
                    player.visible_tiles_cache = self.calculate_fov(player.x, player.y, scene_of_player, SENSE_SIGHT_RANGE)


            elif action_type == 'build_wall':
                dx, dy = details.get('dx', 0), details.get('dy', 0); target_x, target_y = self.get_target_coordinates(player, dx, dy)
                if not (0 <= target_x < GRID_WIDTH and 0 <= target_y < GRID_HEIGHT): self.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_FAIL_OUT_OF_BOUNDS', 'type': 'event-bad'}, room=player.id)
                elif scene_of_player.get_tile_type(target_x, target_y) != TILE_FLOOR: self.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_FAIL_OBSTRUCTED', 'type': 'event-bad'}, room=player.id)
                elif self.get_npc_at(target_x, target_y, player.scene_x, player.scene_y) or self.get_player_at(target_x, target_y, player.scene_x, player.scene_y): self.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_FAIL_OBSTRUCTED', 'type': 'event-bad'}, room=player.id)
                elif not player.has_wall_items(): self.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_FAIL_NO_MATERIALS', 'type': 'event-bad'}, room=player.id)
                else:
                    player.use_wall_item(); scene_of_player.set_tile_type(target_x, target_y, TILE_WALL)
                    self.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_SUCCESS', 'placeholders': {'walls': player.walls}, 'type': 'event-good'}, room=player.id)
                    # Re-calculate FOV for all players in scene after terrain change
                    for p_sid in scene_of_player.get_player_sids():
                        p = self.get_player(p_sid)
                        if p: p.visible_tiles_cache = self.calculate_fov(p.x, p.y, scene_of_player, SENSE_SIGHT_RANGE)

            elif action_type == 'destroy_wall':
                dx, dy = details.get('dx', 0), details.get('dy', 0); target_x, target_y = self.get_target_coordinates(player, dx, dy)
                if not (0 <= target_x < GRID_WIDTH and 0 <= target_y < GRID_HEIGHT): self.socketio.emit('lore_message', {'messageKey': 'LORE.DESTROY_FAIL_OUT_OF_BOUNDS', 'type': 'event-bad'}, room=player.id)
                elif scene_of_player.get_tile_type(target_x, target_y) != TILE_WALL: self.socketio.emit('lore_message', {'messageKey': 'LORE.DESTROY_FAIL_NO_WALL', 'type': 'event-bad'}, room=player.id)
                elif not player.can_afford_mana(DESTROY_WALL_MANA_COST): self.socketio.emit('lore_message', {'messageKey': 'LORE.DESTROY_FAIL_NO_MANA', 'placeholders': {'manaCost': DESTROY_WALL_MANA_COST}, 'type': 'event-bad'}, room=player.id)
                else:
                    player.spend_mana(DESTROY_WALL_MANA_COST); player.add_wall_item(); scene_of_player.set_tile_type(target_x, target_y, TILE_FLOOR)
                    self.socketio.emit('lore_message', {'messageKey': 'LORE.DESTROY_SUCCESS', 'placeholders': {'walls': player.walls, 'manaCost': DESTROY_WALL_MANA_COST}, 'type': 'event-good'}, room=player.id)
                    for p_sid in scene_of_player.get_player_sids(): # Re-calculate FOV for all players in scene
                        p = self.get_player(p_sid)
                        if p: p.visible_tiles_cache = self.calculate_fov(p.x, p.y, scene_of_player, SENSE_SIGHT_RANGE)

            elif action_type == 'drink_potion': player.drink_potion(self.socketio)

            elif action_type == 'say':
                message_text = details.get('message', '');
                if message_text:
                    chat_data = { 'sender_id': player.id, 'sender_name': player.name, 'message': message_text, 'type': 'say', 'scene_coords': f"({player.scene_x},{player.scene_y})" }
                    if (player.scene_x, player.scene_y) in self.scenes:
                        for target_sid in scene_of_player.get_player_sids(): self.socketio.emit('chat_message', chat_data, room=target_sid)

            elif action_type == 'shout':
                message_text = details.get('message', '')
                if message_text:
                    if player.spend_mana(SHOUT_MANA_COST):
                        chat_data = { 'sender_id': player.id, 'sender_name': player.name, 'message': message_text, 'type': 'shout', 'scene_coords': f"({player.scene_x},{player.scene_y})" }
                        for target_player_obj in list(self.players.values()):
                            if abs(target_player_obj.scene_x - player.scene_x) <= 1 and \
                               abs(target_player_obj.scene_y - player.scene_y) <= 1:
                                self.socketio.emit('chat_message', chat_data, room=target_player_obj.id)
                        self.socketio.emit('lore_message', {'messageKey': 'LORE.VOICE_BOOM_SHOUT', 'placeholders': {'manaCost': SHOUT_MANA_COST}, 'type': 'system'}, room=player.id)
                    else:
                        self.socketio.emit('lore_message', {'messageKey': 'LORE.LACK_MANA_SHOUT', 'placeholders': {'manaCost': SHOUT_MANA_COST}, 'type': 'event-bad'}, room=player.id)

            processed_sids.add(sid_action)


# --- Global Game Manager Instance ---
game_manager = GameManager(socketio_instance=sio)


# --- Game Loop Internals (Robustified) ---
def _game_loop_iteration_content():
    game_manager.loop_iteration_count += 1
    loop_count = game_manager.loop_iteration_count
    try: game_manager.process_actions()
    except Exception as e: app.logger.error(f"Heartbeat {loop_count}: EXCEPTION in process_actions: {e}", exc_info=True)
    try:
        game_manager.heartbeats_until_mana_regen -=1
        if game_manager.heartbeats_until_mana_regen <= 0:
            for player_obj in list(game_manager.players.values()):
                pixie_boost_for_player = 0
                player_scene_obj = game_manager.get_or_create_scene(player_obj.scene_x, player_obj.scene_y)
                for npc_id in player_scene_obj.get_npc_ids():
                    npc = game_manager.get_npc(npc_id)
                    if npc and isinstance(npc, ManaPixie):
                        dist = abs(player_obj.x - npc.x) + abs(player_obj.y - npc.y)
                        if dist <= PIXIE_PROXIMITY_FOR_BOOST: pixie_boost_for_player += PIXIE_MANA_REGEN_BOOST
                player_obj.regenerate_mana(BASE_MANA_REGEN_PER_HEARTBEAT_CYCLE, pixie_boost_for_player, sio)
            game_manager.heartbeats_until_mana_regen = HEARTBEATS_PER_MANA_REGEN_CYCLE
    except Exception as e: app.logger.error(f"Heartbeat {loop_count}: EXCEPTION in mana_regen: {e}", exc_info=True)
    try:
        if game_manager.server_is_raining:
            for player_obj in list(game_manager.players.values()):
                player_scene = game_manager.get_or_create_scene(player_obj.scene_x, player_obj.scene_y)
                if not player_scene.is_indoors and not player_obj.is_wet:
                    player_obj.set_wet_status(True, sio, reason="rain")
        for player_obj in list(game_manager.players.values()):
            player_scene = game_manager.get_or_create_scene(player_obj.scene_x, player_obj.scene_y)
            if player_obj.is_wet and (player_scene.is_indoors or not game_manager.server_is_raining):
                 player_obj.set_wet_status(False, sio, reason="indoors_or_dry_weather")
    except Exception as e: app.logger.error(f"Heartbeat {loop_count}: EXCEPTION in rain/wetness: {e}", exc_info=True)
    try:
        if loop_count % 5 == 0: # Less frequent sensory perception updates for non-look actions
            for player_obj in list(game_manager.players.values()):
                scene_of_player = game_manager.get_or_create_scene(player_obj.scene_x, player_obj.scene_y)
                # Ensure FOV is current before general sensory perception if player hasn't moved/looked
                if not player_obj.visible_tiles_cache: # Or if a timer indicates cache is stale
                     player_obj.visible_tiles_cache = game_manager.calculate_fov(player_obj.x, player_obj.y, scene_of_player, SENSE_SIGHT_RANGE)
                game_manager.process_sensory_perception(player_obj, scene_of_player)
    except Exception as e: app.logger.error(f"Heartbeat {loop_count}: EXCEPTION in sensory processing: {e}", exc_info=True)
    try:
        for npc in list(game_manager.npcs.values()):
            if isinstance(npc, ManaPixie):
                scene_of_npc = game_manager.get_or_create_scene(npc.scene_x, npc.scene_y)
                npc.wander(scene_of_npc)
    except Exception as e: app.logger.error(f"Heartbeat {loop_count}: EXCEPTION in NPC updates: {e}", exc_info=True)
    try:
        if game_manager.players:
            current_players_snapshot = list(game_manager.players.values())
            num_updates_sent_this_heartbeat = 0
            for recipient_player in current_players_snapshot:
                if recipient_player.id not in game_manager.players: continue
                
                # Ensure player's FOV is up-to-date before sending data
                # This is crucial if FOV isn't recalculated elsewhere every tick
                # For now, assume it's updated on move/look/terrain change.
                # If not, uncomment:
                # current_player_scene = game_manager.get_or_create_scene(recipient_player.scene_x, recipient_player.scene_y)
                # recipient_player.visible_tiles_cache = game_manager.calculate_fov(recipient_player.x, recipient_player.y, current_player_scene, SENSE_SIGHT_RANGE)

                payload_for_client = {
                    'self_player_data': recipient_player.get_full_data(),
                    'visible_other_players': game_manager.get_visible_players_for_observer(recipient_player),
                    'visible_npcs': game_manager.get_visible_npcs_for_observer(recipient_player),
                    'visible_terrain': game_manager.get_or_create_scene(recipient_player.scene_x, recipient_player.scene_y).get_terrain_for_payload(recipient_player.visible_tiles_cache),
                }
                sio.emit('game_update', payload_for_client, room=recipient_player.id); num_updates_sent_this_heartbeat +=1
            if num_updates_sent_this_heartbeat > 0 and loop_count % 20 == 1:
                app.logger.debug(f"Heartbeat {loop_count}: Sent 'game_update' to {num_updates_sent_this_heartbeat} players.")
            elif len(current_players_snapshot) > 0 and num_updates_sent_this_heartbeat == 0 and loop_count % 20 == 1 :
                app.logger.debug(f"Heartbeat {loop_count}: Players present, but NO 'game_update' emitted.")
    except Exception as e: app.logger.error(f"Heartbeat {loop_count}: EXCEPTION in emitting game updates: {e}", exc_info=True)


def _persistent_game_loop_runner():
    with app.app_context():
        my_pid = os.getpid()
        app.logger.info(f"Persistent game loop runner starting in PID {my_pid}...")
        game_manager.loop_is_actually_running_flag = True
        game_manager.spawn_initial_npcs()
        app.logger.info(f"PID {my_pid}: Initial NPCs spawned. Beginning persistent game loop.")
    while game_manager.loop_is_actually_running_flag:
        loop_start_time = time.time()
        try:
            with app.app_context():
                _game_loop_iteration_content()
        except Exception as e:
            with app.app_context():
                app.logger.critical(
                    f"PID {os.getpid()} Heartbeat {game_manager.loop_iteration_count}: "
                    f"CRITICAL UNCAUGHT EXCEPTION in _game_loop_iteration_content: {e}", exc_info=True
                )
            eventlet.sleep(1.0)
        elapsed_time = time.time() - loop_start_time
        sleep_duration = GAME_HEARTBEAT_RATE - elapsed_time
        if sleep_duration < 0:
            with app.app_context():
                app.logger.warning(
                    f"PID {os.getpid()} Heartbeat {game_manager.loop_iteration_count}: Iteration "
                    f"took too long ({elapsed_time:.4f}s vs {GAME_HEARTBEAT_RATE}s rate). No sleep."
                )
            sleep_duration = 0.0001
        eventlet.sleep(sleep_duration)
    with app.app_context():
        app.logger.info(f"PID {os.getpid()}: Persistent game loop runner terminating as flag is false.")


def start_game_loop_for_worker():
    global _game_loop_started_in_this_process
    with app.app_context():
        my_pid = os.getpid()
        if not _game_loop_started_in_this_process:
            app.logger.info(f"PID {my_pid} Worker: Attempting to start game loop via _persistent_game_loop_runner...")
            try:
                game_manager.game_loop_greenlet = eventlet.spawn(_persistent_game_loop_runner)
                _game_loop_started_in_this_process = True
                app.logger.info(f"PID {my_pid} Worker: Game loop greenlet successfully spawned.")
            except Exception as e:
                app.logger.critical(f"PID {my_pid} Worker: FAILED TO START GAME LOOP GREENLET: {e}", exc_info=True)
        else:
            app.logger.info(f"PID {my_pid} Worker: Game loop already marked as started in this process.")


# --- Flask Blueprint and Routes ---
game_blueprint = Blueprint('game', __name__, template_folder='templates', static_folder='static', static_url_path='/static/game')
@game_blueprint.route('/')
def index_route(): return render_template('index.html')

app.register_blueprint(game_blueprint, url_prefix=GAME_PATH_PREFIX)
sio.init_app(app, path=f"{GAME_PATH_PREFIX}/socket.io")

@app.route('/')
def health_check_route(): return "OK", 200


# --- SocketIO Event Handlers ---
@sio.on('connect')
def handle_connect_event(auth=None):
    with app.app_context():
        player = game_manager.add_player(request.sid)
        app.logger.info(f"Connect: {player.name} ({request.sid}). Total players: {len(game_manager.players)}")
        
        # Initial FOV calculation already done in add_player
        current_scene = game_manager.get_or_create_scene(player.scene_x, player.scene_y)

        emit_ctx('initial_game_data', {
            'player_data': player.get_full_data(),
            'other_players_in_scene': game_manager.get_visible_players_for_observer(player), # Uses FOV
            'visible_npcs': game_manager.get_visible_npcs_for_observer(player), # Uses FOV
            'visible_terrain': current_scene.get_terrain_for_payload(player.visible_tiles_cache), # Send only visible terrain
            'grid_width': GRID_WIDTH, 'grid_height': GRID_HEIGHT,
            'tick_rate': GAME_HEARTBEAT_RATE, 'default_rain_intensity': DEFAULT_RAIN_INTENSITY
        })
        emit_ctx('lore_message', {'messageKey': "LORE.WELCOME_INITIAL", 'type': 'welcome-message'}, room=request.sid)

@sio.on('disconnect')
def handle_disconnect_event():
    with app.app_context():
        player_left = game_manager.remove_player(request.sid)
        if player_left:
            app.logger.info(f"Disconnect: {player_left.name} ({request.sid}). Total players: {len(game_manager.players)}")
        else:
            app.logger.info(f"Disconnect for SID {request.sid} (player not found or already removed).")

@sio.on('queue_player_action')
def handle_queue_player_action(data):
    with app.app_context():
        player = game_manager.get_player(request.sid)
        if not player:
            app.logger.warning(f"Action received from unknown SID: {request.sid}")
            emit_ctx('action_feedback', {'success': False, 'message': "Player not recognized."}); return

        action_type = data.get('type')
        valid_actions = ['move', 'look', 'drink_potion', 'say', 'shout', 'build_wall', 'destroy_wall']
        if action_type not in valid_actions:
            app.logger.warning(f"Player {player.name} sent invalid action type: {action_type}")
            emit_ctx('action_feedback', {'success': False, 'messageKey': 'ACTION_SENT_FEEDBACK.ACTION_FAILED_UNKNOWN_COMMAND', 'placeholders': {'actionWord': action_type}}); return

        game_manager.queued_actions[request.sid] = data
        emit_ctx('action_feedback', {'success': True, 'messageKey': 'ACTION_SENT_FEEDBACK.ACTION_QUEUED'})


# --- Main Execution ---
if __name__ == '__main__':
    with app.app_context():
        app.logger.info(f"Starting Flask-SocketIO server for LOCAL DEVELOPMENT on PID {os.getpid()}...")
    start_game_loop_for_worker()
    sio.run(app,
            debug=app.debug,
            host='0.0.0.0',
            port=int(os.environ.get('PORT', 5000)),
            use_reloader=False)
else:
    with app.app_context():
        app.logger.info(f"App module loaded by WSGI server (e.g., Gunicorn) in PID {os.getpid()}. Game loop to be started by post_fork.")
# app.py

import eventlet
eventlet.monkey_patch()

import os
import random
pinching in vs. spreading out).
        *   It's important to also handle panning during a two-fingerfrom flask import Flask, render_template, request, Blueprint
from flask_socketio import SocketIO, emit as emit_ctx
import time
import traceback
import uuid

# --- Game Settings ---
GRID_WIDTH, GRID gesture if desired, but for now, we'll focus on zoom.
    *   Adjust `centerViewOn_HEIGHT, GAME_TICK_RATE, SHOUT_MANA_COST, MAX_VIEW_DISTANCE = 20, 15, 0.75, 5, 8
_game_loopPlayer` and potentially `estimateCharacterSize` if zoom factor changes affect how centering or canvas sizing should work (though CSS_started_in_this_process = False
DESTROY_WALL_MANA_COST = 10
INITIAL_WALL_ITEMS = 77 # Changed
INITIAL_POTIONS = 77    # Changed

TILE zoom usually handles the visual scaling part well).

**3. Frontend (`style.css`):**
    *   No_FLOOR = 0
TILE_WALL = 1
TILE_WATER = 2

SERVER_IS_RA direct changes are strictly needed for zoom functionality if we're just changing the CSS variable `--game-zoom`, but weINING = True 
DEFAULT_RAIN_INTENSITY = 0.25

PIXIE_CHAR = '*'
PIXIE_MANA_REGEN_BOOST = 1 
PIXIE_PRO need to ensure the layout handles different zoom levels gracefully.

Let's start with `app.py` for the resource countXIMITY_FOR_BOOST = 3 
BASE_MANA_REGEN_PER_TICK = changes.

**File 1: `app.py` (Complete with updated initial resources)**

```python
# app.py

import eventlet
eventlet.monkey_patch()

import os
import random
from flask import Flask 0.5 
TICKS_PER_MANA_REGEN_CYCLE = 3

SENSE_SIGHT_RANGE = MAX_VIEW_DISTANCE
SENSE_SOUND_RANGE_MAX = 8
SENSE_, render_template, request, Blueprint
from flask_socketio import SocketIO, emit as emit_ctx
SMELL_RANGE_MAX = 6
SENSE_MAGIC_RANGE_MAX = 5

defimport time
import traceback
import uuid

# --- Game Settings ---
GRID_WIDTH, GRID_HEIGHT, GAME get_player_name(sid): return f"Wizard-{sid[:4]}"

class ManaPixie:
_TICK_RATE, SHOUT_MANA_COST, MAX_VIEW_DISTANCE = 20,    def __init__(self, scene_x, scene_y, initial_x=None, initial_y=None):
        self.id = str(uuid.uuid4())
        self.char = PIX 15, 0.75, 5, 8
_game_loop_started_in_this_process = False
DESTROY_WALL_MANA_COST = 10
INITIAL_WALL_IE_CHAR
        self.scene_x = scene_x
        self.scene_y = scene_y
        self.x = initial_x if initial_x is not None else random.randint(0,ITEMS = 77 # Updated
INITIAL_POTIONS = 77    # Updated

TILE_FLOOR = 0
TILE_WALL = 1
TILE_WATER = 2

SERVER_IS_RAINING = True  GRID_WIDTH - 1)
        self.y = initial_y if initial_y is not None else
DEFAULT_RAIN_INTENSITY = 0.25

PIXIE_CHAR = '*'
PIX random.randint(0, GRID_HEIGHT - 1)
        self.name = f"Pixie-{IE_MANA_REGEN_BOOST = 1 
PIXIE_PROXIMITY_self.id[:4]}"
        self.sensory_cues = {
            'sight': [
FOR_BOOST = 3 
BASE_MANA_REGEN_PER_TICK = 0.5                ('SENSORY.PIXIE_SIGHT_SHIMMER', 0.8, SENSE_SIGHT_RANGE),
                ('SENSORY.PIXIE_SIGHT_DART', 0.6 
TICKS_PER_MANA_REGEN_CYCLE = 3

SENSE_SIGHT_RANGE = MAX_VIEW_DISTANCE
SENSE_SOUND_RANGE_MAX = 8
SENSE_SMELL_, SENSE_SIGHT_RANGE)
            ],
            'sound': [
                ('SENSORY.PIXIE_SOUND_CHIME', 0.7, 5),
                ('SENSORYRANGE_MAX = 6
SENSE_MAGIC_RANGE_MAX = 5

def get_player_name(sid): return f"Wizard-{sid[:4]}"

class ManaPixie:
    def __init.PIXIE_SOUND_WINGS', 0.4, 3)
            ],
            'smell': [
                ('SENSORY.PIXIE_SMELL_OZONE', 0__(self, scene_x, scene_y, initial_x=None, initial_y=None):
.3, 2)
            ],
            'magic': [
                ('SENSORY.PIX        self.id = str(uuid.uuid4())
        self.char = PIXIE_CHAR
        self.IE_MAGIC_AURA', 0.9, 4)
            ]
        }
        selfscene_x = scene_x
        self.scene_y = scene_y
        self.x = initial_x if initial_x is not None else random.randint(0, GRID_WIDTH - 1).is_hidden = False

    def get_public_data(self):
        return {'id': self
        self.y = initial_y if initial_y is not None else random.randint(0, GRID.id, 'name': self.name, 'char': self.char, 'x': self.x, 'y': self.y, 
                'scene_x': self.scene_x, 'scene__HEIGHT - 1)
        self.name = f"Pixie-{self.id[:4]}"
        self.sensory_cues = {
            'sight': [('SENSORY.PIXIEy': self.scene_y}

    def wander(self, scene): # scene is a Scene object
        if random.random() < 0.3:
            dx, dy = random.choice([-1, 0,_SIGHT_SHIMMER', 0.8, SENSE_SIGHT_RANGE), ('SENSORY. 1]), random.choice([-1, 0, 1])
            if dx == 0 and dyPIXIE_SIGHT_DART', 0.6, SENSE_SIGHT_RANGE)],
            'sound': [('SENSORY.PIXIE_SOUND_CHIME', 0.7, == 0: return
            new_x, new_y = self.x + dx, self.y + dy
            if 0 <= new_x < GRID_WIDTH and 0 <= new_y < GRID 5), ('SENSORY.PIXIE_SOUND_WINGS', 0.4, 3_HEIGHT:
                tile_type = scene.get_tile_type(new_x, new_y)],
            'smell': [('SENSORY.PIXIE_SMELL_OZONE', 0.3, 2)],
            'magic': [('SENSORY.PIXIE_MAGIC)
                if tile_type != TILE_WALL and not scene.is_npc_at(new_x, new_y, exclude_id=self.id):
                    self.x, self.y = new_x_AURA', 0.9, 4)]
        }
        self.is_hidden = False

    def get_public_data(self):
        return {'id': self.id, 'name':, new_y
    
    def attempt_evade(self, player_x, player_y, scene): self.name, 'char': self.char, 'x': self.x, 'y': self.y
        possible_moves = []
        for dx_evade in [-1, 0, 1]:
            for, 
                'scene_x': self.scene_x, 'scene_y': self.scene_ dy_evade in [-1, 0, 1]:
                if dx_evade == 0 and dy_evade == 0: continue
                evade_x, evade_y = self.x + dxy}

    def wander(self, scene):
        if random.random() < 0.3:
_evade, self.y + dy_evade
                if 0 <= evade_x < GRID_            dx, dy = random.choice([-1, 0, 1]), random.choice([-1, 0, 1])
            if dx == 0 and dy == 0: return
            new_x, new_WIDTH and 0 <= evade_y < GRID_HEIGHT:
                    tile_type = scene.get_tiley = self.x + dx, self.y + dy
            if 0 <= new_x < GRID_type(evade_x, evade_y)
                    if tile_type != TILE_WALL and_WIDTH and 0 <= new_y < GRID_HEIGHT:
                tile_type = scene.get_ \
                       not scene.is_npc_at(evade_x, evade_y, exclude_id=self.id) and \
                       not scene.is_player_at(evade_x, evadetile_type(new_x, new_y)
                if tile_type != TILE_WALL and not scene.is_npc_at(new_x, new_y, exclude_id=self.id_y, player_id_to_check=None):
                        possible_moves.append((evade_x,):
                    self.x, self.y = new_x, new_y
    
    def attempt evade_y))
        if possible_moves:
            self.x, self.y = random.choice_evade(self, player_x, player_y, scene):
        possible_moves = []
(possible_moves); return True
        return False

class Player:
    def __init__(self, sid, name        for dx_evade in [-1, 0, 1]:
            for dy_evade in):
        self.id = sid; self.name = name; self.scene_x = 0; self.scene_y = 0
        self.x = GRID_WIDTH // 2; self.y = GRID_ [-1, 0, 1]:
                if dx_evade == 0 and dy_evade == 0: continue
                evade_x, evade_y = self.x + dx_evadeHEIGHT // 2
        self.char = random.choice(['^', 'v', '<', '>'])
, self.y + dy_evade
                if 0 <= evade_x < GRID_WIDTH and 0 <= evade_y < GRID_HEIGHT:
                    tile_type = scene.get_tile_type(        self.max_health = 100; self.current_health = 100
        self.max_mana = 175; self.current_mana = 175.0
evade_x, evade_y)
                    if tile_type != TILE_WALL and \
                       not scene.is_npc_at(evade_x, evade_y, exclude_id=self.        self.potions = INITIAL_POTIONS; self.gold = 0; self.walls = INITIAL_WALL_ITEMS
        self.is_wet = False; self.time_became_wet = 0
id) and \
                       not scene.is_player_at(evade_x, evade_y,        self.mana_regen_accumulator = 0.0

    def update_position(self, dx, player_id_to_check=None):
                        possible_moves.append((evade_x, evade dy, new_char, game_manager, socketio_instance):
        old_scene_x, old_y))
        if possible_moves:
            self.x, self.y = random.choice(_scene_y = self.scene_x, self.scene_y
        original_x_tile, original_ypossible_moves); return True
        return False

class Player:
    def __init__(self, sid,_tile = self.x, self.y
        scene_changed_flag = False; transition_key = name):
        self.id = sid; self.name = name; self.scene_x = 0 None
        nx, ny = self.x + dx, self.y + dy

        if nx < ; self.scene_y = 0
        self.x = GRID_WIDTH // 2; self.0:
            self.scene_x -= 1
            self.x = GRID_WIDTH - 1y = GRID_HEIGHT // 2
        self.char = random.choice(['^', 'v', '<
            scene_changed_flag = True
            transition_key = 'LORE.SCENE_TRANSITION_WEST'', '>'])
        self.max_health = 100; self.current_health = 1
        elif nx >= GRID_WIDTH:
            self.scene_x += 1
            self.x00
        self.max_mana = 175; self.current_mana = 17 = 0
            scene_changed_flag = True
            transition_key = 'LORE.SCENE5.0
        self.potions = INITIAL_POTIONS # Updated
        self.gold = 0; self._TRANSITION_EAST'
        else:
            self.x = nx

        if ny < 0walls = INITIAL_WALL_ITEMS # Updated
        self.is_wet = False; self.time_became:
            self.scene_y -= 1
            self.y = GRID_HEIGHT - 1
_wet = 0
        self.mana_regen_accumulator = 0.0

    def update_position(self            scene_changed_flag = True
            if not transition_key: 
                transition_key = 'LORE.SCENE_TRANSITION_NORTH'
        elif ny >= GRID_HEIGHT:
            self., dx, dy, new_char, game_manager, socketio_instance):
        old_scene_x, old_scene_y = self.scene_x, self.scene_y
        original_xscene_y += 1
            self.y = 0
            scene_changed_flag = True
_tile, original_y_tile = self.x, self.y
        scene_changed_flag = False; transition_key = None
        nx, ny = self.x + dx, self.y + dy            if not transition_key: 
                transition_key = 'LORE.SCENE_TRANSITION_SOUTH'
        else:
            self.y = ny
            
        self.char = new_char
        if nx < 0: self.scene_x -= 1; self.x = GRID_WIDTH
        if scene_changed_flag:
            game_manager.handle_player_scene_change(self - 1; scene_changed_flag = True; transition_key = 'LORE.SCENE_TRANSITION_WEST'
        elif nx >= GRID_WIDTH: self.scene_x += 1; self., old_scene_x, old_scene_y)
            if transition_key: socketio_instance.emit('lore_message', {'messageKey': transition_key, 'placeholders': {'scene_x': selfx = 0; scene_changed_flag = True; transition_key = 'LORE.SCENE_.scene_x, 'scene_y': self.scene_y}, 'type': 'system'}, room=TRANSITION_EAST'
        else: self.x = nx
        if ny < 0: self.self.id)
        return scene_changed_flag or (self.x != original_x_tile or self.yscene_y -= 1; self.y = GRID_HEIGHT - 1; scene_changed_flag = True
            if not transition_key: transition_key = 'LORE.SCENE_TRANSITION_NORTH != original_y_tile)

    def drink_potion(self, socketio_instance):
        if self.potions > 0: self.potions -= 1; self.current_health = min('
        elif ny >= GRID_HEIGHT: self.scene_y += 1; self.y = 0; scene_changed_flag = True
            if not transition_key: transition_key = 'LOREself.max_health, self.current_health + 15); socketio_instance.emit('lore_message', {'messageKey': 'LORE.POTION_DRINK_SUCCESS', 'type': 'event.SCENE_TRANSITION_SOUTH'
        else: self.y = ny
        self.char = new_char
        if scene_changed_flag:
            game_manager.handle_player_scene_-good'}, room=self.id); return True
        else: socketio_instance.emit('lore_message', {'messageKey': 'LORE.POTION_DRINK_FAIL_EMPTY', 'type': 'change(self, old_scene_x, old_scene_y)
            if transition_key: socketio_instance.emit('lore_message', {'messageKey': transition_key, 'placeholders': {'sceneevent-bad'}, room=self.id); return False

    def can_afford_mana(self,_x': self.scene_x, 'scene_y': self.scene_y}, 'type': ' cost): return self.current_mana >= cost
    def spend_mana(self, cost):
        if self.can_afford_mana(cost): self.current_mana -= cost; return True
        return False
    system'}, room=self.id)
        return scene_changed_flag or (self.x != original_x_tile or self.y != original_y_tile)

    def drink_potion(self, socketdef has_wall_items(self): return self.walls > 0
    def use_wall_item(self):
        if self.has_wall_items(): self.walls -= 1; return True
io_instance):
        if self.potions > 0: self.potions -= 1; self.current_health = min(self.max_health, self.current_health + 15); socket        return False
    def add_wall_item(self): self.walls += 1
    
    def set_wet_status(self, status, socketio_instance, reason="unknown"):
        if selfio_instance.emit('lore_message', {'messageKey': 'LORE.POTION_DRINK_SUCCESS', 'type': 'event-good'}, room=self.id); return True
        else: socketio_instance..is_wet != status:
            self.is_wet = status
            if status:
                self.time_became_wet = time.time()
                if reason == "water_tile": socketio_emit('lore_message', {'messageKey': 'LORE.POTION_DRINK_FAIL_EMPTY', 'type': 'event-bad'}, room=self.id); return False

    def can_afford_instance.emit('player_event', {'type': 'stepped_in_water', 'sid': self.id}, room=self.id); socketio_instance.emit('lore_message', {'messageKey': 'mana(self, cost): return self.current_mana >= cost
    def spend_mana(self, cost):
        LORE.BECAME_WET_WATER', 'type': 'system'}, room=self.id)
if self.can_afford_mana(cost): self.current_mana -= cost; return True
                        elif reason == "rain": socketio_instance.emit('lore_message', {'messageKey': 'Lreturn False
    def has_wall_items(self): return self.walls > 0
    def use_wallORE.BECAME_WET_RAIN', 'type': 'system'}, room=self.id)
            else: socketio_instance.emit('lore_message', {'messageKey': 'LORE.BECAME_DRY',_item(self):
        if self.has_wall_items(): self.walls -= 1; return True
        return False
    def add_wall_item(self): self.walls += 1
    
    def set_wet_status(self, status, socketio_instance, reason="unknown"):
         'type': 'system'}, room=self.id)

    def regenerate_mana(self, base_regen_amount, pixie_boost_total, socketio_instance):
        total_regen_this_cycle =if self.is_wet != status:
            self.is_wet = status
            if status:
                self.time_became_wet = time.time()
                if reason == "water_tile": socketio_instance. base_regen_amount + pixie_boost_total
        self.mana_regen_accumulator += total_regen_this_cycle
        if self.mana_regen_accumulator >= 1.0:
            mana_emit('player_event', {'type': 'stepped_in_water', 'sid': self.id}, room=selfto_add = int(self.mana_regen_accumulator)
            self.current_mana = min(.id); socketio_instance.emit('lore_message', {'messageKey': 'LORE.BECAMEself.max_mana, self.current_mana + mana_to_add)
            self.mana__WET_WATER', 'type': 'system'}, room=self.id)
                elif reason == "rain": socketregen_accumulator -= mana_to_add
            if pixie_boost_total > 0 and mana_to_add > 0: socketio_instance.emit('lore_message', {'messageKey': 'LORE.PIXio_instance.emit('lore_message', {'messageKey': 'LORE.BECAME_WET_IE_MANA_BOOST', 'type': 'event-good', 'placeholders': {'amount': manaRAIN', 'type': 'system'}, room=self.id)
            else: socketio_instance.emit('lore_message', {'messageKey': 'LORE.BECAME_DRY', 'type': 'system'}, room=_to_add}}, room=self.id)

    def get_public_data(self):
        self.id)

    def regenerate_mana(self, base_regen_amount, pixie_boost_totalreturn {'id': self.id, 'name': self.name, 'x': self.x, 'y, socketio_instance):
        total_regen_this_cycle = base_regen_amount + pixie_': self.y, 'char': self.char, 
                'scene_x': self.scene_x, 'scene_y': self.scene_y, 'is_wet': self.is_wet}boost_total
        self.mana_regen_accumulator += total_regen_this_cycle
        if self.mana_regen_accumulator >= 1.0:
            mana_to_add = int(self.

    def get_full_data(self):
        return {'id': self.id, 'name': self.name, 'scene_x': self.scene_x, 'scene_y': self.scene_mana_regen_accumulator)
            self.current_mana = min(self.max_mana, self.y,
                'x': self.x, 'y': self.y, 'char': self.charcurrent_mana + mana_to_add)
            self.mana_regen_accumulator -= mana_to_add
            if pixie_boost_total > 0 and mana_to_add > 0: socketio_instance., 'max_health': self.max_health, 
                'current_health': self.current_health, 'max_mana': self.max_mana, 
                'current_mana': int(selfemit('lore_message', {'messageKey': 'LORE.PIXIE_MANA_BOOST', 'type': 'event-good', 'placeholders': {'amount': mana_to_add}}, room=self.current_mana), 'potions': self.potions, 'gold': self.gold, 
                'walls': self.walls, 'is_wet': self.is_wet}

class Scene:
    .id)

    def get_public_data(self):
        return {'id': self.id,def __init__(self, scene_x, scene_y, name_generator_func=None):
         'name': self.name, 'x': self.x, 'y': self.y, 'char': self.char, 
                'scene_x': self.scene_x, 'scene_y': selfself.scene_x = scene_x; self.scene_y = scene_y
        self.name = f"Area ({scene_x},{scene_y})"
        if name_generator_func: self..scene_y, 'is_wet': self.is_wet}

    def get_full_dataname = name_generator_func(scene_x, scene_y)
        self.players_sids(self):
        return {'id': self.id, 'name': self.name, 'scene_x': self.scene_x, 'scene_y': self.scene_y,
                'x': self.x, 'y': self.y, 'char': self.char, 'max_health': self. = set(); self.npc_ids = set()
        self.terrain_grid = [[TILE_FLOOR for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
        self.is_indoors = False
        self.game_manager_ref = None 

    def add_player(self, player_max_health, 
                'current_health': self.current_health, 'max_mana': self.max_mana, 
                'current_mana': int(self.current_mana), 'potionssid): self.players_sids.add(player_sid)
    def remove_player(self,': self.potions, 'gold': self.gold, 
                'walls': self.walls, ' player_sid): self.players_sids.discard(player_sid)
    def get_player_is_wet': self.is_wet}

class Scene:
    def __init__(self, scene_sids(self): return list(self.players_sids)
    def add_npc(self,x, scene_y, name_generator_func=None):
        self.scene_x = scene_ npc_id): self.npc_ids.add(npc_id)
    def remove_npc(selfx; self.scene_y = scene_y
        self.name = f"Area ({scene_x, npc_id): self.npc_ids.discard(npc_id)
    def get_npc_},{scene_y})"
        if name_generator_func: self.name = name_generator_func(scene_x, scene_y)
        self.players_sids = set(); self.npc_idsids(self): return list(self.npc_ids)
    def get_tile_type(self, x, y):
        if 0 <= y < GRID_HEIGHT and 0 <= x < GRID_WIDTH: return self.terrain_grid[y][x]
        return None
    def set_tile_type = set()
        self.terrain_grid = [[TILE_FLOOR for _ in range(GRID_WIDTH(self, x, y, tile_type):
        if 0 <= y < GRID_HEIGHT and )] for _ in range(GRID_HEIGHT)]
        self.is_indoors = False
        self.game_manager_ref = None 

    def add_player(self, player_sid): self.players_sids0 <= x < GRID_WIDTH: self.terrain_grid[y][x] = tile_type; return True
        .add(player_sid)
    def remove_player(self, player_sid): self.players_return False
    def get_terrain_for_payload(self):
        terrain_data = {'walls': [], 'water': []}
        for r_idx, row in enumerate(self.terrain_grid):
sids.discard(player_sid)
    def get_player_sids(self): return list(self.players_sids)
    def add_npc(self, npc_id): self.npc_            for c_idx, tile_type in enumerate(row):
                if tile_type == TILE_ids.add(npc_id)
    def remove_npc(self, npc_id): self.npcWALL: terrain_data['walls'].append({'x': c_idx, 'y': r_idx})
_ids.discard(npc_id)
    def get_npc_ids(self): return list(self                elif tile_type == TILE_WATER: terrain_data['water'].append({'x': c_idx, 'y': r_idx})
        return terrain_data
    def is_npc_at(self.npc_ids)
    def get_tile_type(self, x, y):
        if 0 <= y < GRID_HEIGHT and 0 <= x < GRID_WIDTH: return self.terrain_grid[, x, y, exclude_id=None):
        if not self.game_manager_ref: returny][x]
        return None
    def set_tile_type(self, x, y, tile False
        for npc_id_in_scene in self.npc_ids:
            if exclude_id and npc_id_in_scene == exclude_id: continue
            npc = self.game_manager_ref_type):
        if 0 <= y < GRID_HEIGHT and 0 <= x < GRID_WIDTH: self.terrain_grid[y][x] = tile_type; return True
        return False
    def get_terrain.get_npc(npc_id_in_scene)
            if npc and npc.x == x and npc.y == y: return True
        return False
    def is_player_at(self, x_for_payload(self):
        terrain_data = {'walls': [], 'water': []}
        , y, player_id_to_check=None): 
        if not self.game_manager_for r_idx, row in enumerate(self.terrain_grid):
            for c_idx, tile_type in enumerate(row):
                if tile_type == TILE_WALL: terrain_data['walls'].ref: return False
        for player_sid_in_scene in self.players_sids:
            player = self.game_manager_ref.get_player(player_sid_in_scene)
            append({'x': c_idx, 'y': r_idx})
                elif tile_type == TILE_WATER: terrain_data['water'].append({'x': c_idx, 'y': r_idx})if player and player.x == x and player.y == y: return True
        return False

class GameManager
        return terrain_data
    def is_npc_at(self, x, y, exclude_id:
    def __init__(self, socketio_instance):
        self.players = {}; self.scenes=None):
        if not self.game_manager_ref: return False
        for npc_id_ = {}; self.npcs = {}
        self.queued_actions = {}; self.socketio = socketio_instance
        self.server_is_raining = SERVER_IS_RAINING
        self.ticks_until_mana_in_scene in self.npc_ids:
            if exclude_id and npc_id_in_scene == exclude_id: continue
            npc = self.game_manager_ref.get_npc(npc_regen = TICKS_PER_MANA_REGEN_CYCLE

    def spawn_initial_npcs(selfid_in_scene)
            if npc and npc.x == x and npc.y == y: return):
        scene_0_0 = self.get_or_create_scene(0,0)
 True
        return False
    def is_player_at(self, x, y, player_id_        for i in range(3): 
            px, py = random.randint(0, GRID_WIDTHto_check=None): 
        if not self.game_manager_ref: return False
        for-1), random.randint(0, GRID_HEIGHT-1)
            while scene_0_0.get_tile player_sid_in_scene in self.players_sids:
            player = self.game_manager_ref_type(px,py) == TILE_WALL or self.get_npc_at(px,py,0.get_player(player_sid_in_scene)
            if player and player.x == x and,0) is not None:
                 px, py = random.randint(0, GRID_WIDTH-1 player.y == y: return True
        return False

class GameManager:
    def __init__(self,), random.randint(0, GRID_HEIGHT-1)
            pixie = ManaPixie(0, socketio_instance):
        self.players = {}; self.scenes = {}; self.npcs = {}
         0, initial_x=px, initial_y=py)
            self.npcs[pixie.self.queued_actions = {}; self.socketio = socketio_instance
        self.server_is_id] = pixie; scene_0_0.add_npc(pixie.id)
            print(f"raining = SERVER_IS_RAINING
        self.ticks_until_mana_regen = TICKS_PER_MANA_REGEN_CYCLE

    def spawn_initial_npcs(self):
        scene_0Spawned pixie {pixie.name} at ({pixie.scene_x},{pixie.scene_y}) tile ({pixie.x},{pixie.y})")

    def setup_spawn_shrine(_0 = self.get_or_create_scene(0,0)
        for i in range(self, scene_obj):
        mid_x, mid_y = GRID_WIDTH // 2, GRID3): 
            px, py = random.randint(0, GRID_WIDTH-1), random.randint_HEIGHT // 2; shrine_size = 2 
        for i in range(-shrine_size, shrine_(0, GRID_HEIGHT-1)
            while scene_0_0.get_tile_type(pxsize + 1):
            scene_obj.set_tile_type(mid_x + i, mid,py) == TILE_WALL or self.get_npc_at(px,py,0,0) is_y - shrine_size, TILE_WALL) 
            scene_obj.set_tile_type not None:
                 px, py = random.randint(0, GRID_WIDTH-1), random.randint(mid_x + i, mid_y + shrine_size, TILE_WALL) 
            if(0, GRID_HEIGHT-1)
            pixie = ManaPixie(0, 0, initial_x=px, initial_y=py)
            self.npcs[pixie.id] = pixie abs(i) < shrine_size : 
                scene_obj.set_tile_type(mid_x - shrine_size, mid_y + i, TILE_WALL) 
                scene_obj.; scene_0_0.add_npc(pixie.id)
            print(f"Spawned pixie {set_tile_type(mid_x + shrine_size, mid_y + i, TILE_WALL) 
pixie.name} at ({pixie.scene_x},{pixie.scene_y}) tile ({pixie.        scene_obj.set_tile_type(mid_x, mid_y + shrine_size, Tx},{pixie.y})")

    def setup_spawn_shrine(self, scene_obj):
        ILE_FLOOR)
        scene_obj.set_tile_type(mid_x - (shrine_size + 2), mid_y, TILE_WATER)
        scene_obj.set_tilemid_x, mid_y = GRID_WIDTH // 2, GRID_HEIGHT // 2; shrine_size = 2 
        for i in range(-shrine_size, shrine_size + 1):_type(mid_x - (shrine_size + 2), mid_y + 1, TILE_WATER)
        scene_obj.set_tile_type(mid_x + (shrine_
            scene_obj.set_tile_type(mid_x + i, mid_y - shrine_size, TILE_WALL) 
            scene_obj.set_tile_type(mid_x +size + 2), mid_y -1, TILE_WATER)

    def get_or_create_scene(self, scene_x, scene_y):
        scene_coords = (scene_x, i, mid_y + shrine_size, TILE_WALL) 
            if abs(i) < shrine_size : 
                scene_obj.set_tile_type(mid_x - shrine_size, mid_y + i, TILE_WALL) 
                scene_obj.set_tile_type scene_y)
        if scene_coords not in self.scenes:
            new_scene = Scene(scene_x, scene_y); new_scene.game_manager_ref = self 
            if scene_x == 0 and scene_y == 0: self.setup_spawn_shrine(new_scene)
(mid_x + shrine_size, mid_y + i, TILE_WALL) 
        scene_obj.set_tile_type(mid_x, mid_y + shrine_size, TILE_FLOOR)
        scene_obj.set_tile_type(mid_x - (shrine_size            self.scenes[scene_coords] = new_scene
        return self.scenes[scene_coords]

 + 2), mid_y, TILE_WATER)
        scene_obj.set_tile_type    def add_player(self, sid):
        name = get_player_name(sid); player = Player(sid, name); self.players[sid] = player
        scene = self.get_or_create_scene(player.scene_x, player.scene_y); scene.add_player(sid)
        (mid_x - (shrine_size + 2), mid_y + 1, TILE_WATER)
        scene_obj.set_tile_type(mid_x + (shrine_size + 2), mid_y -1, TILE_WATER)

    def get_or_create_scenenew_player_public_data = player.get_public_data()
        for other_sid_in(self, scene_x, scene_y):
        scene_coords = (scene_x, scene__scene in scene.get_player_sids():
            if other_sid_in_scene != sid: self.socketio.emit('player_entered_your_scene', new_player_public_data,y)
        if scene_coords not in self.scenes:
            new_scene = Scene(scene_ room=other_sid_in_scene)
        return player

    def remove_player(self, sidx, scene_y); new_scene.game_manager_ref = self 
            if scene_x == 0 and scene_y == 0: self.setup_spawn_shrine(new_scene)):
        player = self.players.pop(sid, None)
        if sid in self.queued_
            self.scenes[scene_coords] = new_scene
        return self.scenes[scene_coordsactions: del self.queued_actions[sid]
        if player:
            old_scene_coords = (player.scene_x, player.scene_y)
            if old_scene_coords in self.]

    def add_player(self, sid):
        name = get_player_name(sid); player = Player(sid, name); self.players[sid] = player
        scene = self.get_or_createscenes:
                scene = self.scenes[old_scene_coords]; scene.remove_player(sid)
                for other_sid_in_scene in scene.get_player_sids(): self.socketio_scene(player.scene_x, player.scene_y); scene.add_player(sid)
.emit('player_exited_your_scene', {'id': sid, 'name': player.name}, room=other_sid_in_scene)
            return player
        return None

    def get_player        new_player_public_data = player.get_public_data()
        for other_sid_in_scene in scene.get_player_sids():
            if other_sid_in_scene !=(self, sid): return self.players.get(sid)
    def get_npc(self, npc_id): return self.npcs.get(npc_id)
    def get_npc_at(self sid: self.socketio.emit('player_entered_your_scene', new_player_public_data, room=other_sid_in_scene)
        return player

    def remove_player(self, sid):, x, y, scene_x, scene_y):
        for npc_id, npc_obj in self.npcs.items():
            if npc_obj.scene_x == scene_x and npc_obj
        player = self.players.pop(sid, None)
        if sid in self.queued_actions: del self.scene_y == scene_y and npc_obj.x == x and npc_obj.y == y:
.queued_actions[sid]
        if player:
            old_scene_coords = (player.scene_x, player.scene_y)
            if old_scene_coords in self.scenes:
                                return npc_obj
        return None
    def get_player_at(self, x, y,scene = self.scenes[old_scene_coords]; scene.remove_player(sid)
                for other_sid_in_scene in scene.get_player_sids(): self.socketio.emit('player scene_x, scene_y):
        for player_obj in self.players.values():
            if player_obj_exited_your_scene', {'id': sid, 'name': player.name}, room=other_.scene_x == scene_x and player_obj.scene_y == scene_y and player_objsid_in_scene)
            return player
        return None

    def get_player(self, sid.x == x and player_obj.y == y:
                return player_obj
        return None

    def handle_player_scene_change(self, player, old_scene_x, old_scene_): return self.players.get(sid)
    def get_npc(self, npc_id): return self.npcs.get(npc_id)
    def get_npc_at(self, x, yy):
        old_scene_coords = (old_scene_x, old_scene_y); new_scene_coords = (player.scene_x, player.scene_y)
        if old_scene, scene_x, scene_y):
        for npc_id, npc_obj in self.npcs.items():
_coords != new_scene_coords:
            if old_scene_coords in self.scenes:
                            if npc_obj.scene_x == scene_x and npc_obj.scene_y == scene_old_scene_obj = self.scenes[old_scene_coords]; old_scene_obj.remove_y and npc_obj.x == x and npc_obj.y == y:
                return npc_obj
        returnplayer(player.id)
                for other_sid in old_scene_obj.get_player_s None
    def get_player_at(self, x, y, scene_x, scene_y):ids(): self.socketio.emit('player_exited_your_scene', {'id': player.id, '
        for player_obj in self.players.values():
            if player_obj.scene_x == scene_xname': player.name}, room=other_sid)
            new_scene_obj = self.get_ and player_obj.scene_y == scene_y and player_obj.x == x and player_objor_create_scene(player.scene_x, player.scene_y); new_scene_obj..y == y:
                return player_obj
        return None

    def handle_player_scene_add_player(player.id)
            player_public_data_for_new_scene = player.get_public_data()
            for other_sid in new_scene_obj.get_player_schange(self, player, old_scene_x, old_scene_y):
        old_scene_coords = (old_scene_x, old_scene_y); new_scene_coords = (player.ids():
                if other_sid != player.id: self.socketio.emit('player_entered_your_scene', player_public_data_for_new_scene, room=other_sid)

    def is_scene_x, player.scene_y)
        if old_scene_coords != new_scene_coords:
            if old_scene_coords in self.scenes:
                old_scene_obj = self.player_visible_to_observer(self, obs_p, target_p):
        if not obs_scenes[old_scene_coords]; old_scene_obj.remove_player(player.id)
                p or not target_p: return False
        if obs_p.id == target_p.id: return False
for other_sid in old_scene_obj.get_player_sids(): self.socketio.emit('player        if obs_p.scene_x != target_p.scene_x or obs_p.scene__exited_your_scene', {'id': player.id, 'name': player.name}, room=y != target_p.scene_y: return False
        return abs(obs_p.x - targetother_sid)
            new_scene_obj = self.get_or_create_scene(player.scene_x, player.scene_y); new_scene_obj.add_player(player.id)_p.x) <= MAX_VIEW_DISTANCE and abs(obs_p.y - target_p.y) <= MAX_VIEW_DISTANCE
    
    def is_npc_visible_to_observer(self,
            player_public_data_for_new_scene = player.get_public_data()
             obs_p, target_npc):
        if not obs_p or not target_npc: return False
        if obsfor other_sid in new_scene_obj.get_player_sids():
                if other_sid_p.scene_x != target_npc.scene_x or obs_p.scene_y != target != player.id: self.socketio.emit('player_entered_your_scene', player_public__npc.scene_y: return False
        return abs(obs_p.x - target_npc.data_for_new_scene, room=other_sid)

    def is_player_visible_to_observer(self, obs_p, target_p):
        if not obs_p or not target_p: return Falsex) <= MAX_VIEW_DISTANCE and abs(obs_p.y - target_npc.y) <= MAX_VIEW_DISTANCE

    def get_visible_players_for_observer(self, observer_player):
        if obs_p.id == target_p.id: return False
        if obs_p.scene_x != target_p.scene_x or obs_p.scene_y != target_p.
        visible_others = []
        scene = self.get_or_create_scene(observer_player.scene_x, observer_player.scene_y)
        for target_sid in scene.get_playerscene_y: return False
        return abs(obs_p.x - target_p.x) <= MAX_VIEW_DISTANCE and abs(obs_p.y - target_p.y) <= MAX_VIEW_DISTANCE
_sids():
            if target_sid == observer_player.id: continue
            target_player = self.get_player(target_sid)
            if target_player and self.is_player_visible    
    def is_npc_visible_to_observer(self, obs_p, target_npc):
        if_to_observer(observer_player, target_player):
                visible_others.append(target_player not obs_p or not target_npc: return False
        if obs_p.scene_x != target.get_public_data())
        return visible_others

    def get_visible_npcs_for__npc.scene_x or obs_p.scene_y != target_npc.scene_y: returnobserver(self, observer_player):
        visible_npcs_data = []
        scene = self.get_or_ False
        return abs(obs_p.x - target_npc.x) <= MAX_VIEW_DISTANCEcreate_scene(observer_player.scene_x, observer_player.scene_y)
        for npc and abs(obs_p.y - target_npc.y) <= MAX_VIEW_DISTANCE

    def_id in scene.get_npc_ids():
            npc = self.get_npc(npc_id get_visible_players_for_observer(self, observer_player):
        visible_others = []
)
            if npc and self.is_npc_visible_to_observer(observer_player, npc):
                   visible        scene = self.get_or_create_scene(observer_player.scene_x, observer_player_npcs_data.append(npc.get_public_data())
        return visible_npcs_data
.scene_y)
        for target_sid in scene.get_player_sids():
            if target    
    def get_target_coordinates(self, player, dx, dy): return player.x + dx_sid == observer_player.id: continue
            target_player = self.get_player(target_sid)
            if target_player and self.is_player_visible_to_observer(observer_player, player.y + dy

    def get_general_direction(self, observer, target):
        dx = target.x - observer.x; dy = target.y - observer.y
        if abs(dx, target_player):
                visible_others.append(target_player.get_public_data())
) > abs(dy): return "to the east" if dx > 0 else "to the west"
        return visible_others

    def get_visible_npcs_for_observer(self, observer_player):        elif abs(dy) > abs(dx): return "to the south" if dy > 0 else "
        visible_npcs_data = []
        scene = self.get_or_create_scene(observer_player.scene_x, observer_player.scene_y)
        for npc_id in scene.get_npcto the north"
        else: # Diagonal or same spot
            if dx > 0 and dy > 0: return "to the southeast"
            elif dx > 0 and dy < 0: return "to the northeast_ids():
            npc = self.get_npc(npc_id)
            if npc and self.is_npc"
            elif dx < 0 and dy > 0: return "to the southwest"
            elif dx_visible_to_observer(observer_player, npc):
                   visible_npcs_data.append(npc.get_public_data())
        return visible_npcs_data
    
    def get_target_ < 0 and dy < 0: return "to the northwest"
            else: return "nearby"


    def process_sensory_perception(self, player, scene):
        perceived_cues_this_tickcoordinates(self, player, dx, dy): return player.x + dx, player.y + dy

    def get_general_direction(self, observer, target):
        dx = target.x - observer.x = set() 
        for npc_id in scene.get_npc_ids():
            npc = self; dy = target.y - observer.y
        if abs(dx) > abs(dy): return ".get_npc(npc_id)
            if not npc or npc.is_hidden: continue

            is_visibleto the east" if dx > 0 else "to the west"
        elif abs(dy) > abs(_flag = self.is_npc_visible_to_observer(player, npc)
            distance = abs(playerdx): return "to the south" if dy > 0 else "to the north"
        else: #.x - npc.x) + abs(player.y - npc.y)

            if is_visible_flag:
                for cue_key, relevance, _ in npc.sensory_cues.get('sight', []):
                    if random.random() < (relevance * 0.15) and cue_ Diagonal or same spot (though distance check should prevent same spot for non-visual)
            if dx > 0 andkey not in perceived_cues_this_tick: # Low chance for passive "noticing"
                        self.socketio dy > 0: return "to the southeast"
            elif dx < 0 and dy > 0:.emit('lore_message', {'messageKey': cue_key, 'placeholders': {'npcName': npc return "to the southwest"
            elif dx > 0 and dy < 0: return "to the northeast.name}, 'type': 'sensory-sight'}, room=player.id)
                        perceived_c"
            elif dx < 0 and dy < 0: return "to the northwest"
            return "nearby" # Fallback

    def process_sensory_perception(self, player, scene):
        perues_this_tick.add(cue_key)
                        break 
            else: 
                forceived_cues_this_tick = set() 
        for npc_id in scene.get_npc sense_type in ['sound', 'smell', 'magic']:
                    for cue_key, relevance, cue_range in npc.sensory_cues.get(sense_type, []):
                        if distance <= cue_range_ids():
            npc = self.get_npc(npc_id)
            if not npc or npc.is_hidden: continue

            is_visible_flag = self.is_npc_visible_to_observer:
                            perception_chance = relevance * (1 - (distance / (cue_range + 1))) * 0.(player, npc)
            distance = abs(player.x - npc.x) + abs(player.6 
                            if random.random() < perception_chance and cue_key not in perceived_cues_this_tick:
                                self.socketio.emit('lore_message', 
                                                   {'messageKey': cuey - npc.y)

            if is_visible_flag:
                for cue_key, relevance, _ in npc.sensory_cues.get('sight', []):
                    if random.random() <_key, 
                                                    'placeholders': {'npcName': npc.name, 'direction': self.get_general_direction(player, npc)}, 
                                                    'type': f'sensory-{sense_type}'}, (relevance * 0.15) and cue_key not in perceived_cues_this_tick:
                        self.socketio.emit('lore_message', {'messageKey': cue_key, 'place 
                                                   room=player.id)
                                perceived_cues_this_tick.add(cue_key)
                                break 
                        if cue_key in perceived_cues_this_tick: breakholders': {'npcName': npc.name}, 'type': 'sensory-sight'}, room=player.id)
                        perceived_cues_this_tick.add(cue_key)
                        break 
            else 

    def process_actions(self):
        current_actions_to_process = dict(self.: 
                for sense_type in ['sound', 'smell', 'magic']:
                    for cue_queued_actions); self.queued_actions.clear(); processed_sids = set()
        for sid_action, action_data in current_actions_to_process.items():
            if sid_action in processed_sids : continue
            player = self.get_player(sid_action);
            if not playerkey, relevance, cue_range in npc.sensory_cues.get(sense_type, []):
                        if distance <= cue_range:
                            perception_chance = relevance * (1 - (distance / (cue_range: continue
            action_type = action_data.get('type'); details = action_data.get(' + 1))) * 0.6 
                            if random.random() < perception_chance and cue_key not in perceived_cues_this_tick:
                                self.socketio.emit('lore_message', details', {})

            if action_type == 'move' or action_type == 'look':
                dx, dy = details.get('dx', 0), details.get('dy', 0)
                new
                                                   {'messageKey': cue_key, 
                                                    'placeholders': {'npcName': npc.name, 'direction': self.get_general_direction(player, npc)}, 
                                                    'type': f'_char_for_player = details.get('newChar', player.char)
                
                if action_type == 'move' and (dx != 0 or dy != 0):
                    target_x,sensory-{sense_type}'}, 
                                                   room=player.id)
                                perceived_cues target_y = player.x + dx, player.y + dy
                    scene_of_player = self_this_tick.add(cue_key)
                                break 
                        if cue_key in perceived_cues_.get_or_create_scene(player.scene_x, player.scene_y)
                    can_move_to_tile = True
                    if 0 <= target_x < GRID_WIDTH and 0this_tick: break 

    def process_actions(self):
        current_actions_to_process = dict(self.queued_actions); self.queued_actions.clear(); processed_sids = set()
        for sid_action, action_data in current_actions_to_process.items():
            if sid_ <= target_y < GRID_HEIGHT:
                        tile_type_at_target = scene_of_player.get_tile_type(target_x, target_y)
                        npc_at_target = selfaction in processed_sids : continue
            player = self.get_player(sid_action);
            .get_npc_at(target_x, target_y, player.scene_x, player.sceneif not player: continue
            action_type = action_data.get('type'); details = action_data_y)

                        if tile_type_at_target == TILE_WALL: self.socketio.emit('lore_message', {'messageKey': 'LORE.ACTION_BLOCKED_WALL', 'type':.get('details', {})

            if action_type == 'move' or action_type == 'look':
                dx, dy = details.get('dx', 0), details.get('dy', 0)
                new 'event-bad'}, room=player.id); can_move_to_tile = False
                        elif npc_char_for_player = details.get('newChar', player.char)
                
                if action_at_target and isinstance(npc_at_target, ManaPixie):
                            if npc_at_target.attempt_evade(player.x, player.y, scene_of_player): self.socketio_type == 'move' and (dx != 0 or dy != 0):
                    target_x,.emit('lore_message', {'messageKey': 'LORE.PIXIE_MOVED_AWAY target_y = player.x + dx, player.y + dy
                    scene_of_player = self.get_or_create_scene(player.scene_x, player.scene_y)
                    can', 'type': 'system', 'placeholders':{'pixieName': npc_at_target.name}}, room_move_to_tile = True
                    if 0 <= target_x < GRID_WIDTH and 0=player.id)
                            else: self.socketio.emit('lore_message', {'messageKey': 'LORE <= target_y < GRID_HEIGHT:
                        tile_type_at_target = scene_of_player.PIXIE_BLOCKED_PATH', 'type': 'event-bad', 'placeholders':{'pix.get_tile_type(target_x, target_y)
                        npc_at_target = selfieName': npc_at_target.name}}, room=player.id); can_move_to_tile.get_npc_at(target_x, target_y, player.scene_x, player.scene = False
                        elif tile_type_at_target == TILE_WATER: player.set_wet_status(True_y)

                        if tile_type_at_target == TILE_WALL: self.socketio.emit('lore_message', {'messageKey': 'LORE.ACTION_BLOCKED_WALL', 'type':, self.socketio, reason="water_tile")
                    
                    if can_move_to_tile: player.update_position(dx, dy, new_char_for_player, self, self.socket 'event-bad'}, room=player.id); can_move_to_tile = False
                        elif npcio)
                    elif player.char != new_char_for_player : player.char = new_char_at_target and isinstance(npc_at_target, ManaPixie):
                            if npc_at_target.attempt_evade(player.x, player.y, scene_of_player): self.socketio_for_player 
                else: 
                    player.update_position(dx, dy, new_char.emit('lore_message', {'messageKey': 'LORE.PIXIE_MOVED_AWAY_for_player, self, self.socketio)
                    if action_type == 'look': 
                        scene_of_player = self.get_or_create_scene(player.scene_x, player.scene_', 'type': 'system', 'placeholders':{'pixieName': npc_at_target.name}}, roomy)
                        self.process_sensory_perception(player, scene_of_player) 

            elif=player.id)
                            else: self.socketio.emit('lore_message', {'messageKey': 'LORE.PIXIE_BLOCKED_PATH', 'type': 'event-bad', 'placeholders':{' action_type == 'build_wall':
                dx, dy = details.get('dx', 0), details.get('dy', 0); target_x, target_y = self.get_target_coordinatespixieName': npc_at_target.name}}, room=player.id); can_move_to_(player, dx, dy)
                scene = self.get_or_create_scene(player.scene_x, player.scene_y)
                if not (0 <= target_x < GRID_WIDTH andtile = False
                        elif tile_type_at_target == TILE_WATER: player.set_wet_status(True, self.socketio, reason="water_tile")
                    
                    if can_move_to_ 0 <= target_y < GRID_HEIGHT): self.socketio.emit('lore_message', {'messagetile: player.update_position(dx, dy, new_char_for_player, self, self.Key': 'LORE.BUILD_FAIL_OUT_OF_BOUNDS', 'type': 'event-badsocketio)
                    elif player.char != new_char_for_player : player.char = new_'}, room=player.id)
                elif scene.get_tile_type(target_x, target_y) !=char_for_player
                else: 
                    player.update_position(dx, dy, new_char_ TILE_FLOOR: self.socketio.emit('lore_message', {'messageKey': 'LOREfor_player, self, self.socketio)
                    if action_type == 'look': 
                        scene_of_player = self.get_or_create_scene(player.scene_x, player..BUILD_FAIL_OBSTRUCTED', 'type': 'event-bad'}, room=player.id)
                elif self.get_npc_at(target_x, target_y, player.scene_x,scene_y)
                        self.process_sensory_perception(player, scene_of_player)

 player.scene_y) or self.get_player_at(target_x, target_y, player            elif action_type == 'build_wall':
                dx, dy = details.get('dx', 0), details.get('dy', 0); target_x, target_y = self.get_target.scene_x, player.scene_y): self.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_FAIL_OBSTRUCTED', 'type': 'event-bad'}, room=player.id)
                elif not player.has_wall_items(): self.socketio.emit('lore_coordinates(player, dx, dy)
                scene = self.get_or_create_scene(player.scene_x, player.scene_y)
                if not (0 <= target_x < GRID__message', {'messageKey': 'LORE.BUILD_FAIL_NO_MATERIALS', 'type': 'eventWIDTH and 0 <= target_y < GRID_HEIGHT): self.socketio.emit('lore_message',-bad'}, room=player.id)
                else: player.use_wall_item(); scene.set_tile {'messageKey': 'LORE.BUILD_FAIL_OUT_OF_BOUNDS', 'type': 'event-bad'}, room=player.id)
                elif scene.get_tile_type(target_x, target_type(target_x, target_y, TILE_WALL); self.socketio.emit('lore_y) != TILE_FLOOR: self.socketio.emit('lore_message', {'messageKey_message', {'messageKey': 'LORE.BUILD_SUCCESS', 'placeholders': {'walls': player.': 'LORE.BUILD_FAIL_OBSTRUCTED', 'type': 'event-bad'}, room=playerwalls}, 'type': 'event-good'}, room=player.id)
            
            elif action_type == 'destroy_wall':
                dx, dy = details.get('dx', 0), details.get.id)
                elif self.get_npc_at(target_x, target_y, player.('dy', 0); target_x, target_y = self.get_target_coordinates(player,scene_x, player.scene_y) or self.get_player_at(target_x, target_y, player.scene_x, player.scene_y): self.socketio.emit('lore_ dx, dy)
                scene = self.get_or_create_scene(player.scene_x, player.scene_y)
                if not (0 <= target_x < GRID_WIDTH and 0 <= target_y < GRID_HEIGHT): self.socketio.emit('lore_message', {'messageKey': 'message', {'messageKey': 'LORE.BUILD_FAIL_OBSTRUCTED', 'type': 'event-LORE.DESTROY_FAIL_OUT_OF_BOUNDS', 'type': 'event-bad'}, room=bad'}, room=player.id)
                elif not player.has_wall_items(): self.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_FAIL_NO_MATERIALS', 'type': 'event-bad'}, room=player.id)
                else: player.use_wall_itemplayer.id)
                elif scene.get_tile_type(target_x, target_y) != TILE_WALL: self.socketio.emit('lore_message', {'messageKey': 'LORE.DESTROY_FAIL_NO_WALL', 'type': 'event-bad'}, room=player.id)
                elif not(); scene.set_tile_type(target_x, target_y, TILE_WALL); self.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_SUCCESS', 'placeholders': {' player.can_afford_mana(DESTROY_WALL_MANA_COST): self.socketio.emit('lorewalls': player.walls}, 'type': 'event-good'}, room=player.id)
            
            _message', {'messageKey': 'LORE.DESTROY_FAIL_NO_MANA', 'placeholders':elif action_type == 'destroy_wall':
                dx, dy = details.get('dx', 0), details.get('dy', 0); target_x, target_y = self.get_target_ {'manaCost': DESTROY_WALL_MANA_COST}, 'type': 'event-bad'}, room=player.id)
                else: player.spend_mana(DESTROY_WALL_MANA_COST); playercoordinates(player, dx, dy)
                scene = self.get_or_create_scene(player.scene_x, player.scene_y)
                if not (0 <= target_x < GRID_WIDTH.add_wall_item(); scene.set_tile_type(target_x, target_y, TILE_FLOOR); self.socketio.emit('lore_message', {'messageKey': 'LORE.DESTROY_SUCCESS', 'placeholders': {'walls': player.walls, 'manaCost': DESTROY_WALL_ and 0 <= target_y < GRID_HEIGHT): self.socketio.emit('lore_message', {'messageKey': 'LORE.DESTROY_FAIL_OUT_OF_BOUNDS', 'type': 'event-MANA_COST}, 'type': 'event-good'}, room=player.id)
            
            elifbad'}, room=player.id)
                elif scene.get_tile_type(target_x, target action_type == 'drink_potion': player.drink_potion(self.socketio)
            
            _y) != TILE_WALL: self.socketio.emit('lore_message', {'messageKey': 'Lelif action_type == 'say':
                message_text = details.get('message', '')
                ifORE.DESTROY_FAIL_NO_WALL', 'type': 'event-bad'}, room=player.id) message_text: 
                    chat_data = { 'sender_id': player.id, 'sender_name': player
                elif not player.can_afford_mana(DESTROY_WALL_MANA_COST): self.socketio.name, 'message': message_text, 'type': 'say', 'scene_coords': f"({.emit('lore_message', {'messageKey': 'LORE.DESTROY_FAIL_NO_MANA',player.scene_x},{player.scene_y})" }
                    player_scene_coords = (player.scene_ 'placeholders': {'manaCost': DESTROY_WALL_MANA_COST}, 'type': 'event-bad'}, room=player.id)
                else: player.spend_mana(DESTROY_WALL_MANAx, player.scene_y)
                    if player_scene_coords in self.scenes: 
                        scene = self.scenes[player_scene_coords] 
                        for target_sid in scene.get_player_sids():_COST); player.add_wall_item(); scene.set_tile_type(target_x, target_y, TILE_FLOOR); self.socketio.emit('lore_message', {'messageKey': self.socketio.emit('chat_message', chat_data, room=target_sid)
            
            elif action_type == 'shout':
                message_text = details.get('message', '')
 'LORE.DESTROY_SUCCESS', 'placeholders': {'walls': player.walls, 'manaCost': DESTROY_WALL_MANA_COST}, 'type': 'event-good'}, room=player.id)
            
                            if message_text:
                    if player.spend_mana(SHOUT_MANA_COST):
                        chat_data = { 
                            'sender_id': player.id, 
                            'sender_elif action_type == 'drink_potion': player.drink_potion(self.socketio)
            
name': player.name, 
                            'message': message_text, 
                            'type': 'sh            elif action_type == 'say':
                message_text = details.get('message', '')
                out', 
                            'scene_coords': f"({player.scene_x},{player.scene_yif message_text: 
                    chat_data = { 'sender_id': player.id, 'sender_name': player.name, 'message': message_text, 'type': 'say', 'scene_coords})" 
                        }
                        for target_player_obj in list(self.players.values()):
                            if abs(target_player_obj.scene_x - player.scene_x) <= 1 and \
                               ': f"({player.scene_x},{player.scene_y})" }
                    player_scene_coordsabs(target_player_obj.scene_y - player.scene_y) <= 1:
                                = (player.scene_x, player.scene_y)
                    if player_scene_coords in self.scenes self.socketio.emit('chat_message', chat_data, room=target_player_obj.id: 
                        scene = self.scenes[player_scene_coords] 
                        for target_sid in scene.)
                        
                        self.socketio.emit('lore_message', {
                            'messageKey': 'get_player_sids(): self.socketio.emit('chat_message', chat_data, room=target_sid)
            
            elif action_type == 'shout':
                message_text = detailsLORE.VOICE_BOOM_SHOUT', 
                            'placeholders': {'manaCost': SHOUT_MANA_COST}, 
                            'type': 'system',
                            'message': f"Your voice booms, costing {SH.get('message', '')
                if message_text:
                    if player.spend_mana(SHOUT_MANAOUT_MANA_COST} mana!"
                        }, room=player.id)
                    else:
                        self_COST):
                        chat_data = { 
                            'sender_id': player.id, 
                            'sender_name': player.name, 
                            'message': message_text, 
                            '.socketio.emit('lore_message', {
                            'messageKey': 'LORE.LACK_type': 'shout', 
                            'scene_coords': f"({player.scene_x},{playerMANA_SHOUT', 
                            'placeholders': {'manaCost': SHOUT_MANA_COST.scene_y})" 
                        }
                        for target_player_obj in list(self.players.values()):}, 
                            'type': 'event-bad',
                            'message': f"You need {SHOUT_MANA_COST} mana to shout."
                        }, room=player.id)
            processed_s
                            if abs(target_player_obj.scene_x - player.scene_x) <= 1ids.add(sid_action)


# --- App Setup & SocketIO ---
app = Flask(__name__) and \
                               abs(target_player_obj.scene_y - player.scene_y) <= 1:
                                self.socketio.emit('chat_message', chat_data, room=target_player
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev_security_key')
GAME_PATH_PREFIX = '/world-of-the-wand'
s_obj.id)
                        
                        self.socketio.emit('lore_message', {
                            'io = SocketIO(logger=True, engineio_logger=True, async_mode="eventlet")
messageKey': 'LORE.VOICE_BOOM_SHOUT', 
                            'placeholders': {'manaCost': SHOUT_MANA_COST}, 
                            'type': 'system',
                            'messagegame_manager = GameManager(socketio_instance=sio)
sio.init_app(app, path=f"{GAME_PATH_PREFIX}/socket.io")
game_blueprint = Blueprint('game', __name__, template': f"Your voice booms, costing {SHOUT_MANA_COST} mana!"
                        }, room=_folder='templates', static_folder='static', static_url_path='/static/game')
@game_blueprint.route('/')
def index_route(): return render_template('index.html')
app.registerplayer.id)
                    else: # This else corresponds to: if not player.spend_mana(SHOUT_MANA_COST)
                        self.socketio.emit('lore_message', {
                            'messageKey':_blueprint(game_blueprint, url_prefix=GAME_PATH_PREFIX)
@app.route('/')
 'LORE.LACK_MANA_SHOUT', 
                            'placeholders': {'manaCost':def health_check_route(): return "OK", 200

# --- Game Loop ---
def game SHOUT_MANA_COST}, 
                            'type': 'event-bad',
                            'message':_loop():
    my_pid = os.getpid()
    print(f">>>> [{my_pid}] game_loop THREAD ENTERED (Tick rate: {GAME_TICK_RATE}s) <<<<")
 f"You need {SHOUT_MANA_COST} mana to shout."
                        }, room=player.id)
            processed_sids.add(sid_action)


# --- App Setup & SocketIO ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FL    game_manager.spawn_initial_npcs()
    loop_count = 0
    try:
        while True:
            loop_start_time = time.time()
            loop_count += 1ASK_SECRET_KEY', 'dev_security_key')
GAME_PATH_PREFIX = '/world-of
            game_manager.ticks_until_mana_regen -=1

            if loop_count % 20 == -the-wand'
sio = SocketIO(logger=True, engineio_logger=True, async1:
                 print(f"---- [{my_pid}] Tick {loop_count} ---- Players: {_mode="eventlet")
game_manager = GameManager(socketio_instance=sio)
sio.init_app(app, path=f"{GAME_PATH_PREFIX}/socket.io")
game_blueprint = Blueprintlen(game_manager.players)} NPCs: {len(game_manager.npcs)} Actions: {len(game_manager.queued_actions)} Rain: {game_manager.server_is_raining} ----")

('game', __name__, template_folder='templates', static_folder='static', static_url_path='/static/game            for npc in list(game_manager.npcs.values()):
                if isinstance(npc, ManaPixie):
                    scene_of_npc = game_manager.get_or_create_scene(npc.scene_x')
@game_blueprint.route('/')
def index_route(): return render_template('index.html')
app.register_blueprint(game_blueprint, url_prefix=GAME_PATH_PREFIX)
@app.route('/')
def health_check_route(): return "OK", 200

# --- Game Loop, npc.scene_y)
                    npc.wander(scene_of_npc)
            
            game_manager.process_actions()

            if game_manager.ticks_until_mana_regen <= 0:
                 ---
def game_loop():
    my_pid = os.getpid()
    print(f">>>> [{my_pid}] game_loop THREAD ENTERED (Tick rate: {GAME_TICK_RATEfor player_obj in list(game_manager.players.values()):
                    pixie_boost_for_player = 0
                    player_scene_obj = game_manager.get_or_create_scene(player_obj}s) <<<<")
    game_manager.spawn_initial_npcs()
    loop_count = 0
    try:
        while True:
            loop_start_time = time.time()
.scene_x, player_obj.scene_y)
                    for npc_id in player_scene_            loop_count += 1
            game_manager.ticks_until_mana_regen -=1

            if loopobj.get_npc_ids():
                        npc = game_manager.get_npc(npc_id)
                        if npc and isinstance(npc, ManaPixie):
                            dist = abs(player_obj.x_count % 20 == 1:
                 print(f"---- [{my_pid}] Tick {loop_count} ---- Players: {len(game_manager.players)} NPCs: {len(game_manager - npc.x) + abs(player_obj.y - npc.y)
                            if dist <= PI.npcs)} Actions: {len(game_manager.queued_actions)} Rain: {game_manager.serverXIE_PROXIMITY_FOR_BOOST: pixie_boost_for_player += PIXIE_MANA_REGEN_BOOST
                    player_obj.regenerate_mana(BASE_MANA_is_raining} ----")

            for npc in list(game_manager.npcs.values()):
                _REGEN_PER_TICK, pixie_boost_for_player, sio)
                game_manager.ticksif isinstance(npc, ManaPixie):
                    scene_of_npc = game_manager.get_or_create_until_mana_regen = TICKS_PER_MANA_REGEN_CYCLE

            if game__scene(npc.scene_x, npc.scene_y)
                    npc.wander(scene_ofmanager.server_is_raining:
                for player_obj in list(game_manager.players.values_npc)
            
            game_manager.process_actions()

            if game_manager.ticks_until_mana_regen <= 0:
                for player_obj in list(game_manager.players.values()):
()): 
                    player_scene = game_manager.get_or_create_scene(player_obj.scene_                    pixie_boost_for_player = 0
                    player_scene_obj = game_manager.get_orx, player_obj.scene_y)
                    if not player_scene.is_indoors: 
                        if not player_obj.is_wet: player_obj.set_wet_status(True, sio, reason="rain")
            
            if loop_count % 5 == 0: 
                for player_obj in list_create_scene(player_obj.scene_x, player_obj.scene_y)
                    for npc_id in player_scene_obj.get_npc_ids():
                        npc = game_manager.get_npc(npc_id)
                        if npc and isinstance(npc, ManaPixie):
                            dist(game_manager.players.values()):
                    scene_of_player = game_manager.get_or_create_scene(player_obj.scene_x, player_obj.scene_y)
                    game_manager = abs(player_obj.x - npc.x) + abs(player_obj.y - npc..process_sensory_perception(player_obj, scene_of_player)

            if game_managery)
                            if dist <= PIXIE_PROXIMITY_FOR_BOOST: pixie_boost_for.players:
                current_players_snapshot = list(game_manager.players.values())
                num_player += PIXIE_MANA_REGEN_BOOST
                    player_obj.regenerate_mana(BASE_MANA_REGEN_PER_TICK, pixie_boost_for_player, sio_updates_sent_successfully = 0
                for recipient_player in current_players_snapshot:
                    )
                game_manager.ticks_until_mana_regen = TICKS_PER_MANA_REif recipient_player.id not in game_manager.players: continue
                    self_data_payload = recipient_player.get_full_data()
                    visible_others_payload = game_manager.get_visibleGEN_CYCLE

            if game_manager.server_is_raining:
                for player_obj in list(game_manager.players.values()): 
                    player_scene = game_manager.get_or_create__players_for_observer(recipient_player)
                    visible_npcs_payload = game_manager.get_visible_npcs_for_observer(recipient_player)
                    current_scene_obj = game_manager.get_or_create_scene(recipient_player.scene_x, recipient_player.scene_y)
scene(player_obj.scene_x, player_obj.scene_y)
                    if not player_scene.is_indoors: 
                        if not player_obj.is_wet: player_obj.set_wet_status(True, sio, reason="rain")
            
            if loop_count % 5 ==                     visible_terrain_payload = current_scene_obj.get_terrain_for_payload() 
                    payload_for_client = {
                        'self_player_data': self_data_payload,
                        0: 
                for player_obj in list(game_manager.players.values()):
                    scene_of_player = game_manager.get_or_create_scene(player_obj.scene_x, player_obj'visible_other_players': visible_others_payload,
                        'visible_npcs': visible_npcs_payload,
                        'visible_terrain': visible_terrain_payload, 
                    }
                    try: sio.scene_y)
                    game_manager.process_sensory_perception(player_obj, scene_.emit('game_update', payload_for_client, room=recipient_player.id); num_updates_sentof_player)


            if game_manager.players:
                current_players_snapshot = list(game_manager.players.values())
                num_updates_sent_successfully = 0
                for recipient_player_successfully +=1
                    except Exception as e_emit: print(f"!!! [{my_pid}] Tick {loop_count}: ERROR during sio.emit for SID {recipient_player.id}: {e_emit}"); in current_players_snapshot:
                    if recipient_player.id not in game_manager.players: continue
                    self_data_payload = recipient_player.get_full_data()
                    visible_others_ traceback.print_exc()
                if num_updates_sent_successfully > 0 and loop_count %payload = game_manager.get_visible_players_for_observer(recipient_player)
                    visible_ 10 == 1: print(f"[{my_pid}] Tick {loop_count}: Completed sending 'game_update' to {num_updates_sent_successfully} players.")
            
            elapsed_timenpcs_payload = game_manager.get_visible_npcs_for_observer(recipient_player)
                    current_scene_obj = game_manager.get_or_create_scene(recipient_player.scene_ = time.time() - loop_start_time
            sleep_duration = GAME_TICK_RATE - elapsed_time
            if sleep_duration > 0: sio.sleep(sleep_duration)
            elif sleep_x, recipient_player.scene_y)
                    visible_terrain_payload = current_scene_obj.get_terrain_for_payload() 
                    payload_for_client = {
                        'self_player_data':duration < -0.05: print(f"!!! [{my_pid}] GAME LOOP OVERRUN: Tick {loop_count} took {elapsed_time:.4f}s (ran over by {-sleep_duration:.4f}s).")
    except Exception as e_loop: print(f"!!!!!!!! [{my_pid self_data_payload,
                        'visible_other_players': visible_others_payload,
                        'visible_npcs': visible_npcs_payload,
                        'visible_terrain': visible_terrain_payload, 
                    }
                    try: sio.emit('game_update', payload_for_client, room=recipient}] FATAL ERROR IN GAME_LOOP (PID: {my_pid}): {e_loop} !!!!!!!!!"); traceback.print_exc()

# --- SocketIO Event Handlers ---
@sio.on('connect')
def handle_connect_event(auth=None):
    sid, pid = request.sid, os._player.id); num_updates_sent_successfully +=1
                    except Exception as e_emit: print(f"!!! [{my_pid}] Tick {loop_count}: ERROR during sio.emit for SID {recipient_playergetpid()
    player = game_manager.add_player(sid)
    player_full_data.id}: {e_emit}"); traceback.print_exc()
                if num_updates_sent_successfully = player.get_full_data()
    visible_to_new_player = game_manager.get > 0 and loop_count % 10 == 1: print(f"[{my_pid}]_visible_players_for_observer(player)
    visible_npcs_to_new_player = game_manager Tick {loop_count}: Completed sending 'game_update' to {num_updates_sent_successfully} players.get_visible_npcs_for_observer(player)
    
    emit_ctx('initial_game.")
            
            elapsed_time = time.time() - loop_start_time
            sleep_duration_data', {
        'player_data': player_full_data,
        'other_players_in_scene': visible_to_new_player,
        'visible_npcs': visible_npcs_to = GAME_TICK_RATE - elapsed_time
            if sleep_duration > 0: sio.sleep(sleep_duration)
            elif sleep_duration < -0.05: print(f"!!! [{my__new_player,
        'grid_width': GRID_WIDTH, 'grid_height': GRID_HEIGHT, 'tick_rate': GAME_TICK_RATE,
        'default_rain_intensity': DEFAULT_pid}] GAME LOOP OVERRUN: Tick {loop_count} took {elapsed_time:.4f}s (ran over by {-sleep_duration:.4f}s).")
    except Exception as e_loop: print(f"!!!!!!!! [{my_pid}] FATAL ERROR IN GAME_LOOP (PID: {my_pid}):RAIN_INTENSITY 
    })
    emit_ctx('lore_message', {'messageKey': "LORE.WELCOME_INITIAL", 'type': 'welcome-message'}, room=sid)
    print(f"[{pid}] Connect: { {e_loop} !!!!!!!!!"); traceback.print_exc()

# --- SocketIO Event Handlers ---
@sio.on('connect')
def handle_connect_event(auth=None):
    sid,player.name} ({sid}). Players: {len(game_manager.players)}")


@sio.on('disconnect')
def handle_disconnect_event():
    sid, pid = request.sid, os.getpid()
 pid = request.sid, os.getpid()
    player = game_manager.add_player(sid)
    player_full_data = player.get_full_data()
    visible_to_new_player = game_manager.get_visible_players_for_observer(player)
    visible_npcs    player_left = game_manager.remove_player(sid)
    if player_left: print(f"[{pid}] Disconnect: {player_left.name} ({sid}). Players: {len(game_manager.players)}")
    else: print(f"[{pid}] Disconnect for SID {sid} (player not found_to_new_player = game_manager.get_visible_npcs_for_observer(player)
    
    emit_ctx('initial_game_data', {
        'player_data': player_full_data or already removed by GameManager).")

@sio.on('queue_player_action')
def handle_,
        'other_players_in_scene': visible_to_new_player,
        'visible_npcs': visible_npcs_to_new_player,
        'grid_width': GRID_WIDTH,queue_player_action(data):
    sid, pid = request.sid, os.getpid()
    player = game_manager.get_player(sid)
    if not player: emit_ctx('action 'grid_height': GRID_HEIGHT, 'tick_rate': GAME_TICK_RATE,
        'default_rain_intensity': DEFAULT_RAIN_INTENSITY 
    })
    emit_ctx('lore_message_feedback', {'success': False, 'message': "Player not recognized."}); return
    action_type = data.get('type')
    valid_actions = ['move', 'look', 'drink_potion', 'say', 'shout', 'build_wall', 'destroy_wall']
    if action_type not in valid_actions', {'messageKey': "LORE.WELCOME_INITIAL", 'type': 'welcome-message'}, room=sid)
: emit_ctx('action_feedback', {'success': False, 'messageKey': 'ACTION_SENT_FEEDBACK.ACTION    print(f"[{pid}] Connect: {player.name} ({sid}). Players: {len(game_manager.players)}")

@sio.on('disconnect')
def handle_disconnect_event():
    sid, pid = request._FAILED_UNKNOWN_COMMAND', 'placeholders': {'actionWord': action_type}}); return
    game_manager.queuedsid, os.getpid()
    player_left = game_manager.remove_player(sid)
_actions[sid] = data
    emit_ctx('action_feedback', {'success': True, 'messageKey': 'ACTION_SENT_FEEDBACK.ACTION_QUEUED'})

def start_game_loop_for    if player_left: print(f"[{pid}] Disconnect: {player_left.name} ({_worker():
    global _game_loop_started_in_this_process
    my_pid =sid}). Players: {len(game_manager.players)}")
    else: print(f"[{pid}] os.getpid()
    if not _game_loop_started_in_this_process:
         Disconnect for SID {sid} (player not found or already removed by GameManager).")

@sio.on('queue_print(f"[{my_pid}] Worker: Attempting to start game_loop task...")
        try:
            player_action')
def handle_queue_player_action(data):
    sid, pid = request.sid, os.getpid()
    player = game_manager.get_player(sid)
    ifsio.start_background_task(target=game_loop)
            _game_loop_started_in_this_process = True
            sio.sleep(0.01) # Yield control briefly
            print( not player: emit_ctx('action_feedback', {'success': False, 'message': "Player not recognized."}); return
    action_type = data.get('type')
    valid_actions = ['move', 'look', 'f"[{my_pid}] Worker: Game loop task started successfully via sio.start_background_task.")
        except Exception as e:
            print(f"!!! [{my_pid}] Worker: FAILED TO START GAME LOOP: {e} !!!")
            traceback.print_exc()
    else: 
        drink_potion', 'say', 'shout', 'build_wall', 'destroy_wall']
    if action_type not in valid_actions: emit_ctx('action_feedback', {'success': False, 'messageKey': 'ACTION_SENT_FEEDBACK.ACTION_FAILED_UNKNOWN_COMMAND', 'placeholders': {'actionWord': actionprint(f"[{my_pid}] Worker: Game loop already marked as started in this process.")

if __name__ == '__main__':
    print(f"[{os.getpid()}] Starting Flask-SocketIO server for LOCAL DEVELOPMENT...")
    start_game_loop_for_worker()
    sio.run(_type}}); return
    game_manager.queued_actions[sid] = data
    emit_ctx('action_feedback', {'success': True, 'messageKey': 'ACTION_SENT_FEEDBACK.ACTION_QUEUED'})

def start_game_loop_for_worker():
    global _game_loop_started_in_thisapp, debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), use_reloader=False)
else:
    print(f"[{_process
    my_pid = os.getpid()
    if not _game_loop_started_in_this_process:
        print(f"[{my_pid}] Worker: Attempting to start gameos.getpid()}] App module loaded by Gunicorn. Game loop is intended to start via post_fork hook.")
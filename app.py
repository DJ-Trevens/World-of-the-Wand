# app.py

import eventlet
eventlet.monkey_patch()

import os
import random
from flask import Flask, render_template, request, Blueprint, current_app
from flask_socketio import SocketIO, emit as emit_ctx
import time
import traceback
import uuid
import logging
import math
import psycopg2 # For PostgreSQL
from urllib.parse import urlparse # For parsing DATABASE_URL

# --- Game Settings ---
GRID_WIDTH, GRID_HEIGHT, GAME_HEARTBEAT_RATE, SHOUT_MANA_COST, MAX_VIEW_DISTANCE = 20, 15, 0.75, 5, 8
_game_loop_started_in_this_process = False
DESTROY_WALL_MANA_COST = 10
CHOP_TREE_MANA_COST = 15
INITIAL_POTIONS_DB = 3 # Default for new players in DB
INITIAL_WALL_ITEMS_DB = 3 # Default for new players in DB

TILE_FLOOR = 0
TILE_WALL = 1
TILE_WATER = 2

SERVER_IS_RAINING = True
DEFAULT_RAIN_INTENSITY = 0.25

PIXIE_CHAR = '*'
PIXIE_MANA_REGEN_BOOST = 1
PIXIE_PROXIMITY_FOR_BOOST = 3

ELF_CHAR = 'E'
TREE_CHAR = '\u2663'

BASE_MANA_REGEN_PER_HEARTBEAT_CYCLE = 0.5
HEARTBEATS_PER_MANA_REGEN_CYCLE = 3

SENSE_SIGHT_RANGE = MAX_VIEW_DISTANCE
SENSE_SOUND_RANGE_MAX = 8
SENSE_SMELL_RANGE_MAX = 6
SENSE_MAGIC_RANGE_MAX = 5

# --- App Setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'a_deep_and_binding_secret_for_dev')
GAME_PATH_PREFIX = '/world-of-the-wand'

# --- Database Configuration ---
DATABASE_URL = os.environ.get('DATABASE_URL')

# --- Logging Configuration ---
# (Same as before)
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


sio = SocketIO(logger=False, engineio_logger=False, async_mode="eventlet")
game_manager_instance = None

def get_player_name(sid): return f"Wizard-{sid[:4]}" # Simple name from SID


# --- Database Helper Functions ---
def get_db_connection():
    if not DATABASE_URL:
        app.logger.error("DATABASE_URL environment variable not set.")
        return None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        app.logger.error(f"Error connecting to database: {e}", exc_info=True)
        return None

def init_db_tables():
    conn = get_db_connection()
    if not conn:
        app.logger.error("Cannot initialize DB tables: No database connection.")
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS players (
                    player_id VARCHAR(255) PRIMARY KEY,
                    name VARCHAR(255),
                    scene_x INTEGER DEFAULT 0,
                    scene_y INTEGER DEFAULT 0,
                    x INTEGER DEFAULT %s,
                    y INTEGER DEFAULT %s,
                    char VARCHAR(1) DEFAULT '^',
                    current_health INTEGER DEFAULT 100,
                    max_health INTEGER DEFAULT 100,
                    current_mana REAL DEFAULT 175.0,
                    max_mana INTEGER DEFAULT 175,
                    potions INTEGER DEFAULT %s,
                    walls INTEGER DEFAULT %s,
                    gold INTEGER DEFAULT 0,
                    is_wet BOOLEAN DEFAULT FALSE,
                    last_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """, (GRID_WIDTH // 2, GRID_HEIGHT // 2, INITIAL_POTIONS_DB, INITIAL_WALL_ITEMS_DB))

            cur.execute("""
                CREATE TABLE IF NOT EXISTS trees (
                    tree_id VARCHAR(255) PRIMARY KEY,
                    scene_x INTEGER,
                    scene_y INTEGER,
                    x INTEGER,
                    y INTEGER,
                    species VARCHAR(50),
                    is_ancient BOOLEAN,
                    is_chopped_down BOOLEAN DEFAULT FALSE,
                    name VARCHAR(255),
                    lore_name VARCHAR(255),
                    elf_guardian_ids TEXT DEFAULT '' -- Comma-separated string of elf IDs
                );
            """)
            # Add more tables here (NPCs, scene_objects, etc.) as needed
            conn.commit()
        app.logger.info("Database tables checked/created successfully.")
    except Exception as e:
        app.logger.error(f"Error initializing database tables: {e}", exc_info=True)
    finally:
        if conn: conn.close()

class Tree: # ... (Tree class, elf_guardian_ids is now a list in code, TEXT in DB) ...
    def __init__(self, scene_x, scene_y, x, y, tree_id=None, species="Oak", is_ancient=True, is_chopped_down=False, name=None, elf_guardian_ids_str=""):
        self.id = tree_id if tree_id else str(uuid.uuid4())
        self.type = "Tree"
        self.char = TREE_CHAR
        self.scene_x = scene_x
        self.scene_y = scene_y
        self.x = x
        self.y = y
        self.species = species
        self.is_ancient = is_ancient
        self.is_chopped_down = is_chopped_down
        self.name = name if name else f"{self.species}-{self.id[:4]}"
        self.lore_name = f"{self.is_chopped_down and 'felled ' or ''}{self.is_ancient and 'ancient ' or ''}{self.species}"
        self.elf_guardian_ids = [eid.strip() for eid in elf_guardian_ids_str.split(',') if eid.strip()] if elf_guardian_ids_str else []


    def get_public_data(self):
        return {
            'id': self.id, 'type': self.type, 'char': self.char,
            'x': self.x, 'y': self.y,
            'scene_x': self.scene_x, 'scene_y': self.scene_y,
            'is_chopped_down': self.is_chopped_down,
            'name': self.name, 'lore_name': self.lore_name
        }
    def save_to_db(self):
        conn = get_db_connection()
        if not conn: return
        try:
            with conn.cursor() as cur:
                elf_ids_str = ",".join(self.elf_guardian_ids)
                cur.execute("""
                    INSERT INTO trees (tree_id, scene_x, scene_y, x, y, species, is_ancient, is_chopped_down, name, lore_name, elf_guardian_ids)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (tree_id) DO UPDATE SET
                        is_chopped_down = EXCLUDED.is_chopped_down,
                        elf_guardian_ids = EXCLUDED.elf_guardian_ids;
                """, (self.id, self.scene_x, self.scene_y, self.x, self.y, self.species, self.is_ancient, self.is_chopped_down, self.name, self.lore_name, elf_ids_str))
                conn.commit()
        except Exception as e:
            app.logger.error(f"Error saving tree {self.id} to DB: {e}", exc_info=True)
        finally:
            if conn: conn.close()


class ManaPixie: # ... (same as before) ...
    def __init__(self, scene_x, scene_y, initial_x=None, initial_y=None):
        self.id = str(uuid.uuid4())
        self.type = "ManaPixie"
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
                'scene_x': self.scene_x, 'scene_y': self.scene_y, 'type': self.type}
    def wander(self, scene):
        if random.random() < 0.3:
            dx, dy = random.choice([-1, 0, 1]), random.choice([-1, 0, 1])
            if dx == 0 and dy == 0: return
            new_x, new_y = self.x + dx, self.y + dy
            if scene.is_walkable(new_x, new_y) and not scene.is_entity_at(new_x, new_y, exclude_id=self.id): # Use generic is_entity_at
                self.x, self.y = new_x, new_y
    def attempt_evade(self, player_x, player_y, scene):
        possible_moves = []
        for dx_evade in [-1, 0, 1]:
            for dy_evade in [-1, 0, 1]:
                if dx_evade == 0 and dy_evade == 0: continue
                evade_x, evade_y = self.x + dx_evade, self.y + dy_evade
                if scene.is_walkable(evade_x, evade_y) and \
                   not scene.is_entity_at(evade_x, evade_y, exclude_id=self.id): # Use generic is_entity_at
                    possible_moves.append((evade_x, evade_y))
        if possible_moves:
            self.x, self.y = random.choice(possible_moves); return True
        return False

class Elf: # ... (same, no DB methods needed here yet, state is managed by GM) ...
    def __init__(self, scene_x, scene_y, initial_x=None, initial_y=None, home_tree_id=None):
        self.id = str(uuid.uuid4())
        self.type = "Elf"
        self.race = "Wood"
        self.char = ELF_CHAR
        self.scene_x = scene_x
        self.scene_y = scene_y
        self.x = initial_x if initial_x is not None else random.randint(0, GRID_WIDTH - 1)
        self.y = initial_y if initial_y is not None else random.randint(0, GRID_HEIGHT - 1)
        self.name = f"Elf-{self.id[:4]}"
        self.lore_name = f"{self.race} Elf"
        self.home_tree_id = home_tree_id
        self.state = "wandering_near_tree"
        self.max_health = 30
        self.current_health = self.max_health
        self.is_sneaking = False
        self.sensory_cues = {
            'sight': [('SENSORY.ELF_SIGHT_GRACEFUL', 0.7, SENSE_SIGHT_RANGE)],
            'sound': [('SENSORY.ELF_SOUND_RUSTLE', 0.5, 4), ('SENSORY.ELF_SOUND_SOFT_SONG', 0.2, 6)],
            'smell': [('SENSORY.ELF_SMELL_PINE', 0.4, 3)],
            'magic': [('SENSORY.ELF_MAGIC_NATURE', 0.6, 3)]
        }
        self.is_hidden_by_tree = False
    def get_public_data(self):
        return {
            'id': self.id, 'name': self.name, 'char': self.char, 'type': self.type,
            'x': self.x, 'y': self.y, 'scene_x': self.scene_x, 'scene_y': self.scene_y,
            'is_sneaking': self.is_sneaking, 'state': self.state,
            'is_hidden_by_tree': self.is_hidden_by_tree
        }
    def update_ai(self, scene, game_manager):
        home_tree = game_manager.get_tree(self.home_tree_id) if self.home_tree_id else None
        if self.state == "distressed_no_tree":
            if random.random() < 0.05: self.wander_randomly(scene)
            return
        if self.state == "wandering_near_tree":
            if home_tree and not home_tree.is_chopped_down:
                self.wander_near_tree(scene, home_tree)
            else:
                self.state = "distressed_no_tree"
                self.wander_randomly(scene)
        if home_tree and not home_tree.is_chopped_down and self.x == home_tree.x and self.y == home_tree.y:
            self.is_hidden_by_tree = True
        else:
            self.is_hidden_by_tree = False
    def wander_near_tree(self, scene, tree):
        WANDER_RADIUS_FROM_TREE = 4
        if random.random() < 0.2:
            dist_to_tree = math.sqrt((self.x - tree.x)**2 + (self.y - tree.y)**2)
            dx = 0; dy = 0
            if dist_to_tree > WANDER_RADIUS_FROM_TREE:
                if self.x < tree.x: dx = 1
                elif self.x > tree.x: dx = -1
                if self.y < tree.y: dy = 1
                elif self.y > tree.y: dy = -1
            else: dx, dy = random.choice([-1, 0, 1]), random.choice([-1, 0, 1])
            if dx == 0 and dy == 0: return
            new_x, new_y = self.x + dx, self.y + dy
            if math.sqrt((new_x - tree.x)**2 + (new_y - tree.y)**2) > WANDER_RADIUS_FROM_TREE + 1: return
            if scene.is_walkable(new_x, new_y) and not scene.is_entity_at(new_x, new_y, exclude_id=self.id):
                self.x, self.y = new_x, new_y
    def wander_randomly(self, scene):
        if random.random() < 0.15:
            dx, dy = random.choice([-1, 0, 1]), random.choice([-1, 0, 1])
            if dx == 0 and dy == 0: return
            new_x, new_y = self.x + dx, self.y + dy
            if scene.is_walkable(new_x, new_y) and not scene.is_entity_at(new_x, new_y, exclude_id=self.id):
                self.x, self.y = new_x, new_y

class Player: # Modified for DB interaction
    def __init__(self, sid, name, db_data=None):
        self.id = sid # SID is the primary key for now
        self.name = name
        if db_data:
            # Load from db_data (dictionary from DB row)
            self.scene_x = db_data.get('scene_x', 0)
            self.scene_y = db_data.get('scene_y', 0)
            self.x = db_data.get('x', GRID_WIDTH // 2)
            self.y = db_data.get('y', GRID_HEIGHT // 2)
            self.char = db_data.get('char', random.choice(['^', 'v', '<', '>']))
            self.current_health = db_data.get('current_health', 100)
            self.max_health = db_data.get('max_health', 100)
            self.current_mana = float(db_data.get('current_mana', 175.0))
            self.max_mana = db_data.get('max_mana', 175)
            self.potions = db_data.get('potions', INITIAL_POTIONS_DB)
            self.walls = db_data.get('walls', INITIAL_WALL_ITEMS_DB)
            self.gold = db_data.get('gold', 0)
            self.is_wet = db_data.get('is_wet', False)
        else: # Default values for a new player
            self.scene_x = 0
            self.scene_y = 0
            self.x = GRID_WIDTH // 2
            self.y = GRID_HEIGHT // 2
            self.char = random.choice(['^', 'v', '<', '>'])
            self.max_health = 100; self.current_health = 100
            self.max_mana = 175; self.current_mana = 175.0
            self.potions = INITIAL_POTIONS_DB
            self.walls = INITIAL_WALL_ITEMS_DB
            self.gold = 0
            self.is_wet = False

        self.time_became_wet = 0 # Transient state
        self.mana_regen_accumulator = 0.0 # Transient state
        self.visible_tiles_cache = set() # Transient state

    def save_to_db(self):
        conn = get_db_connection()
        if not conn: return
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO players (player_id, name, scene_x, scene_y, x, y, char, current_health, max_health, current_mana, max_mana, potions, walls, gold, is_wet, last_seen)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (player_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        scene_x = EXCLUDED.scene_x, scene_y = EXCLUDED.scene_y,
                        x = EXCLUDED.x, y = EXCLUDED.y, char = EXCLUDED.char,
                        current_health = EXCLUDED.current_health, max_health = EXCLUDED.max_health,
                        current_mana = EXCLUDED.current_mana, max_mana = EXCLUDED.max_mana,
                        potions = EXCLUDED.potions, walls = EXCLUDED.walls, gold = EXCLUDED.gold,
                        is_wet = EXCLUDED.is_wet, last_seen = CURRENT_TIMESTAMP;
                """, (self.id, self.name, self.scene_x, self.scene_y, self.x, self.y, self.char,
                      self.current_health, self.max_health, self.current_mana, self.max_mana,
                      self.potions, self.walls, self.gold, self.is_wet))
                conn.commit()
            app.logger.debug(f"Saved player {self.name} ({self.id}) to DB.")
        except Exception as e:
            app.logger.error(f"Error saving player {self.name} ({self.id}) to DB: {e}", exc_info=True)
        finally:
            if conn: conn.close()

    # ... (rest of Player methods: update_position, drink_potion, etc. are the same) ...
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
        char_changed = self.char != new_char
        self.char = new_char
        if scene_changed_flag:
            game_manager.handle_player_scene_change(self, old_scene_x, old_scene_y)
            if transition_key: socketio_instance.emit('lore_message', {'messageKey': transition_key, 'placeholders': {'scene_x': self.scene_x, 'scene_y': self.scene_y}, 'type': 'system'}, room=self.id)
        elif self.x != original_x_tile or self.y != original_y_tile or char_changed :
            current_scene = game_manager.get_or_create_scene(self.scene_x, self.scene_y)
            self.visible_tiles_cache = game_manager.calculate_fov(self.x, self.y, current_scene, SENSE_SIGHT_RANGE)
        return scene_changed_flag or (self.x != original_x_tile or self.y != original_y_tile or char_changed)
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
    def get_full_data(self): # Ensure this reflects what's in DB and current state
        return {'id': self.id, 'name': self.name, 'scene_x': self.scene_x, 'scene_y': self.scene_y,
                'x': self.x, 'y': self.y, 'char': self.char, 'max_health': self.max_health,
                'current_health': self.current_health, 'max_mana': self.max_mana,
                'current_mana': int(self.current_mana), 'potions': self.potions, 'gold': self.gold,
                'walls': self.walls, 'is_wet': self.is_wet}


class Scene: # ... (same as before) ...
    def __init__(self, scene_x, scene_y, name_generator_func=None):
        self.scene_x = scene_x; self.scene_y = scene_y
        self.name = f"Area ({scene_x},{scene_y})"
        if name_generator_func: self.name = name_generator_func(scene_x, scene_y)
        self.players_sids = set(); self.npc_ids = set()
        self.tree_ids = set()
        self.terrain_grid = [[TILE_FLOOR for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
        self.is_indoors = False
        self.game_manager_ref = get_game_manager() # Ensure ref is set on creation
    def add_player(self, player_sid): self.players_sids.add(player_sid)
    def remove_player(self, player_sid): self.players_sids.discard(player_sid)
    def get_player_sids(self): return list(self.players_sids)
    def add_npc(self, npc_id): self.npc_ids.add(npc_id)
    def remove_npc(self, npc_id): self.npc_ids.discard(npc_id)
    def get_npc_ids(self): return list(self.npc_ids)
    def add_tree(self, tree_id): self.tree_ids.add(tree_id)
    def remove_tree(self, tree_id): self.tree_ids.discard(tree_id) # If trees can be removed
    def get_tree_ids(self): return list(self.tree_ids)
    def get_tile_type(self, x, y):
        if 0 <= y < GRID_HEIGHT and 0 <= x < GRID_WIDTH: return self.terrain_grid[y][x]
        return TILE_WALL
    def is_transparent(self, x, y):
        if not (0 <= x < GRID_WIDTH and 0 <= y < GRID_HEIGHT): return False
        gm = get_game_manager()
        if gm and gm.get_tree_at(x,y, self.scene_x, self.scene_y):
            tree = gm.get_tree_at(x,y, self.scene_x, self.scene_y)
            if tree and not tree.is_chopped_down:
                return False
        tile_type = self.terrain_grid[y][x]
        return tile_type == TILE_FLOOR or tile_type == TILE_WATER
    def is_walkable(self, x, y):
        if not (0 <= x < GRID_WIDTH and 0 <= y < GRID_HEIGHT): return False
        tile_type = self.get_tile_type(x,y)
        gm = get_game_manager()
        if gm:
            tree_at_loc = gm.get_tree_at(x, y, self.scene_x, self.scene_y)
            if tree_at_loc and not tree_at_loc.is_chopped_down:
                return False
        return tile_type == TILE_FLOOR or tile_type == TILE_WATER
    def set_tile_type(self, x, y, tile_type):
        if 0 <= y < GRID_HEIGHT and 0 <= x < GRID_WIDTH: self.terrain_grid[y][x] = tile_type; return True
        return False
    def get_terrain_for_payload(self, visible_tiles_set):
        terrain_data = {'walls': [], 'water': []}
        if not visible_tiles_set: return terrain_data
        for r_idx, row in enumerate(self.terrain_grid):
            for c_idx, tile_type in enumerate(row):
                if (c_idx, r_idx) in visible_tiles_set:
                    if tile_type == TILE_WALL: terrain_data['walls'].append({'x': c_idx, 'y': r_idx})
                    elif tile_type == TILE_WATER: terrain_data['water'].append({'x': c_idx, 'y': r_idx})
        return terrain_data
    def is_entity_at(self, x, y, exclude_id=None): # Generic check for any entity (NPC or Player)
        gm = get_game_manager()
        if self.is_npc_at(x,y, exclude_id): return True
        if self.is_player_at(x,y): return True # exclude_id not applicable for players in this simple check
        tree = gm.get_tree_at(x,y,self.scene_x, self.scene_y)
        if tree and not tree.is_chopped_down and tree.id != exclude_id:
             return True # Unchopped trees block general entity movement
        return False
    def is_npc_at(self, x, y, exclude_id=None):
        gm = get_game_manager()
        if not gm: return False
        for npc_id_in_scene in self.npc_ids:
            if exclude_id and npc_id_in_scene == exclude_id: continue
            npc = gm.get_npc(npc_id_in_scene)
            if npc and npc.x == x and npc.y == y: return True
        return False
    def is_player_at(self, x, y, player_id_to_check=None):
        gm = get_game_manager()
        if not gm: return False
        for player_sid_in_scene in self.players_sids:
            player = gm.get_player(player_sid_in_scene)
            if player and player.x == x and player.y == y: return True
        return False

class GameManager: # ... (same structure, DB methods added)
    def __init__(self, socketio_instance):
        self.players = {}; self.scenes = {}
        self.all_npcs = {}
        self.all_trees = {}
        self.queued_actions = {}; self.socketio = socketio_instance
        self.server_is_raining = SERVER_IS_RAINING
        self.heartbeats_until_mana_regen = HEARTBEATS_PER_MANA_REGEN_CYCLE
        self.loop_is_actually_running_flag = False
        self.game_loop_greenlet = None
        self.loop_iteration_count = 0
        self._fov_octant_transforms = [
            (1,  0,  0,  1), (0,  1,  1,  0), (0, -1,  1,  0), (-1,  0,  0,  1),
            (-1,  0,  0, -1), (0, -1, -1,  0), (0,  1, -1,  0), (1,  0,  0, -1)
        ]
        self.load_all_trees_from_db() # Load trees on startup

    def load_all_trees_from_db(self):
        conn = get_db_connection()
        if not conn: return
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT tree_id, scene_x, scene_y, x, y, species, is_ancient, is_chopped_down, name, lore_name, elf_guardian_ids FROM trees")
                for row in cur.fetchall():
                    tree_id, scene_x, scene_y, x, y, species, is_ancient, is_chopped, name, lore_name, elf_ids_str = row
                    tree = Tree(scene_x, scene_y, x, y, tree_id, species, is_ancient, is_chopped, name, elf_ids_str)
                    self.all_trees[tree.id] = tree
                    # Ensure tree is added to its scene's list
                    scene = self.get_or_create_scene(scene_x, scene_y) # This uses get_game_manager implicitly
                    if tree.id not in scene.tree_ids:
                        scene.add_tree(tree.id)
                app.logger.info(f"Loaded {len(self.all_trees)} trees from database.")
        except Exception as e:
            app.logger.error(f"Error loading trees from DB: {e}", exc_info=True)
        finally:
            if conn: conn.close()

    def calculate_fov(self, observer_x, observer_y, scene, radius):
        visible_tiles = set()
        visible_tiles.add((observer_x, observer_y))
        for octant in range(8):
            self._cast_light_octant(observer_x, observer_y, radius, 1, 1.0, 0.0, octant, scene, visible_tiles)
        return visible_tiles
    def _cast_light_octant(self, cx, cy, radius, row_depth, start_slope, end_slope, octant, scene, visible_tiles):
        xx, xy, yx, yy = self._fov_octant_transforms[octant]
        radius_squared = radius * radius
        if start_slope < end_slope: return
        for i in range(row_depth, radius + 1):
            blocked_for_row = False
            dx, dy = -i, -i
            while dx <= 0:
                dx += 1
                map_x = cx + dx * xx + dy * xy
                map_y = cy + dx * yx + dy * yy
                if not (0 <= map_x < GRID_WIDTH and 0 <= map_y < GRID_HEIGHT): continue
                left_slope = (dx - 0.5) / (dy + 0.5) if (dy + 0.5) != 0 else float('inf') * math.copysign(1, dx - 0.5)
                right_slope = (dx + 0.5) / (dy - 0.5) if (dy - 0.5) != 0 else float('inf') * math.copysign(1, dx + 0.5)
                if start_slope < right_slope: continue
                elif end_slope > left_slope: break
                if (dx * dx + dy * dy) < radius_squared: visible_tiles.add((map_x, map_y))
                if not scene.is_transparent(map_x, map_y):
                    if blocked_for_row: continue
                    else:
                        blocked_for_row = True
                        self._cast_light_octant(cx, cy, radius, i + 1, start_slope, left_slope, octant, scene, visible_tiles)
                        start_slope = right_slope
                else:
                    if blocked_for_row:
                        blocked_for_row = False
                        start_slope = right_slope
            if blocked_for_row: break

    def spawn_initial_npcs_and_entities(self): # For initial DB population if empty
        scene_0_0 = self.get_or_create_scene(0,0)
        # Spawn Pixies (these are not persisted by default in this example)
        for i in range(2):
            px, py = random.randint(0, GRID_WIDTH-1), random.randint(0, GRID_HEIGHT-1)
            while not scene_0_0.is_walkable(px,py) or scene_0_0.is_entity_at(px,py):
                 px, py = random.randint(0, GRID_WIDTH-1), random.randint(0, GRID_HEIGHT-1)
            pixie = ManaPixie(0, 0, initial_x=px, initial_y=py)
            self.all_npcs[pixie.id] = pixie; scene_0_0.add_npc(pixie.id)
            app.logger.info(f"Spawned transient {pixie.type} {pixie.name} at S(0,0) T({pixie.x},{pixie.y})")

        # Spawn One Test Tree if no trees exist in DB for this scene (or at all)
        if not any(t for t in self.all_trees.values() if t.scene_x == 0 and t.scene_y == 0):
            tree_x, tree_y = 5, 5
            while not scene_0_0.is_walkable(tree_x, tree_y) or scene_0_0.is_entity_at(tree_x,tree_y):
                tree_x, tree_y = random.randint(2, GRID_WIDTH-3), random.randint(2, GRID_HEIGHT-3)
            test_tree = Tree(0,0, tree_x, tree_y)
            test_tree.save_to_db() # Save to DB
            self.all_trees[test_tree.id] = test_tree
            scene_0_0.add_tree(test_tree.id)
            app.logger.info(f"Spawned and saved {test_tree.type} {test_tree.name} at S(0,0) T({test_tree.x},{test_tree.y})")

            # Spawn Elves near the tree (these are not persisted by default)
            for i in range(2):
                ex, ey = test_tree.x, test_tree.y
                elf_already_here = False
                for elf_id_guard in test_tree.elf_guardian_ids:
                    existing_elf = self.get_npc(elf_id_guard)
                    if existing_elf and existing_elf.x == ex and existing_elf.y == ey:
                        elf_already_here = True; break
                if elf_already_here:
                     ex, ey = tree_x + random.choice([-1,1]), tree_y + random.choice([-1,1])
                     while not scene_0_0.is_walkable(ex,ey) or scene_0_0.is_entity_at(ex,ey):
                         ex, ey = tree_x + random.choice([-1,0,1]), tree_y + random.choice([-1,0,1])
                         if ex == tree_x and ey == tree_y : ex, ey = tree_x+1, tree_y
                elf = Elf(0,0, initial_x=ex, initial_y=ey, home_tree_id=test_tree.id)
                self.all_npcs[elf.id] = elf
                scene_0_0.add_npc(elf.id)
                test_tree.elf_guardian_ids.append(elf.id)
            test_tree.save_to_db() # Re-save tree with elf guardian IDs
            app.logger.info(f"Spawned transient Elves for {test_tree.name}")
        else:
            app.logger.info("Trees already loaded from DB, skipping initial tree spawn.")


    def get_tree(self, tree_id): return self.all_trees.get(tree_id)
    def get_tree_at(self, x, y, scene_x, scene_y):
        for tree_obj in self.all_trees.values():
            if tree_obj.scene_x == scene_x and tree_obj.scene_y == scene_y and \
               tree_obj.x == x and tree_obj.y == y:
                return tree_obj
        return None
    def get_visible_trees_for_observer(self, observer_player):
        visible_trees_data = []
        gm = get_game_manager()
        scene = gm.get_or_create_scene(observer_player.scene_x, observer_player.scene_y)
        for tree_id in scene.get_tree_ids(): # Iterate only trees in current scene
            tree = gm.get_tree(tree_id)
            if tree and (tree.x, tree.y) in observer_player.visible_tiles_cache:
                visible_trees_data.append(tree.get_public_data())
        return visible_trees_data
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
        gm = get_game_manager()
        if scene_coords not in gm.scenes:
            new_scene = Scene(scene_x, scene_y)
            if scene_x == 0 and scene_y == 0:
                gm.setup_spawn_shrine(new_scene)
            gm.scenes[scene_coords] = new_scene
            app.logger.info(f"Created new scene at ({scene_x},{scene_y}): {new_scene.name}")
        return gm.scenes[scene_coords]

    def add_player(self, sid): # Modified to load/save player
        name = get_player_name(sid)
        gm = get_game_manager()
        player_data_from_db = None
        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT scene_x, scene_y, x, y, char, current_health, max_health, current_mana, max_mana, potions, walls, gold, is_wet FROM players WHERE player_id = %s", (sid,))
                    row = cur.fetchone()
                    if row:
                        keys = ['scene_x', 'scene_y', 'x', 'y', 'char', 'current_health', 'max_health', 'current_mana', 'max_mana', 'potions', 'walls', 'gold', 'is_wet']
                        player_data_from_db = dict(zip(keys, row))
                        app.logger.info(f"Loaded player {name} ({sid}) from DB.")
            except Exception as e:
                app.logger.error(f"Error loading player {name} ({sid}) from DB: {e}", exc_info=True)
            finally:
                if conn: conn.close()

        player = Player(sid, name, db_data=player_data_from_db)
        if not player_data_from_db: # New player
            player.save_to_db() # Save initial state for new player
            app.logger.info(f"Created new player {name} ({sid}) and saved to DB.")

        gm.players[sid] = player
        scene = gm.get_or_create_scene(player.scene_x, player.scene_y)
        scene.add_player(sid)
        player.visible_tiles_cache = gm.calculate_fov(player.x, player.y, scene, SENSE_SIGHT_RANGE)
        app.logger.info(f"Player {name} added to scene ({player.scene_x},{player.scene_y}). Total players: {len(gm.players)}")

        new_player_public_data = player.get_public_data()
        for other_sid_in_scene in scene.get_player_sids():
            if other_sid_in_scene != sid:
                other_player = gm.get_player(other_sid_in_scene)
                if other_player and gm.is_player_visible_to_observer(other_player, player):
                     gm.socketio.emit('player_entered_your_scene', new_player_public_data, room=other_sid_in_scene)
        return player

    def remove_player(self, sid): # Modified to save player on disconnect
        gm = get_game_manager()
        player = gm.players.get(sid) # Get before pop to save
        if player:
            player.save_to_db() # Save player state before removing
            app.logger.info(f"Player {player.name} state saved on disconnect.")
        
        player = gm.players.pop(sid, None) # Now pop
        if sid in gm.queued_actions: del gm.queued_actions[sid]

        if player:
            old_scene_coords = (player.scene_x, player.scene_y)
            if old_scene_coords in gm.scenes:
                scene = gm.scenes[old_scene_coords]; scene.remove_player(sid)
                app.logger.info(f"Removed {player.name} from scene {old_scene_coords}. Players in scene: {len(scene.get_player_sids())}")
                for other_sid_in_scene in scene.get_player_sids():
                     gm.socketio.emit('player_exited_your_scene', {'id': sid, 'name': player.name}, room=other_sid_in_scene)
            return player
        return None

    def get_player(self, sid): return get_game_manager().players.get(sid)
    def get_npc(self, npc_id): return get_game_manager().all_npcs.get(npc_id)
    def get_npc_at(self, x, y, scene_x, scene_y): # ... (same) ...
        gm = get_game_manager()
        for npc_obj in gm.all_npcs.values():
            if npc_obj.scene_x == scene_x and npc_obj.scene_y == scene_y and npc_obj.x == x and npc_obj.y == y:
                return npc_obj
        return None
    def get_player_at(self, x, y, scene_x, scene_y): # ... (same) ...
        gm = get_game_manager()
        for player_obj in gm.players.values():
            if player_obj.scene_x == scene_x and player_obj.scene_y == scene_y and player_obj.x == x and player_obj.y == y:
                return player_obj
        return None
    def handle_player_scene_change(self, player, old_scene_x, old_scene_y): # ... (same) ...
        gm = get_game_manager()
        old_scene_coords = (old_scene_x, old_scene_y); new_scene_coords = (player.scene_x, player.scene_y)
        if old_scene_coords != new_scene_coords:
            if old_scene_coords in gm.scenes:
                old_scene_obj = gm.scenes[old_scene_coords]; old_scene_obj.remove_player(player.id)
                app.logger.info(f"Player {player.name} left scene {old_scene_coords}.")
                for other_sid in old_scene_obj.get_player_sids():
                    gm.socketio.emit('player_exited_your_scene', {'id': player.id, 'name': player.name}, room=other_sid)
            new_scene_obj = gm.get_or_create_scene(player.scene_x, player.scene_y); new_scene_obj.add_player(player.id)
            player.visible_tiles_cache = gm.calculate_fov(player.x, player.y, new_scene_obj, SENSE_SIGHT_RANGE)
            app.logger.info(f"Player {player.name} entered scene {new_scene_coords}. Terrain: {new_scene_obj.name}")
            player_public_data_for_new_scene = player.get_public_data()
            for other_sid in new_scene_obj.get_player_sids():
                if other_sid != player.id:
                    other_player = gm.get_player(other_sid)
                    if other_player and gm.is_player_visible_to_observer(other_player, player):
                        gm.socketio.emit('player_entered_your_scene', player_public_data_for_new_scene, room=other_sid)
    def is_player_visible_to_observer(self, obs_p, target_p): # ... (same) ...
        if not obs_p or not target_p: return False
        if obs_p.id == target_p.id: return False
        if obs_p.scene_x != target_p.scene_x or obs_p.scene_y != target_p.scene_y: return False
        return (target_p.x, target_p.y) in obs_p.visible_tiles_cache
    def is_npc_visible_to_observer(self, obs_p, target_npc): # ... (same) ...
        if not obs_p or not target_npc: return False
        if obs_p.scene_x != target_npc.scene_x or obs_p.scene_y != target_npc.scene_y: return False
        if hasattr(target_npc, 'is_sneaking') and target_npc.is_sneaking:
             return False
        return (target_npc.x, target_npc.y) in obs_p.visible_tiles_cache
    def get_visible_players_for_observer(self, observer_player): # ... (same) ...
        visible_others = []
        gm = get_game_manager()
        scene = gm.get_or_create_scene(observer_player.scene_x, observer_player.scene_y)
        for target_sid in scene.get_player_sids():
            if target_sid == observer_player.id: continue
            target_player = gm.get_player(target_sid)
            if target_player and (target_player.x, target_player.y) in observer_player.visible_tiles_cache:
                visible_others.append(target_player.get_public_data())
        return visible_others
    def get_visible_npcs_for_observer(self, observer_player): # ... (same) ...
        visible_npcs_data = []
        gm = get_game_manager()
        scene = gm.get_or_create_scene(observer_player.scene_x, observer_player.scene_y)
        for npc_id in scene.get_npc_ids():
            npc = gm.get_npc(npc_id)
            if not npc: continue
            if isinstance(npc, Elf) and npc.home_tree_id:
                home_tree = gm.get_tree(npc.home_tree_id)
                if home_tree and not home_tree.is_chopped_down and npc.x == home_tree.x and npc.y == home_tree.y:
                    npc.is_hidden_by_tree = True
                else:
                    npc.is_hidden_by_tree = False
            #else: # Ensure attribute exists for non-elves if client expects it universally
            #    npc.is_hidden_by_tree = False
            if gm.is_npc_visible_to_observer(observer_player, npc):
                   visible_npcs_data.append(npc.get_public_data())
        return visible_npcs_data
    def get_target_coordinates(self, player, dx, dy): return player.x + dx, player.y + dy # ... (same) ...
    def get_general_direction(self, observer, target): # ... (same) ...
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
    def process_sensory_perception(self, player, scene): # ... (same) ...
        perceived_cues_this_tick = set()
        gm = get_game_manager()
        for npc_id in scene.get_npc_ids():
            npc = gm.get_npc(npc_id)
            if not npc or npc.is_hidden: continue
            if hasattr(npc, 'is_hidden_by_tree') and npc.is_hidden_by_tree: continue
            is_visible_flag = (npc.x, npc.y) in player.visible_tiles_cache
            if hasattr(npc, 'is_sneaking') and npc.is_sneaking: is_visible_flag = False
            distance = abs(player.x - npc.x) + abs(player.y - npc.y)
            if is_visible_flag:
                for cue_key, relevance, _ in npc.sensory_cues.get('sight', []):
                    if random.random() < (relevance * 0.05) and cue_key not in perceived_cues_this_tick:
                        gm.socketio.emit('lore_message', {'messageKey': cue_key, 'placeholders': {'npcName': npc.name}, 'type': 'sensory-sight'}, room=player.id)
                        perceived_cues_this_tick.add(cue_key); break
            else:
                for sense_type in ['sound', 'smell', 'magic']:
                    for cue_key, relevance, cue_range in npc.sensory_cues.get(sense_type, []):
                        if distance <= cue_range:
                            perception_chance = relevance * (1 - (distance / (cue_range + 1.0))) * 0.5
                            if random.random() < perception_chance and cue_key not in perceived_cues_this_tick:
                                gm.socketio.emit('lore_message', {'messageKey': cue_key, 'placeholders': {'npcName': npc.name, 'direction': gm.get_general_direction(player, npc)}, 'type': f'sensory-{sense_type}'}, room=player.id)
                                perceived_cues_this_tick.add(cue_key); break
                        if cue_key in perceived_cues_this_tick: break
    def process_actions(self,): # ... (same chop_tree logic, just ensure it calls tree.save_to_db()) ...
        gm = get_game_manager()
        current_actions_to_process = dict(gm.queued_actions); gm.queued_actions.clear(); processed_sids = set()
        for sid_action, action_data in current_actions_to_process.items():
            if sid_action in processed_sids : continue
            player = gm.get_player(sid_action);
            if not player: app.logger.warning(f"Action from non-existent player SID {sid_action}"); continue
            action_type = action_data.get('type'); details = action_data.get('details', {})
            app.logger.debug(f"Processing action for {player.name}: {action_type} with details {details}")
            scene_of_player = gm.get_or_create_scene(player.scene_x, player.scene_y)
            if action_type == 'move' or action_type == 'look':
                dx, dy = details.get('dx', 0), details.get('dy', 0)
                new_char_for_player = details.get('newChar', player.char)
                if action_type == 'move':
                    target_x, target_y = player.x + dx, player.y + dy
                    can_move_to_tile = True
                    if 0 <= target_x < GRID_WIDTH and 0 <= target_y < GRID_HEIGHT:
                        if not scene_of_player.is_walkable(target_x, target_y):
                            gm.socketio.emit('lore_message', {'messageKey': 'LORE.ACTION_BLOCKED_WALL', 'type': 'event-bad'}, room=player.id); can_move_to_tile = False # Generic blocked message
                        else:
                            npc_at_target = gm.get_npc_at(target_x, target_y, player.scene_x, player.scene_y)
                            if npc_at_target and isinstance(npc_at_target, ManaPixie):
                                if npc_at_target.attempt_evade(player.x, player.y, scene_of_player):
                                    gm.socketio.emit('lore_message', {'messageKey': 'LORE.PIXIE_MOVED_AWAY', 'type': 'system', 'placeholders':{'pixieName': npc_at_target.name}}, room=player.id)
                                else:
                                    gm.socketio.emit('lore_message', {'messageKey': 'LORE.PIXIE_BLOCKED_PATH', 'type': 'event-bad', 'placeholders':{'pixieName': npc_at_target.name}}, room=player.id); can_move_to_tile = False
                            elif npc_at_target :
                                 gm.socketio.emit('lore_message', {'messageKey': 'LORE.NPC_BLOCKED_PATH', 'type': 'event-bad', 'placeholders':{'npcName': npc_at_target.name}}, room=player.id); can_move_to_tile = False
                            elif scene_of_player.get_tile_type(target_x, target_y) == TILE_WATER:
                                player.set_wet_status(True, gm.socketio, reason="water_tile")
                    if can_move_to_tile:
                         player.update_position(dx, dy, new_char_for_player, gm, gm.socketio)
                    elif player.char != new_char_for_player:
                        player.char = new_char_for_player
                        player.visible_tiles_cache = gm.calculate_fov(player.x, player.y, scene_of_player, SENSE_SIGHT_RANGE)
                elif action_type == 'look':
                    if player.char != new_char_for_player: player.char = new_char_for_player
                    player.visible_tiles_cache = gm.calculate_fov(player.x, player.y, scene_of_player, SENSE_SIGHT_RANGE)
                    gm.process_sensory_perception(player, scene_of_player)
            elif action_type == 'chop_tree':
                dx, dy = details.get('dx', 0), details.get('dy', 0)
                target_x, target_y = gm.get_target_coordinates(player, dx, dy)
                tree_to_chop = gm.get_tree_at(target_x, target_y, player.scene_x, player.scene_y)
                if not tree_to_chop:
                    gm.socketio.emit('lore_message', {'messageKey': 'LORE.CHOP_FAIL_NO_TREE', 'type': 'event-bad'}, room=player.id)
                elif tree_to_chop.is_chopped_down:
                    gm.socketio.emit('lore_message', {'messageKey': 'LORE.CHOP_FAIL_ALREADY_CHOPPED', 'type': 'event-bad'}, room=player.id)
                elif not player.can_afford_mana(CHOP_TREE_MANA_COST):
                    gm.socketio.emit('lore_message', {'messageKey': 'LORE.CHOP_FAIL_NO_MANA', 'placeholders': {'manaCost': CHOP_TREE_MANA_COST}, 'type': 'event-bad'}, room=player.id)
                else:
                    player.spend_mana(CHOP_TREE_MANA_COST)
                    tree_to_chop.is_chopped_down = True
                    tree_to_chop.save_to_db() # Persist change
                    gm.socketio.emit('lore_message', {'messageKey': 'LORE.CHOP_SUCCESS', 'placeholders': {'treeName': tree_to_chop.name, 'manaCost': CHOP_TREE_MANA_COST}, 'type': 'event-good'}, room=player.id)
                    for elf_id in tree_to_chop.elf_guardian_ids:
                        elf = gm.get_npc(elf_id)
                        if elf and isinstance(elf, Elf):
                            elf.state = "distressed_no_tree"
                            gm.socketio.emit('lore_message', {'messageKey': 'LORE.ELF_TREE_DESTROYED_REACTION', 'placeholders': {'elfName': elf.name, 'treeName': tree_to_chop.lore_name}, 'type': 'system-event-negative'}, room=player.id)
                    for p_sid in scene_of_player.get_player_sids():
                        p = gm.get_player(p_sid)
                        if p: p.visible_tiles_cache = gm.calculate_fov(p.x, p.y, scene_of_player, SENSE_SIGHT_RANGE)
            elif action_type == 'build_wall':
                dx, dy = details.get('dx', 0), details.get('dy', 0); target_x, target_y = gm.get_target_coordinates(player, dx, dy)
                if not (0 <= target_x < GRID_WIDTH and 0 <= target_y < GRID_HEIGHT): gm.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_FAIL_OUT_OF_BOUNDS', 'type': 'event-bad'}, room=player.id)
                elif not scene_of_player.is_walkable(target_x, target_y) or scene_of_player.get_tile_type(target_x, target_y) != TILE_FLOOR: gm.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_FAIL_OBSTRUCTED', 'type': 'event-bad'}, room=player.id)
                elif gm.get_npc_at(target_x, target_y, player.scene_x, player.scene_y) or gm.get_player_at(target_x, target_y, player.scene_x, player.scene_y): gm.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_FAIL_OBSTRUCTED', 'type': 'event-bad'}, room=player.id)
                elif not player.has_wall_items(): gm.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_FAIL_NO_MATERIALS', 'type': 'event-bad'}, room=player.id)
                else:
                    player.use_wall_item(); scene_of_player.set_tile_type(target_x, target_y, TILE_WALL)
                    gm.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_SUCCESS', 'placeholders': {'walls': player.walls}, 'type': 'event-good'}, room=player.id)
                    for p_sid in scene_of_player.get_player_sids():
                        p = gm.get_player(p_sid)
                        if p: p.visible_tiles_cache = gm.calculate_fov(p.x, p.y, scene_of_player, SENSE_SIGHT_RANGE)
            elif action_type == 'destroy_wall':
                dx, dy = details.get('dx', 0), details.get('dy', 0); target_x, target_y = gm.get_target_coordinates(player, dx, dy)
                if not (0 <= target_x < GRID_WIDTH and 0 <= target_y < GRID_HEIGHT): gm.socketio.emit('lore_message', {'messageKey': 'LORE.DESTROY_FAIL_OUT_OF_BOUNDS', 'type': 'event-bad'}, room=player.id)
                elif scene_of_player.get_tile_type(target_x, target_y) != TILE_WALL: gm.socketio.emit('lore_message', {'messageKey': 'LORE.DESTROY_FAIL_NO_WALL', 'type': 'event-bad'}, room=player.id)
                elif not player.can_afford_mana(DESTROY_WALL_MANA_COST): gm.socketio.emit('lore_message', {'messageKey': 'LORE.DESTROY_FAIL_NO_MANA', 'placeholders': {'manaCost': DESTROY_WALL_MANA_COST}, 'type': 'event-bad'}, room=player.id)
                else:
                    player.spend_mana(DESTROY_WALL_MANA_COST); player.add_wall_item(); scene_of_player.set_tile_type(target_x, target_y, TILE_FLOOR)
                    gm.socketio.emit('lore_message', {'messageKey': 'LORE.DESTROY_SUCCESS', 'placeholders': {'walls': player.walls, 'manaCost': DESTROY_WALL_MANA_COST}, 'type': 'event-good'}, room=player.id)
                    for p_sid in scene_of_player.get_player_sids():
                        p = gm.get_player(p_sid)
                        if p: p.visible_tiles_cache = gm.calculate_fov(p.x, p.y, scene_of_player, SENSE_SIGHT_RANGE)
            elif action_type == 'drink_potion': player.drink_potion(gm.socketio)
            elif action_type == 'say':
                message_text = details.get('message', '');
                if message_text:
                    chat_data = { 'sender_id': player.id, 'sender_name': player.name, 'message': message_text, 'type': 'say', 'scene_coords': f"({player.scene_x},{player.scene_y})" }
                    if (player.scene_x, player.scene_y) in gm.scenes:
                        for target_sid in scene_of_player.get_player_sids(): gm.socketio.emit('chat_message', chat_data, room=target_sid)
            elif action_type == 'shout':
                message_text = details.get('message', '')
                if message_text:
                    if player.spend_mana(SHOUT_MANA_COST):
                        chat_data = { 'sender_id': player.id, 'sender_name': player.name, 'message': message_text, 'type': 'shout', 'scene_coords': f"({player.scene_x},{player.scene_y})" }
                        for target_player_obj in list(gm.players.values()):
                            if abs(target_player_obj.scene_x - player.scene_x) <= 1 and \
                               abs(target_player_obj.scene_y - player.scene_y) <= 1:
                                gm.socketio.emit('chat_message', chat_data, room=target_player_obj.id)
                        gm.socketio.emit('lore_message', {'messageKey': 'LORE.VOICE_BOOM_SHOUT', 'placeholders': {'manaCost': SHOUT_MANA_COST}, 'type': 'system'}, room=player.id)
                    else:
                        gm.socketio.emit('lore_message', {'messageKey': 'LORE.LACK_MANA_SHOUT', 'placeholders': {'manaCost': SHOUT_MANA_COST}, 'type': 'event-bad'}, room=player.id)
            processed_sids.add(sid_action)

def get_game_manager():
    global game_manager_instance
    if game_manager_instance is None:
        with app.app_context():
             app.logger.info("Initializing GameManager instance...")
             game_manager_instance = GameManager(socketio_instance=sio)
    return game_manager_instance

def _game_loop_iteration_content(): # ... (same as last response) ...
    gm = get_game_manager()
    gm.loop_iteration_count += 1
    loop_count = gm.loop_iteration_count
    try: gm.process_actions()
    except Exception as e: app.logger.error(f"Heartbeat {loop_count}: EXCEPTION in process_actions: {e}", exc_info=True)
    try: # Mana Regen
        gm.heartbeats_until_mana_regen -=1
        if gm.heartbeats_until_mana_regen <= 0:
            for player_obj in list(gm.players.values()):
                pixie_boost_for_player = 0
                player_scene_obj = gm.get_or_create_scene(player_obj.scene_x, player_obj.scene_y)
                for npc_id in player_scene_obj.get_npc_ids():
                    npc = gm.get_npc(npc_id)
                    if npc and isinstance(npc, ManaPixie):
                        dist = abs(player_obj.x - npc.x) + abs(player_obj.y - npc.y)
                        if dist <= PIXIE_PROXIMITY_FOR_BOOST: pixie_boost_for_player += PIXIE_MANA_REGEN_BOOST
                player_obj.regenerate_mana(BASE_MANA_REGEN_PER_HEARTBEAT_CYCLE, pixie_boost_for_player, sio)
            gm.heartbeats_until_mana_regen = HEARTBEATS_PER_MANA_REGEN_CYCLE
    except Exception as e: app.logger.error(f"Heartbeat {loop_count}: EXCEPTION in mana_regen: {e}", exc_info=True)
    try: # Rain/Wetness
        if gm.server_is_raining:
            for player_obj in list(gm.players.values()):
                player_scene = gm.get_or_create_scene(player_obj.scene_x, player_obj.scene_y)
                if not player_scene.is_indoors and not player_obj.is_wet:
                    player_obj.set_wet_status(True, sio, reason="rain")
        for player_obj in list(gm.players.values()):
            player_scene = gm.get_or_create_scene(player_obj.scene_x, player_obj.scene_y)
            if player_obj.is_wet and (player_scene.is_indoors or not gm.server_is_raining):
                 player_obj.set_wet_status(False, sio, reason="indoors_or_dry_weather")
    except Exception as e: app.logger.error(f"Heartbeat {loop_count}: EXCEPTION in rain/wetness: {e}", exc_info=True)
    try: # Sensory Perception
        if loop_count % 5 == 0:
            for player_obj in list(gm.players.values()):
                scene_of_player = gm.get_or_create_scene(player_obj.scene_x, player_obj.scene_y)
                if not player_obj.visible_tiles_cache:
                     player_obj.visible_tiles_cache = gm.calculate_fov(player_obj.x, player_obj.y, scene_of_player, SENSE_SIGHT_RANGE)
                gm.process_sensory_perception(player_obj, scene_of_player)
    except Exception as e: app.logger.error(f"Heartbeat {loop_count}: EXCEPTION in sensory processing: {e}", exc_info=True)
    try: # NPC AI Updates
        for npc in list(gm.all_npcs.values()):
            scene_of_npc = gm.get_or_create_scene(npc.scene_x, npc.scene_y)
            if hasattr(npc, 'update_ai'):
                npc.update_ai(scene_of_npc, gm) # Pass gm instance
            elif hasattr(npc, 'wander'):
                npc.wander(scene_of_npc)
    except Exception as e: app.logger.error(f"Heartbeat {loop_count}: EXCEPTION in NPC AI updates: {e}", exc_info=True)
    try: # Game State Emission
        if gm.players:
            current_players_snapshot = list(gm.players.values())
            num_updates_sent_this_heartbeat = 0
            for recipient_player in current_players_snapshot:
                if recipient_player.id not in gm.players: continue
                all_visible_tiles_list = [{'x': tile[0], 'y': tile[1]} for tile in recipient_player.visible_tiles_cache]
                payload_for_client = {
                    'self_player_data': recipient_player.get_full_data(),
                    'visible_other_players': gm.get_visible_players_for_observer(recipient_player),
                    'visible_npcs': gm.get_visible_npcs_for_observer(recipient_player),
                    'visible_trees': gm.get_visible_trees_for_observer(recipient_player),
                    'visible_terrain': gm.get_or_create_scene(recipient_player.scene_x, recipient_player.scene_y).get_terrain_for_payload(recipient_player.visible_tiles_cache),
                    'all_visible_tiles': all_visible_tiles_list,
                }
                sio.emit('game_update', payload_for_client, room=recipient_player.id); num_updates_sent_this_heartbeat +=1
            if num_updates_sent_this_heartbeat > 0 and loop_count % 20 == 1:
                app.logger.debug(f"Heartbeat {loop_count}: Sent 'game_update' to {num_updates_sent_this_heartbeat} players.")
            elif len(current_players_snapshot) > 0 and num_updates_sent_this_heartbeat == 0 and loop_count % 20 == 1 :
                app.logger.debug(f"Heartbeat {loop_count}: Players present, but NO 'game_update' emitted.")
    except Exception as e: app.logger.error(f"Heartbeat {loop_count}: EXCEPTION in emitting game updates: {e}", exc_info=True)


def _persistent_game_loop_runner():
    gm = get_game_manager()
    with app.app_context():
        my_pid = os.getpid()
        app.logger.info(f"Persistent game loop runner starting in PID {my_pid}...")
        init_db_tables() # Initialize DB tables at the start of the game loop runner
        gm.loop_is_actually_running_flag = True
        gm.spawn_initial_npcs_and_entities()
        app.logger.info(f"PID {my_pid}: Initial NPCs and entities spawned. Beginning persistent game loop.")
    while gm.loop_is_actually_running_flag:
        loop_start_time = time.time()
        try:
            with app.app_context():
                _game_loop_iteration_content()
        except Exception as e:
            with app.app_context():
                app.logger.critical(f"PID {os.getpid()} Heartbeat {gm.loop_iteration_count}: CRITICAL UNCAUGHT EXCEPTION: {e}", exc_info=True)
            eventlet.sleep(1.0)
        elapsed_time = time.time() - loop_start_time
        sleep_duration = GAME_HEARTBEAT_RATE - elapsed_time
        if sleep_duration < 0:
            with app.app_context():
                app.logger.warning(f"PID {os.getpid()} Heartbeat {gm.loop_iteration_count}: Iteration too long ({elapsed_time:.4f}s). No sleep.")
            sleep_duration = 0.0001
        eventlet.sleep(sleep_duration)
    with app.app_context():
        app.logger.info(f"PID {os.getpid()}: Persistent game loop runner terminating.")

def start_game_loop_for_worker():
    global _game_loop_started_in_this_process
    gm = get_game_manager()
    with app.app_context():
        my_pid = os.getpid()
        if not _game_loop_started_in_this_process:
            app.logger.info(f"PID {my_pid} Worker: Attempting to start game loop via _persistent_game_loop_runner...")
            try:
                gm.game_loop_greenlet = eventlet.spawn(_persistent_game_loop_runner)
                _game_loop_started_in_this_process = True
                app.logger.info(f"PID {my_pid} Worker: Game loop greenlet successfully spawned.")
            except Exception as e:
                app.logger.critical(f"PID {my_pid} Worker: FAILED TO START GAME LOOP GREENLET: {e}", exc_info=True)
        else:
            app.logger.info(f"PID {my_pid} Worker: Game loop already marked as started in this process.")

game_blueprint = Blueprint('game', __name__, template_folder='templates', static_folder='static', static_url_path='/static/game')
@game_blueprint.route('/')
def index_route(): return render_template('index.html')
app.register_blueprint(game_blueprint, url_prefix=GAME_PATH_PREFIX)
sio.init_app(app, path=f"{GAME_PATH_PREFIX}/socket.io")
@app.route('/')
def health_check_route(): return "OK", 200

@sio.on('connect')
def handle_connect_event(auth=None):
    gm = get_game_manager()
    with app.app_context():
        player = gm.add_player(request.sid)
        app.logger.info(f"Connect: {player.name} ({request.sid}). Total players: {len(gm.players)}")
        current_scene = gm.get_or_create_scene(player.scene_x, player.scene_y)
        all_visible_tiles_list = [{'x': tile[0], 'y': tile[1]} for tile in player.visible_tiles_cache]
        emit_ctx('initial_game_data', {
            'player_data': player.get_full_data(),
            'other_players_in_scene': gm.get_visible_players_for_observer(player),
            'visible_npcs': gm.get_visible_npcs_for_observer(player),
            'visible_trees': gm.get_visible_trees_for_observer(player),
            'visible_terrain': current_scene.get_terrain_for_payload(player.visible_tiles_cache),
            'all_visible_tiles': all_visible_tiles_list,
            'grid_width': GRID_WIDTH, 'grid_height': GRID_HEIGHT,
            'tick_rate': GAME_HEARTBEAT_RATE, 'default_rain_intensity': DEFAULT_RAIN_INTENSITY,
            'tree_char': TREE_CHAR, 'elf_char': ELF_CHAR
        })
        emit_ctx('lore_message', {'messageKey': "LORE.WELCOME_INITIAL", 'type': 'welcome-message'}, room=request.sid)

@sio.on('disconnect')
def handle_disconnect_event(*args):
    gm = get_game_manager()
    with app.app_context():
        player_left = gm.remove_player(request.sid) # remove_player now saves to DB
        if player_left:
            app.logger.info(f"Disconnect: {player_left.name} ({request.sid}) state saved. Total players: {len(gm.players)}")
        else:
            app.logger.info(f"Disconnect for SID {request.sid} (player not found or already removed).")

@sio.on('queue_player_action')
def handle_queue_player_action(data):
    gm = get_game_manager()
    with app.app_context():
        player = gm.get_player(request.sid)
        if not player:
            app.logger.warning(f"Action received from unknown SID: {request.sid}")
            emit_ctx('action_feedback', {'success': False, 'message': "Player not recognized."}); return
        action_type = data.get('type')
        valid_actions = ['move', 'look', 'drink_potion', 'say', 'shout', 'build_wall', 'destroy_wall', 'chop_tree']
        if action_type not in valid_actions:
            app.logger.warning(f"Player {player.name} sent invalid action type: {action_type}")
            emit_ctx('action_feedback', {'success': False, 'messageKey': 'ACTION_SENT_FEEDBACK.ACTION_FAILED_UNKNOWN_COMMAND', 'placeholders': {'actionWord': action_type}}); return
        gm.queued_actions[request.sid] = data
        emit_ctx('action_feedback', {'success': True, 'messageKey': 'ACTION_SENT_FEEDBACK.ACTION_QUEUED'})

if __name__ == '__main__':
    app.logger.info(f"Starting Flask-SocketIO server for LOCAL DEVELOPMENT on PID {os.getpid()}...")
    start_game_loop_for_worker()
    sio.run(app,
            debug=True, # Enable Flask debug for local dev
            host='0.0.0.0',
            port=int(os.environ.get('PORT', 5000)),
            use_reloader=False) # Important with eventlet.spawn
else:
    app.logger.info(f"App module loaded by WSGI server (e.g., Gunicorn) in PID {os.getpid()}. Game loop to be started by post_fork.")
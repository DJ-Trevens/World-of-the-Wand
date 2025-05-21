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
GRID_WIDTH = 27
GRID_HEIGHT = 17
GAME_HEARTBEAT_RATE = 0.75
SHOUT_MANA_COST = 5
MAX_VIEW_DISTANCE = 8
_game_loop_started_in_this_process = False
DESTROY_WALL_MANA_COST = 10
CHOP_TREE_MANA_COST = 15
INITIAL_POTIONS_DB = 3
INITIAL_WALL_ITEMS_DB = 3

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
DATABASE_URL = os.environ.get('DATABASE_URL')

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
# Initial log message moved to after game_manager is confirmed or within app context

sio = SocketIO(logger = False, engineio_logger = False, async_mode = "eventlet")
game_manager_instance = None # Global placeholder

def get_player_name(sid): # Wizard names attached to accounts in the future.
    return f"Wizard-{sid[:4]}"

def get_db_connection():
    if not DATABASE_URL:
        app.logger.error("DATABASE_URL environment variable not set.")
        return None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        app.logger.error(f"Error connecting to database: {e}", exc_info = True)
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
                    player_id VARCHAR(255) PRIMARY KEY, name VARCHAR(255),
                    scene_x INTEGER DEFAULT 0, scene_y INTEGER DEFAULT 0,
                    x INTEGER DEFAULT %s, y INTEGER DEFAULT %s,
                    char VARCHAR(1) DEFAULT '^', current_health INTEGER DEFAULT 100,
                    max_health INTEGER DEFAULT 100, current_mana REAL DEFAULT 175.0,
                    max_mana INTEGER DEFAULT 175, potions INTEGER DEFAULT %s,
                    walls INTEGER DEFAULT %s, gold INTEGER DEFAULT 0,
                    is_wet BOOLEAN DEFAULT FALSE, last_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """, (GRID_WIDTH // 2, GRID_HEIGHT // 2, INITIAL_POTIONS_DB, INITIAL_WALL_ITEMS_DB))
            cur.execute("""
                CREATE TABLE IF NOT EXISTS trees (
                    tree_id VARCHAR(255) PRIMARY KEY, scene_x INTEGER, scene_y INTEGER,
                    x INTEGER, y INTEGER, species VARCHAR(50), is_ancient BOOLEAN,
                    is_chopped_down BOOLEAN DEFAULT FALSE, name VARCHAR(255), lore_name VARCHAR(255),
                    elf_guardian_ids TEXT DEFAULT ''
                );
            """)
            conn.commit()
        app.logger.info("Database tables checked/created successfully.")
    except Exception as e:
        app.logger.error(f"Error initializing database tables: {e}", exc_info = True)
    finally:
        if conn: conn.close()

class Tree:
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
            'id': self.id,
            'type': self.type,
            'char': self.char,
            'x': self.x,
            'y': self.y,
            'species': self.species,
            'is_ancient': self.is_ancient,
            'scene_x': self.scene_x,
            'scene_y': self.scene_y,
            'is_chopped_down': self.is_chopped_down,
            'name': self.name,
            'lore_name': self.lore_name,
            'elf_guardian_ids': self.elf_guardian_ids
        }
    def save_to_db(self):
        conn = get_db_connection()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                elf_ids_str = ",".join(self.elf_guardian_ids)
                cur.execute("""
                    INSERT INTO trees (tree_id, scene_x, scene_y, x, y, species, is_ancient, is_chopped_down, name, lore_name, elf_guardian_ids)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (tree_id) DO UPDATE SET
                        is_chopped_down = EXCLUDED.is_chopped_down, elf_guardian_ids = EXCLUDED.elf_guardian_ids;
                """, (self.id, self.scene_x, self.scene_y, self.x, self.y, self.species, self.is_ancient, self.is_chopped_down, self.name, self.lore_name, elf_ids_str))
                conn.commit()
        except Exception as e:
            app.logger.error(f"Error saving tree {self.id} to DB: {e}", exc_info = True)
        finally:
            if conn:
                conn.close()

class ManaPixie:
    def __init__(self, scene_x, scene_y, initial_x = None, initial_y = None):
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
            'sound': [('SENSORY.PIXIE_SOUND_CHIME', 0.7, 5),('SENSORY.PIXIE_SOUND_WINGS', 0.4, 3)],
            'smell': [('SENSORY.PIXIE_SMELL_OZONE', 0.3, 2)],
            'magic': [('SENSORY.PIXIE_MAGIC_AURA', 0.9, 4)]}
        self.is_hidden = False
    def get_public_data(self):
        return {
            'id': self.id,
            'name': self.name,
            'char': self.char,
            'x': self.x,
            'y': self.y,
            'scene_x': self.scene_x,
            'scene_y': self.scene_y,
            'type': self.type
        }
    def wander(self, scene):
        if random.random() < 0.3:
            dx, dy = random.choice([-1, 0, 1]), random.choice([-1, 0, 1])
            if dx == 0 and dy == 0:
                return
            new_x, new_y = self.x + dx, self.y + dy
            if scene.is_walkable(new_x, new_y) and not scene.is_entity_at(new_x, new_y, exclude_id = self.id):
                self.x, self.y = new_x, new_y
    def attempt_evade(self, player_x, player_y, scene):
        possible_moves = []
        for dx_evade in [-1, 0, 1]:
            for dy_evade in [-1, 0, 1]:
                if dx_evade == 0 and dy_evade == 0:
                    continue
                evade_x, evade_y = self.x + dx_evade, self.y + dy_evade
                if scene.is_walkable(evade_x, evade_y) and not scene.is_entity_at(evade_x, evade_y, exclude_id = self.id):
                    possible_moves.append((evade_x, evade_y))
        if possible_moves:
            self.x, self.y = random.choice(possible_moves)
            return True
        return False

class Elf:
    def __init__(self, scene_x, scene_y, initial_x = None, initial_y = None, home_tree_id = None):
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
        self.sensory_cues = {'sight': [('SENSORY.ELF_SIGHT_GRACEFUL', 0.7, SENSE_SIGHT_RANGE)], 'sound': [('SENSORY.ELF_SOUND_RUSTLE', 0.5, 4), ('SENSORY.ELF_SOUND_SOFT_SONG', 0.2, 6)], 'smell': [('SENSORY.ELF_SMELL_PINE', 0.4, 3)], 'magic': [('SENSORY.ELF_MAGIC_NATURE', 0.6, 3)]}
        self.is_hidden_by_tree = False
    def get_public_data(self):
        return {
            'id': self.id,
            'name': self.name,
            'char': self.char,
            'type': self.type,
            'x': self.x,
            'y': self.y,
            'scene_x': self.scene_x,
            'scene_y': self.scene_y,
            'is_sneaking': self.is_sneaking,
            'state': self.state,
            'is_hidden_by_tree': self.is_hidden_by_tree
        }
    def update_ai(self, scene, game_manager):
        home_tree = game_manager.get_tree(self.home_tree_id) if self.home_tree_id else None
        if self.state == "distressed_no_tree":
            if random.random() < 0.05:
                self.wander_randomly(scene)
            return
        if self.state == "wandering_near_tree":
            if home_tree and not home_tree.is_chopped_down:
                self.wander_near_tree(scene, home_tree)
            else:
                self.state = "distressed_no_tree"
                self.wander_randomly(scene)
        self.is_hidden_by_tree = bool(home_tree and not home_tree.is_chopped_down and self.x == home_tree.x and self.y == home_tree.y)
    def wander_near_tree(self, scene, tree):
        WANDER_RADIUS = 4
        if random.random() < 0.2:
            dist = math.sqrt((self.x - tree.x) ** 2 + (self.y - tree.y) ** 2)
            dx, dy = (0, 0)
            if dist > WANDER_RADIUS:
                dx = 1 if self.x < tree.x else -1 if self.x > tree.x else 0
                dy = 1 if self.y < tree.y else -1 if self.y > tree.y else 0
            else:
                dx, dy = random.choice([-1, 0, 1]),random.choice([-1, 0, 1])
            if dx == 0 and dy == 0:
                return
            nx, ny = self.x + dx, self.y + dy
            if math.sqrt((nx - tree.x) ** 2 + (ny - tree.y) ** 2) > WANDER_RADIUS + 1:
                return
            if scene.is_walkable(nx, ny) and not scene.is_entity_at(nx, ny, exclude_id = self.id):
                self.x, self.y = nx, ny
    def wander_randomly(self, scene):
        if random.random() < 0.15:
            dx, dy = random.choice([-1, 0, 1]),random.choice([-1, 0, 1])
            if dx == 0 and dy == 0:
                return
            nx, ny = self.x + dx, self.y + dy
            if scene.is_walkable(nx, ny) and not scene.is_entity_at(nx, ny, exclude_id = self.id):
                self.x, self.y = nx, ny

class Player:
    def __init__(self, sid, name, db_data = None):
        self.id = sid
        self.name = name
        if db_data:
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
        else:
            self.scene_x = 0
            self.scene_y = 0
            self.x = GRID_WIDTH // 2
            self.y = GRID_HEIGHT // 2
            self.char = random.choice(['^', 'v', '<', '>'])
            self.max_health = 100
            self.current_health = 100
            self.max_mana = 175
            self.current_mana = 175.0
            self.potions = INITIAL_POTIONS_DB
            self.walls = INITIAL_WALL_ITEMS_DB
            self.gold = 0
            self.is_wet = False
        self.time_became_wet = 0
        self.mana_regen_accumulator = 0.0
        self.visible_tiles_cache = set()
    def save_to_db(self):
        conn = get_db_connection()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO players (player_id, name, scene_x, scene_y, x, y, char, current_health, max_health, current_mana, max_mana, potions, walls, gold, is_wet, last_seen)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
                    ON CONFLICT (player_id) DO UPDATE SET
                        name=EXCLUDED.name, scene_x=EXCLUDED.scene_x, scene_y=EXCLUDED.scene_y,
                        x=EXCLUDED.x, y=EXCLUDED.y, char=EXCLUDED.char, current_health=EXCLUDED.current_health,
                        max_health=EXCLUDED.max_health, current_mana=EXCLUDED.current_mana, max_mana=EXCLUDED.max_mana,
                        potions=EXCLUDED.potions, walls=EXCLUDED.walls, gold=EXCLUDED.gold, is_wet=EXCLUDED.is_wet,
                        last_seen=CURRENT_TIMESTAMP;
                """, (self.id,self.name,self.scene_x,self.scene_y,self.x,self.y,self.char,self.current_health,self.max_health,self.current_mana,self.max_mana,self.potions,self.walls,self.gold,self.is_wet))
                conn.commit()
            app.logger.debug(f"Saved player {self.name} ({self.id}) to DB.")
        except Exception as e:
            app.logger.error(f"Error saving player {self.name} ({self.id}) to DB: {e}", exc_info = True)
        finally:
            if conn:
                conn.close()
    def update_position(self, dx, dy, new_char, gm, sio_inst):
        osx, osy = self.scene_x, self.scene_y
        ox, oy = self.x, self.y
        scf = False
        tk = None
        nx, ny = self.x + dx, self.y + dy
        if nx < 0:
            self.scene_x -= 1
            self.x = GRID_WIDTH - 1
            scf = True
            tk = 'LORE.SCENE_TRANSITION_WEST'
        elif nx >= GRID_WIDTH:
            self.scene_x += 1
            self.x = 0
            scf = True
            tk = 'LORE.SCENE_TRANSITION_EAST'
        else: self.x = nx
        if ny < 0:
            self.scene_y -= 1
            self.y = GRID_HEIGHT - 1
            scf = True
            if not tk:
                tk = 'LORE.SCENE_TRANSITION_NORTH'
        elif ny >= GRID_HEIGHT:
            self.scene_y += 1
            self.y = 0
            scf = True
            if not tk:
                tk = 'LORE.SCENE_TRANSITION_SOUTH'
        else:
            self.y = ny
        char_changed = self.char != new_char
        self.char = new_char
        if scf:
            gm.handle_player_scene_change(self, osx, osy)
            if tk:
                sio_inst.emit('lore_message', {'messageKey': tk, 'placeholders': {'scene_x': self.scene_x, 'scene_y': self.scene_y}, 'type': 'system'}, room = self.id)
        elif self.x != ox or self.y != oy or char_changed:
            cs = gm.get_or_create_scene(self.scene_x, self.scene_y)
            self.visible_tiles_cache = gm.calculate_fov(self.x, self.y, cs, SENSE_SIGHT_RANGE)
        return scf or (self.x != ox or self.y != oy or char_changed)
    def drink_potion(self, sio_inst):
        if self.potions > 0:
            self.potions -= 1
            self.current_health = min(self.max_health, self.current_health + 15)
            sio_inst.emit('lore_message', {'messageKey': 'LORE.POTION_DRINK_SUCCESS', 'type': 'event-good'}, room = self.id)
            return True
        else:
            sio_inst.emit('lore_message', {'messageKey': 'LORE.POTION_DRINK_FAIL_EMPTY', 'type': 'event-bad'}, room = self.id)
            return False
    def can_afford_mana(self, cost):
        return self.current_mana >= cost
    def spend_mana(self, cost):
        if self.can_afford_mana(cost):
            self.current_mana -= cost
            return True
        return False
    def has_wall_items(self):
        return self.walls > 0
    def use_wall_item(self):
        if self.has_wall_items():
            self.walls -= 1
            return True
        return False
    def add_wall_item(self):
        self.walls += 1
    def set_wet_status(self, status, sio_inst, reason = "unknown"):
        if self.is_wet != status:
            self.is_wet = status
            if status:
                self.time_became_wet = time.time()
                if reason == "water_tile":
                    sio_inst.emit('player_event', {'type': 'stepped_in_water', 'sid': self.id}, room = self.id)
                    sio_inst.emit('lore_message', {'messageKey': 'LORE.BECAME_WET_WATER', 'type': 'system'}, room = self.id)
                elif reason == "rain":
                    sio_inst.emit('lore_message', {'messageKey': 'LORE.BECAME_WET_RAIN', 'type': 'system'}, room = self.id)
            else:
                sio_inst.emit('lore_message',{'messageKey':'LORE.BECAME_DRY','type':'system'},room=self.id)
    def regenerate_mana(self, base_regen, pixie_boost, sio_inst):
        total_regen = base_regen + pixie_boost
        self.mana_regen_accumulator += total_regen
        if self.mana_regen_accumulator >= 1.0:
            mana_add = int(self.mana_regen_accumulator)
            self.current_mana = min(self.max_mana, self.current_mana + mana_add)
            self.mana_regen_accumulator -= mana_add
            if pixie_boost > 0 and mana_add > 0:
                sio_inst.emit('lore_message', {'messageKey': 'LORE.PIXIE_MANA_BOOST', 'type': 'event-good', 'placeholders': {'amount': mana_add}}, room = self.id)
    def get_public_data(self):
        return {
            'id': self.id,
            'name': self.name,
            'x': self.x,
            'y': self.y,
            'char': self.char,
            'scene_x': self.scene_x,
            'scene_y': self.scene_y,
            'is_wet': self.is_wet
        }
    def get_full_data(self):
        return {
            'id': self.id,
            'name': self.name,
            'scene_x': self.scene_x,
            'scene_y': self.scene_y,
            'x': self.x,
            'y': self.y,
            'char': self.char,
            'max_health': self.max_health,
            'current_health': self.current_health,
            'max_mana': self.max_mana,
            'current_mana': int(self.current_mana),
            'potions': self.potions,
            'gold': self.gold,
            'walls': self.walls,
            'is_wet': self.is_wet
        }

class Scene:
    def __init__(self, scene_x, scene_y, name_gen = None):
        self.scene_x = scene_x
        self.scene_y = scene_y
        self.name = f"Area ({scene_x}, {scene_y})"
        if name_gen:
            self.name = name_gen(scene_x, scene_y)
        self.players_sids = set()
        self.npc_ids = set()
        self.tree_ids = set()
        self.terrain_grid = [[TILE_FLOOR for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
        self.is_indoors = False
        self.game_manager_ref = get_game_manager()
    def add_player(self, pid):
        self.players_sids.add(pid)
    def remove_player(self, pid):
        self.players_sids.discard(pid)
    def get_player_sids(self):
        return list(self.players_sids)
    def add_npc(self, nid):
        self.npc_ids.add(nid)
    def remove_npc(self, nid):
        self.npc_ids.discard(nid)
    def get_npc_ids(self):
        return list(self.npc_ids)
    def add_tree(self, tid):
        self.tree_ids.add(tid)
    def remove_tree(self, tid):
        self.tree_ids.discard(tid)
    def get_tree_ids(self):
        return list(self.tree_ids)
    def get_tile_type(self, x, y):
        if 0 <= y < GRID_HEIGHT and 0 <= x < GRID_WIDTH:
            return self.terrain_grid[y][x]
        return TILE_WALL
    def is_transparent(self, x, y):
        if not(0 <= x < GRID_WIDTH and 0 <= y < GRID_HEIGHT):
            return False
        gm = get_game_manager()
        if gm and gm.get_tree_at(x, y, self.scene_x, self.scene_y):
            tree = gm.get_tree_at(x, y, self.scene_x, self.scene_y)
            if tree and not tree.is_chopped_down:
                return False
        tile_type = self.terrain_grid[y][x]
        return tile_type == TILE_FLOOR or tile_type == TILE_WATER
    def is_walkable(self, x, y):
        if not(0 <= x < GRID_WIDTH and 0 <= y < GRID_HEIGHT):
            return False
        tile_type = self.get_tile_type(x, y)
        gm = get_game_manager()
        if gm:
            tree = gm.get_tree_at(x, y, self.scene_x, self.scene_y)
            if tree and not tree.is_chopped_down:
                return False
        return tile_type == TILE_FLOOR or tile_type == TILE_WATER
    def set_tile_type(self,x,y,tt):
        if 0 <= y < GRID_HEIGHT and 0 <= x < GRID_WIDTH:
            self.terrain_grid[y][x] = tt
            return True
        return False
    def get_terrain_for_payload(self,visible_tiles):
        td = {'walls': [], 'water': []}
        if not visible_tiles:
            return td
        for r, row in enumerate(self.terrain_grid):
            for c, tt in enumerate(row):
                if(c, r) in visible_tiles:
                    if tt == TILE_WALL:
                        td['walls'].append({'x': c, 'y': r})
                    elif tt == TILE_WATER:
                        td['water'].append({'x': c, 'y': r})
        return td
    def is_entity_at(self, x, y, exclude_id = None):
        gm = get_game_manager()
        if self.is_npc_at(x,y,exclude_id):
            return True
        if self.is_player_at(x, y):
            return True
        tree = gm.get_tree_at(x, y, self.scene_x, self.scene_y)
        if tree and not tree.is_chopped_down and tree.id != exclude_id:
            return True
        return False
    def is_npc_at(self, x, y, exclude_id = None):
        gm = get_game_manager()
        if not gm:
            return False
        for nid in self.npc_ids:
            if exclude_id and nid == exclude_id:
                continue
            npc = gm.get_npc(nid)
            if npc and npc.x == x and npc.y == y:
                return True
        return False
    def is_player_at(self, x, y, pid_check = None):
        gm = get_game_manager()
        if not gm:
            return False
        for psid in self.players_sids:
            player = gm.get_player(psid)
            if player and player.x == x and player.y == y:
                return True
        return False

class GameManager:
    def __init__(self,sio_inst):
        self.players = {}
        self.scenes = {}
        self.all_npcs = {}
        self.all_trees = {}
        self.queued_actions = {}
        self.socketio = sio_inst
        self.server_is_raining = SERVER_IS_RAINING
        self.heartbeats_until_mana_regen = HEARTBEATS_PER_MANA_REGEN_CYCLE
        self.loop_is_actually_running_flag = False
        self.game_loop_greenlet = None
        self.loop_iteration_count = 0
        self._fov_octant_transforms=[
            (1,0,0,1), (0,1,1,0), (0,-1,1,0), (-1,0,0,1),
            (-1,0,0,-1), (0,-1,-1,0), (0,1,-1,0), (1,0,0,-1)
        ]
        self.load_all_trees_from_db()
    def load_all_trees_from_db(self):
        conn = get_db_connection()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT tree_id, scene_x, scene_y, x, y, species, is_ancient, is_chopped_down, name, lore_name, elf_guardian_ids FROM trees")
                for row in cur.fetchall():
                    tid, sx, sy, x, y, sp, ia, ic, n, ln, eids_str = row
                    tree = Tree(sx, sy, x, y, tid, sp, ia, ic, n, eids_str)
                    self.all_trees[tree.id] = tree
                    scene = self.get_or_create_scene(sx, sy)
                    if tree.id not in scene.tree_ids:
                        scene.add_tree(tree.id)
                app.logger.info(f"Loaded {len(self.all_trees)} trees from DB.")
        except Exception as e:
            app.logger.error(f"Error loading trees from DB: {e}", exc_info = True)
        finally:
            if conn:
                conn.close()
    def calculate_fov(self, ox, oy, scene, radius):
        vt = set()
        vt.add((ox, oy))
        for octant in range(8):
            self._cast_light_octant(ox, oy, radius, 1, 1.0, 0.0, octant, scene, vt)
        return vt
    def _cast_light_octant(self, cx, cy, radius, row_depth, start_slope, end_slope, octant, scene, visible_tiles):
        xx, xy, yx, yy = self._fov_octant_transforms[octant]
        rsq = radius * radius
        if start_slope < end_slope:
            return
        for i in range(row_depth, radius + 1):
            blocked = False
            dx, dy= -i, -i
            while dx <= 0:
                dx += 1
                mx = cx + dx * xx + dy * xy
                my = cy + dx * yx + dy * yy
                if not(0 <= mx < GRID_WIDTH and 0 <= my < GRID_HEIGHT):
                    continue
                ls = (dx - 0.5) / (dy + 0.5) if (dy + 0.5) != 0 else float('inf') * math.copysign(1, dx - 0.5)
                rs = (dx + 0.5) / (dy - 0.5) if (dy - 0.5) != 0 else float('inf') * math.copysign(1, dx + 0.5)
                if start_slope < rs:
                    continue
                elif end_slope > ls:
                    break
                if (dx * dx + dy * dy) < rsq:
                    visible_tiles.add((mx, my))
                if not scene.is_transparent(mx, my):
                    if blocked:
                        continue
                    else:
                        blocked = True
                        self._cast_light_octant(cx, cy, radius, i + 1, start_slope, ls, octant, scene, visible_tiles)
                        start_slope = rs
                else:
                    if blocked:
                        blocked = False
                        start_slope = rs
            if blocked:
                break
    def spawn_initial_npcs_and_entities(self):
        scene_0_0 = self.get_or_create_scene(0, 0)
        for i in range(2):
            px, py = random.randint(0, GRID_WIDTH - 1), random.randint(0, GRID_HEIGHT - 1)
            while not scene_0_0.is_walkable(px, py) or scene_0_0.is_entity_at(px, py):
                px, py = random.randint(0, GRID_WIDTH - 1), random.randint(0, GRID_HEIGHT - 1)
            pixie = ManaPixie(0, 0, initial_x = px, initial_y = py)
            self.all_npcs[pixie.id] = pixie
            scene_0_0.add_npc(pixie.id)
            app.logger.info(f"Spawned transient {pixie.type} {pixie.name} at S(0, 0) T({pixie.x}, {pixie.y})")
        if not any(t for t in self.all_trees.values() if t.scene_x == 0 and t.scene_y == 0):
            tx, ty = 5, 5
            while not scene_0_0.is_walkable(tx, ty) or scene_0_0.is_entity_at(tx, ty):
                tx, ty = random.randint(2, GRID_WIDTH - 3), random.randint(2, GRID_HEIGHT - 3)
            test_tree = Tree(0, 0, tx, ty)
            test_tree.save_to_db()
            self.all_trees[test_tree.id] = test_tree
            scene_0_0.add_tree(test_tree.id)
            app.logger.info(f"Spawned and saved {test_tree.type} {test_tree.name} at S(0, 0) T({test_tree.x}, {test_tree.y})")
            for i in range(2):
                ex, ey = test_tree.x, test_tree.y
                elf_here = False
                for eid_g in test_tree.elf_guardian_ids:
                    elf_e = self.get_npc(eid_g)
                    if elf_e and elf_e.x == ex and elf_e.y == ey:
                        elf_here = True
                        break
                if elf_here:
                    ex, ey = tx + random.choice([-1, 1]), ty + random.choice([-1, 1])
                    while not scene_0_0.is_walkable(ex, ey) or scene_0_0.is_entity_at(ex, ey):
                        ex, ey = tx + random.choice([-1, 0, 1]), ty + random.choice([-1, 0, 1])
                        if ex == tx and ey == ty:
                            ex, ey = tx + 1, ty
                elf = Elf(0, 0, initial_x = ex, initial_y = ey, home_tree_id = test_tree.id)
                self.all_npcs[elf.id] = elf
                scene_0_0.add_npc(elf.id)
                test_tree.elf_guardian_ids.append(elf.id)
            test_tree.save_to_db()
            app.logger.info(f"Spawned transient Elves for {test_tree.name}")
        else:
            app.logger.info("Trees already loaded/exist, skipping initial tree spawn.")
    def get_tree(self, tid):
        return self.all_trees.get(tid)
    def get_tree_at(self, x, y, sx, sy):
        for tobj in self.all_trees.values():
            if tobj.scene_x == sx and tobj.scene_y == sy and tobj.x == x and tobj.y == y:
                return tobj
        return None
    def get_visible_trees_for_observer(self, obs_p):
        vtd = []
        scene = self.get_or_create_scene(obs_p.scene_x, obs_p.scene_y)
        for tid in scene.get_tree_ids():
            tree = self.get_tree(tid)
            if tree and (tree.x, tree.y) in obs_p.visible_tiles_cache:
                vtd.append(tree.get_public_data())
        return vtd
    def setup_spawn_shrine(self, scene_obj):
        mid_x, mid_y = GRID_WIDTH // 2, GRID_HEIGHT // 2
        shrine_size = 2
        for i in range(-shrine_size, shrine_size + 1):
            scene_obj.set_tile_type(mid_x + i, mid_y - shrine_size, TILE_WALL)
            scene_obj.set_tile_type(mid_x + i, mid_y + shrine_size, TILE_WALL)
            if abs(i) < shrine_size:
                scene_obj.set_tile_type(mid_x - shrine_size, mid_y + i, TILE_WALL)
                scene_obj.set_tile_type(mid_x + shrine_size, mid_y + i, TILE_WALL)
        scene_obj.set_tile_type(mid_x, mid_y + shrine_size, TILE_FLOOR)
        scene_obj.set_tile_type(mid_x - (shrine_size + 2), mid_y, TILE_WATER)
        scene_obj.set_tile_type(mid_x - (shrine_size + 2), mid_y + 1, TILE_WATER)
        scene_obj.set_tile_type(mid_x + (shrine_size + 2), mid_y - 1, TILE_WATER)
    def get_or_create_scene(self, sx, sy):
        sc = (sx, sy)
        if sc not in self.scenes:
            ns = Scene(sx, sy)
            if sx == 0 and sy == 0:
                self.setup_spawn_shrine(ns)
            self.scenes[sc] = ns
            app.logger.info(f"Created new scene at ({sx}, {sy}): {ns.name}")
        return self.scenes[sc]
    def add_player(self,sid):
        name = get_player_name(sid)
        p_db_data = None
        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT scene_x, scene_y, x, y, char, current_health, max_health, current_mana, max_mana, potions, walls, gold, is_wet FROM players WHERE player_id=%s",(sid,))
                    row = cur.fetchone()
                    if row:
                        keys=['scene_x', 'scene_y', 'x', 'y', 'char', 'current_health', 'max_health', 'current_mana', 'max_mana', 'potions', 'walls', 'gold', 'is_wet'];p_db_data=dict(zip(keys,row));app.logger.info(f"Loaded player {name}({sid}) from DB.")
            except Exception as e:
                app.logger.error(f"Error loading player {name}({sid}) from DB: {e}",exc_info=True)
            finally:
                if conn:
                    conn.close()
        player = Player(sid, name, db_data = p_db_data)
        if not p_db_data:
            player.save_to_db()
            app.logger.info(f"Created new player {name}({sid}) and saved to DB.")
        self.players[sid] = player
        scene = self.get_or_create_scene(player.scene_x, player.scene_y)
        scene.add_player(sid)
        player.visible_tiles_cache = self.calculate_fov(player.x, player.y, scene, SENSE_SIGHT_RANGE)
        app.logger.info(f"Player {name} added to scene({player.scene_x}, {player.scene_y}). Total players: {len(self.players)}")
        new_p_data = player.get_public_data()
        for osid in scene.get_player_sids():
            if osid != sid:
                op = self.get_player(osid)
                if op and self.is_player_visible_to_observer(op,player):
                    self.socketio.emit('player_entered_your_scene', new_p_data, room = osid)
        return player
    def remove_player(self, sid):
        player = self.players.get(sid)
        if player:
            player.save_to_db()
            app.logger.info(f"Player {player.name} state saved on disconnect.")
        player = self.players.pop(sid, None)
        if sid in self.queued_actions:
            del self.queued_actions[sid]
        if player:
            osc = (player.scene_x, player.scene_y)
            if osc in self.scenes:
                scene = self.scenes[osc]
                scene.remove_player(sid)
                app.logger.info(f"Removed {player.name} from scene {osc}. Players in scene: {len(scene.get_player_sids())}")
                for osid in scene.get_player_sids():
                    self.socketio.emit('player_exited_your_scene', {'id': sid, 'name': player.name}, room = osid)
            return player
        return None
    def get_player(self, sid):
        return self.players.get(sid)
    def get_npc(self, nid):
        return self.all_npcs.get(nid)
    def get_npc_at(self, x, y, sx, sy):
        for npc_obj in self.all_npcs.values():
            if npc_obj.scene_x == sx and npc_obj.scene_y == sy and npc_obj.x == x and npc_obj.y == y:
                return npc_obj
        return None
    def get_player_at(self, x, y, sx, sy):
        for p_obj in self.players.values():
            if p_obj.scene_x == sx and p_obj.scene_y == sy and p_obj.x == x and p_obj.y == y:
                return p_obj
        return None
    def handle_player_scene_change(self, player, osx, osy):
        old_sc = (osx, osy)
        new_sc = (player.scene_x, player.scene_y)
        if old_sc != new_sc:
            if old_sc in self.scenes:
                old_so = self.scenes[old_sc]
                old_so.remove_player(player.id)
                app.logger.info(f"Player {player.name} left scene {old_sc}.")
                for osid in old_so.get_player_sids():
                    self.socketio.emit('player_exited_your_scene', {'id': player.id, 'name': player.name}, room = osid)
            new_so = self.get_or_create_scene(player.scene_x, player.scene_y)
            new_so.add_player(player.id)
            player.visible_tiles_cache = self.calculate_fov(player.x, player.y, new_so, SENSE_SIGHT_RANGE)
            app.logger.info(f"Player {player.name} entered scene {new_sc}. Terrain: {new_so.name}")
            p_pdata = player.get_public_data()
            for osid in new_so.get_player_sids():
                if osid != player.id:
                    op = self.get_player(osid)
                    if op and self.is_player_visible_to_observer(op, player):
                        self.socketio.emit('player_entered_your_scene', p_pdata, room = osid)
    def is_player_visible_to_observer(self, obs_p, target_p):
        if not obs_p or not target_p:
            return False
        if obs_p.id == target_p.id:
            return False
        if obs_p.scene_x != target_p.scene_x or obs_p.scene_y != target_p.scene_y:
            return False
        return (target_p.x, target_p.y) in obs_p.visible_tiles_cache
    def is_npc_visible_to_observer(self,obs_p,target_npc):
        if not obs_p or not target_npc:
            return False
        if obs_p.scene_x != target_npc.scene_x or obs_p.scene_y != target_npc.scene_y:
            return False
        if hasattr(target_npc, 'is_sneaking') and target_npc.is_sneaking:
            return False
        return (target_npc.x, target_npc.y) in obs_p.visible_tiles_cache
    def get_visible_players_for_observer(self, obs_p):
        vo=[]
        scene = self.get_or_create_scene(obs_p.scene_x, obs_p.scene_y)
        for tsid in scene.get_player_sids():
            if tsid == obs_p.id:
                continue
            tp = self.get_player(tsid)
            if tp and (tp.x, tp.y) in obs_p.visible_tiles_cache:
                vo.append(tp.get_public_data())
        return vo
    def get_visible_npcs_for_observer(self, obs_p):
        vnd=[]
        scene = self.get_or_create_scene(obs_p.scene_x, obs_p.scene_y)
        for nid in scene.get_npc_ids():
            npc = self.get_npc(nid)
            if not npc:
                continue
            if isinstance(npc, Elf) and npc.home_tree_id:
                ht = self.get_tree(npc.home_tree_id)
                npc.is_hidden_by_tree = bool(ht and not ht.is_chopped_down and npc.x == ht.x and npc.y == ht.y)
            else:
                npc.is_hidden_by_tree = False # Not strictly needed if client checks attribute existence
            if self.is_npc_visible_to_observer(obs_p, npc):
                vnd.append(npc.get_public_data())
        return vnd
    def get_target_coordinates(self, player, dx, dy):
        return player.x + dx, player.y + dy
    def get_general_direction(self, obs, target):
        dx = target.x - obs.x
        dy = target.y - obs.y
        if abs(dx) > abs(dy):
            return "to the East" if dx > 0 else "to the West"
        elif abs(dy) > abs(dx):
            return "to the South" if dy > 0 else "to the North"
        else:
            if dx == 0 and dy == 0:
                return "right here"
            if dx > 0 and dy > 0:
                return "to the SouthEast"
            elif dx < 0 and dy > 0:
                return "to the SouthWest"
            elif dx > 0 and dy < 0:
                return "to the NorthEast"
            elif dx < 0 and dy < 0:
                return "to the NorthWest"
            return "nearby"
    def process_sensory_perception(self, player, scene):
        pcts = set()
        for nid in scene.get_npc_ids():
            npc = self.get_npc(nid)
            if not npc or npc.is_hidden:
                continue
            if hasattr(npc, 'is_hidden_by_tree') and npc.is_hidden_by_tree:
                continue
            is_vis = (npc.x, npc.y) in player.visible_tiles_cache
            if hasattr(npc, 'is_sneaking') and npc.is_sneaking:
                is_vis = False
            dist = abs(player.x - npc.x) + abs(player.y - npc.y)
            if is_vis:
                for ck, rel, _ in npc.sensory_cues.get('sight', []):
                    if random.random() < (rel * 0.05) and ck not in pcts:
                        self.socketio.emit('lore_message', {'messageKey': ck, 'placeholders': {'npcName': npc.name}, 'type': 'sensory-sight'}, room = player.id)
                        pcts.add(ck)
                        break
            else:
                for stype in['sound', 'smell', 'magic']:
                    for ck, rel, crange in npc.sensory_cues.get(stype, []):
                        if dist <= crange:
                            pchance = rel * (1 - (dist / (crange + 1.0))) * 0.5
                            if random.random() < pchance and ck not in pcts:
                                self.socketio.emit('lore_message', {'messageKey': ck, 'placeholders': {'npcName': npc.name, 'direction': self.get_general_direction(player, npc)}, 'type': f'sensory-{stype}'}, room = player.id)
                                pcts.add(ck)
                                break
                        if ck in pcts:
                            break
    def process_actions(self, ):
        gm = get_game_manager()
        current_actions_to_process = dict(gm.queued_actions)
        gm.queued_actions.clear()
        processed_sids = set()
        for sid_action, action_data in current_actions_to_process.items():
            if sid_action in processed_sids:
                continue
            player = gm.get_player(sid_action)
            if not player:
                app.logger.warning(f"Action from non-existent player SID {sid_action}")
                continue
            action_type = action_data.get('type')
            details = action_data.get('details', {})
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
                                player.set_wet_status(True, gm.socketio, reason = "water_tile")
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
                    tree_to_chop.save_to_db()
                    gm.socketio.emit('lore_message', {'messageKey': 'LORE.CHOP_SUCCESS', 'placeholders': {'treeName': tree_to_chop.name, 'manaCost': CHOP_TREE_MANA_COST}, 'type': 'event-good'}, room=player.id)
                    for elf_id in tree_to_chop.elf_guardian_ids:
                        elf = gm.get_npc(elf_id)
                        if elf and isinstance(elf, Elf):
                            elf.state = "distressed_no_tree"
                            gm.socketio.emit('lore_message', {'messageKey': 'LORE.ELF_TREE_DESTROYED_REACTION', 'placeholders': {'elfName': elf.name, 'treeName': tree_to_chop.lore_name}, 'type': 'system-event-negative'}, room=player.id)
                    for p_sid in scene_of_player.get_player_sids():
                        p = gm.get_player(p_sid)
                        if p:
                            p.visible_tiles_cache = gm.calculate_fov(p.x, p.y, scene_of_player, SENSE_SIGHT_RANGE)
            elif action_type == 'build_wall':
                dx, dy = details.get('dx', 0), details.get('dy', 0)
                target_x, target_y = gm.get_target_coordinates(player, dx, dy)
                if not (0 <= target_x < GRID_WIDTH and 0 <= target_y < GRID_HEIGHT):
                    gm.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_FAIL_OUT_OF_BOUNDS', 'type': 'event-bad'}, room = player.id)
                elif not scene_of_player.is_walkable(target_x, target_y) or scene_of_player.get_tile_type(target_x, target_y) != TILE_FLOOR:
                    gm.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_FAIL_OBSTRUCTED', 'type': 'event-bad'}, room = player.id)
                elif gm.get_npc_at(target_x, target_y, player.scene_x, player.scene_y) or gm.get_player_at(target_x, target_y, player.scene_x, player.scene_y):
                    gm.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_FAIL_OBSTRUCTED', 'type': 'event-bad'}, room = player.id)
                elif not player.has_wall_items():
                    gm.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_FAIL_NO_MATERIALS', 'type': 'event-bad'}, room = player.id)
                else:
                    player.use_wall_item()
                    scene_of_player.set_tile_type(target_x, target_y, TILE_WALL)
                    gm.socketio.emit('lore_message', {'messageKey': 'LORE.BUILD_SUCCESS', 'placeholders': {'walls': player.walls}, 'type': 'event-good'}, room = player.id)
                    for p_sid in scene_of_player.get_player_sids():
                        p = gm.get_player(p_sid)
                        if p:
                            p.visible_tiles_cache = gm.calculate_fov(p.x, p.y, scene_of_player, SENSE_SIGHT_RANGE)
            elif action_type == 'destroy_wall':
                dx, dy = details.get('dx', 0), details.get('dy', 0)
                target_x, target_y = gm.get_target_coordinates(player, dx, dy)
                if not (0 <= target_x < GRID_WIDTH and 0 <= target_y < GRID_HEIGHT):
                    gm.socketio.emit('lore_message', {'messageKey': 'LORE.DESTROY_FAIL_OUT_OF_BOUNDS', 'type': 'event-bad'}, room = player.id)
                elif scene_of_player.get_tile_type(target_x, target_y) != TILE_WALL:
                    gm.socketio.emit('lore_message', {'messageKey': 'LORE.DESTROY_FAIL_NO_WALL', 'type': 'event-bad'}, room = player.id)
                elif not player.can_afford_mana(DESTROY_WALL_MANA_COST):
                    gm.socketio.emit('lore_message', {'messageKey': 'LORE.DESTROY_FAIL_NO_MANA', 'placeholders': {'manaCost': DESTROY_WALL_MANA_COST}, 'type': 'event-bad'}, room = player.id)
                else:
                    player.spend_mana(DESTROY_WALL_MANA_COST); player.add_wall_item(); scene_of_player.set_tile_type(target_x, target_y, TILE_FLOOR)
                    gm.socketio.emit('lore_message', {'messageKey': 'LORE.DESTROY_SUCCESS', 'placeholders': {'walls': player.walls, 'manaCost': DESTROY_WALL_MANA_COST}, 'type': 'event-good'}, room = player.id)
                    for p_sid in scene_of_player.get_player_sids():
                        p = gm.get_player(p_sid)
                        if p:
                            p.visible_tiles_cache = gm.calculate_fov(p.x, p.y, scene_of_player, SENSE_SIGHT_RANGE)
            elif action_type == 'drink_potion':
                player.drink_potion(gm.socketio)
            elif action_type == 'say':
                message_text = details.get('message', '')
                if message_text:
                    chat_data = {
                        'sender_id': player.id,
                        'sender_name': player.name,
                        'message': message_text,
                        'type': 'say',
                        'scene_coords': f"({player.scene_x}, {player.scene_y})"
                    }
                    if (player.scene_x, player.scene_y) in gm.scenes:
                        for target_sid in scene_of_player.get_player_sids():
                            gm.socketio.emit('chat_message', chat_data, room = target_sid)
            elif action_type == 'shout':
                message_text = details.get('message', '')
                if message_text:
                    if player.spend_mana(SHOUT_MANA_COST):
                        chat_data = {
                            'sender_id': player.id,
                            'sender_name': player.name,
                            'message': message_text,
                            'type': 'shout',
                            'scene_coords': f"({player.scene_x}, {player.scene_y})"
                        }
                        for target_player_obj in list(gm.players.values()):
                            if abs(target_player_obj.scene_x - player.scene_x) <= 1 and abs(target_player_obj.scene_y - player.scene_y) <= 1:
                                gm.socketio.emit('chat_message', chat_data, room = target_player_obj.id)
                        gm.socketio.emit('lore_message', {'messageKey': 'LORE.VOICE_BOOM_SHOUT', 'placeholders': {'manaCost': SHOUT_MANA_COST}, 'type': 'system'}, room = player.id)
                    else:
                        gm.socketio.emit('lore_message', {'messageKey': 'LORE.LACK_MANA_SHOUT', 'placeholders': {'manaCost': SHOUT_MANA_COST}, 'type': 'event-bad'}, room = player.id)
            processed_sids.add(sid_action)

def get_game_manager():
    global game_manager_instance
    if game_manager_instance is None:
        with app.app_context(): # Ensures logging and other app features are available during init
             init_db_tables()
             app.logger.info("Initializing GameManager instance for this worker/process...")
             game_manager_instance = GameManager(sio_inst = sio)
    return game_manager_instance

def _game_loop_iteration_content():
    gm = get_game_manager()
    gm.loop_iteration_count += 1
    loop_count = gm.loop_iteration_count
    try:
        gm.process_actions()
    except Exception as e:
        app.logger.error(f"H_ERR process_actions: {e}", exc_info = True)
    try:
        gm.heartbeats_until_mana_regen -= 1
        if gm.heartbeats_until_mana_regen <= 0:
            for p_obj in list(gm.players.values()):
                boost = 0
                scene_obj = gm.get_or_create_scene(p_obj.scene_x,p_obj.scene_y)
                for nid in scene_obj.get_npc_ids():
                    npc = gm.get_npc(nid)
                    if npc and isinstance(npc, ManaPixie) and abs(p_obj.x - npc.x) + abs(p_obj.y - npc.y) <= PIXIE_PROXIMITY_FOR_BOOST:
                        boost += PIXIE_MANA_REGEN_BOOST
                p_obj.regenerate_mana(BASE_MANA_REGEN_PER_HEARTBEAT_CYCLE, boost, sio)
            gm.heartbeats_until_mana_regen = HEARTBEATS_PER_MANA_REGEN_CYCLE
    except Exception as e:
        app.logger.error(f"H_ERR mana_regen: {e}", exc_info = True)
    try:
        if gm.server_is_raining:
            for p_obj in list(gm.players.values()):
                scene = gm.get_or_create_scene(p_obj.scene_x,p_obj.scene_y)
                if not scene.is_indoors and not p_obj.is_wet:
                    p_obj.set_wet_status(True, sio, "rain")
        for p_obj in list(gm.players.values()):
            scene = gm.get_or_create_scene(p_obj.scene_x, p_obj.scene_y)
            if p_obj.is_wet and (scene.is_indoors or not gm.server_is_raining):
                p_obj.set_wet_status(False, sio, "indoors_or_dry")
    except Exception as e:
        app.logger.error(f"H_ERR rain/wetness: {e}", exc_info = True)
    try:
        if loop_count % 5 == 0:
            for p_obj in list(gm.players.values()):
                scene = gm.get_or_create_scene(p_obj.scene_x, p_obj.scene_y)
                if not p_obj.visible_tiles_cache:
                    p_obj.visible_tiles_cache = gm.calculate_fov(p_obj.x, p_obj.y, scene, SENSE_SIGHT_RANGE)
                gm.process_sensory_perception(p_obj, scene)
    except Exception as e:
        app.logger.error(f"H_ERR sensory: {e}", exc_info = True)
    try:
        for npc in list(gm.all_npcs.values()):
            scene = gm.get_or_create_scene(npc.scene_x, npc.scene_y)
            if hasattr(npc, 'update_ai'):
                npc.update_ai(scene, gm)
            elif hasattr(npc, 'wander'):
                npc.wander(scene)
    except Exception as e:
        app.logger.error(f"H_ERR npc_ai: {e}", exc_info = True)
    try:
        if gm.players:
            snap = list(gm.players.values())
            updates = 0
            for rp in snap:
                if rp.id not in gm.players:
                    continue
                vis_tiles = [{'x': t[0], 'y': t[1]} for t in rp.visible_tiles_cache]
                payload = {
                    'self_player_data': rp.get_full_data(),
                    'visible_other_players': gm.get_visible_players_for_observer(rp),
                    'visible_npcs': gm.get_visible_npcs_for_observer(rp),
                    'visible_trees': gm.get_visible_trees_for_observer(rp),
                    'visible_terrain': gm.get_or_create_scene(rp.scene_x,rp.scene_y).get_terrain_for_payload(rp.visible_tiles_cache),
                    'all_visible_tiles': vis_tiles
                }
                sio.emit('game_update', payload, room = rp.id)
                updates += 1
            if updates > 0 and loop_count % 20 == 1:
                app.logger.debug(f"H {loop_count}: Sent 'game_update' to {updates} players.")
            elif len(snap) > 0 and updates == 0 and loop_count % 20 == 1:
                app.logger.debug(f"H {loop_count}: Players present, NO 'game_update' sent.")
    except Exception as e:
        app.logger.error(f"H_ERR emit_updates: {e}", exc_info = True)

def _persistent_game_loop_runner():
    gm = get_game_manager()
    with app.app_context():
        pid = os.getpid()
        app.logger.info(f"Persistent game loop runner starting in PID {pid}...")
        init_db_tables()
        gm.loop_is_actually_running_flag = True
        gm.spawn_initial_npcs_and_entities()
        app.logger.info(f"PID {pid}: Initial setup complete. Beginning persistent game loop.")
    while gm.loop_is_actually_running_flag:
        start_time = time.time()
        try:
            with app.app_context():
                _game_loop_iteration_content()
        except Exception as e:
            with app.app_context():
                app.logger.critical(f"PID {os.getpid()} H {gm.loop_iteration_count}: UNCAUGHT EXCEPTION IN ITERATION: {e}", exc_info = True)
            eventlet.sleep(1.0)
        elapsed = time.time() - start_time
        sleep_for = GAME_HEARTBEAT_RATE - elapsed
        if sleep_for < 0:
            with app.app_context():
                app.logger.warning(f"PID {os.getpid()} H {gm.loop_iteration_count}: Iteration too long ({elapsed:.4f}s). No sleep.")
            sleep_for = 0.0001
        eventlet.sleep(sleep_for)
    with app.app_context():
        app.logger.info(f"PID {os.getpid()}: Persistent game loop runner terminating.")

def start_game_loop_for_worker():
    global _game_loop_started_in_this_process
    gm = get_game_manager() # Initialize/get gm for this worker before spawning
    with app.app_context():
        pid = os.getpid()
        if not _game_loop_started_in_this_process:
            app.logger.info(f"PID {pid} Worker: Attempting to start game loop...")
            try:
                gm.game_loop_greenlet = eventlet.spawn(_persistent_game_loop_runner)
                _game_loop_started_in_this_process = True
                app.logger.info(f"PID {pid} Worker: Game loop greenlet successfully spawned.")
            except Exception as e:
                app.logger.critical(f"PID {pid} Worker: FAILED TO START GAME LOOP GREENLET: {e}", exc_info = True)
        else:
            app.logger.info(f"PID {pid} Worker: Game loop already marked as started.")

game_blueprint = Blueprint('game', __name__, template_folder = 'templates', static_folder = 'static', static_url_path = '/static/game')
@game_blueprint.route('/')
def index_route():
    return render_template('index.html')
app.register_blueprint(game_blueprint, url_prefix = GAME_PATH_PREFIX)
sio.init_app(app, path = f"{GAME_PATH_PREFIX}/socket.io")
@app.route('/')
def health_check_route():
    return "OK", 200

@sio.on('connect')
def handle_connect_event(auth=None):
    gm = get_game_manager()
    with app.app_context():
        player = gm.add_player(request.sid)
        app.logger.info(f"Connect: {player.name}({request.sid}). Players: {len(gm.players)}")
        cs = gm.get_or_create_scene(player.scene_x, player.scene_y)
        avtl = [{'x': t[0], 'y': t[1]} for t in player.visible_tiles_cache]
        initial_game_data = {
            'player_data': player.get_full_data(),
            'other_players_in_scene': gm.get_visible_players_for_observer(player),
            'visible_npcs': gm.get_visible_npcs_for_observer(player),
            'visible_trees': gm.get_visible_trees_for_observer(player),
            'visible_terrain': cs.get_terrain_for_payload(player.visible_tiles_cache),
            'all_visible_tiles': avtl,
            'grid_width': GRID_WIDTH,
            'grid_height': GRID_HEIGHT,
            'tick_rate': GAME_HEARTBEAT_RATE,
            'default_rain_intensity': DEFAULT_RAIN_INTENSITY,
            'tree_char': TREE_CHAR,
            'elf_char': ELF_CHAR
        }
        emit_ctx('initial_game_data',initial_game_data)
        emit_ctx('lore_message', {'messageKey': "LORE.WELCOME_INITIAL", 'type': 'welcome-message'}, room = request.sid)

@sio.on('disconnect')
def handle_disconnect_event(*args):
    gm = get_game_manager()
    with app.app_context():
        player_left=gm.remove_player(request.sid)
        if player_left:
            app.logger.info(f"Disconnect: {player_left.name}({request.sid}) state saved. Players: {len(gm.players)}")
        else:
            app.logger.info(f"Disconnect for SID {request.sid} (player not found/removed).")

@sio.on('queue_player_action')
def handle_queue_player_action(data):
    gm = get_game_manager()
    with app.app_context():
        player = gm.get_player(request.sid)
        if not player:
            app.logger.warning(f"Action from unknown SID: {request.sid}")
            emit_ctx('action_feedback', {'success': False, 'message': "Player not recognized."})
            return
        action_type = data.get('type')
        valid_actions = ['move', 'look', 'drink_potion', 'say', 'shout', 'build_wall', 'destroy_wall', 'chop_tree']
        if action_type not in valid_actions:
            app.logger.warning(f"Player {player.name} sent invalid action: {action_type}")
            emit_ctx('action_feedback', {'success': False, 'messageKey': 'ACTION_FAILED_UNKNOWN_COMMAND', 'placeholders': {'actionWord': action_type}})
            return
        gm.queued_actions[request.sid] = data
        emit_ctx('action_feedback', {'success': True, 'messageKey': 'ACTION_QUEUED'})

if __name__ == '__main__':
    app.logger.info(f"Starting Flask-SocketIO server for LOCAL DEVELOPMENT on PID {os.getpid()}...")
    start_game_loop_for_worker()
    sio.run(app, debug = True, host = '0.0.0.0', port = int(os.environ.get('PORT', 5000)), use_reloader = False)
else:
    app.logger.info(f"App module loaded by WSGI server (e.g., Gunicorn) in PID {os.getpid()}. Game loop to be started by post_fork.")
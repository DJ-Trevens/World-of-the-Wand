import eventlet
eventlet.monkey_patch() # Should be the very first non-import line

import os
import random
from flask import Flask, render_template, request, Blueprint
from flask_socketio import SocketIO, emit as emit_ctx
import time
import traceback

# --- App Setup & SocketIO ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev_security_key')
GAME_PATH_PREFIX = '/world-of-the-wand'
game_blueprint = Blueprint('game', __name__, template_folder='templates', static_folder='static', static_url_path='/static/game')
@game_blueprint.route('/')
def index_route(): return render_template('index.html')
app.register_blueprint(game_blueprint, url_prefix=GAME_PATH_PREFIX)
socketio = SocketIO(app, async_mode="eventlet", path=f"{GAME_PATH_PREFIX}/socket.io", logger=True, engineio_logger=True)
@app.route('/')
def health_check(): return "OK", 200

# --- Game Settings & State ---
GRID_WIDTH, GRID_HEIGHT, GAME_TICK_RATE, SHOUT_MANA_COST, MAX_VIEW_DISTANCE = 20, 15, 0.75, 5, 8
players, queued_actions, _game_loop_started_in_this_process = {}, {}, False

def get_player_name(sid): return f"Wizard-{sid[:4]}"

def is_visible_server(obs, target): # obs = observer, target = target player data
    if not obs or not target: return False
    if obs['scene_x'] != target['scene_x'] or obs['scene_y'] != target['scene_y']: return False
    return abs(obs['x'] - target['x']) <= MAX_VIEW_DISTANCE and abs(obs['y'] - target['y']) <= MAX_VIEW_DISTANCE

def game_loop():
    # THIS IS THE VERY FIRST LINE. If this doesn't print, eventlet isn't running this function.
    print(f"GAME_LOOP_FUNCTION_ENTERED: PID {os.getpid()}, Time: {time.time()}")
    my_pid = os.getpid() # Now define my_pid
    try:
        print(f">>>> [{my_pid}] GAME LOOP THREAD HAS SUCCESSFULLY STARTED AND IS RUNNING (Tick rate: {GAME_TICK_RATE}s) <<<<")
        loop_count = 0
        while True:
            loop_start_time = time.time()
            loop_count += 1
            if loop_count % 20 == 1: print(f"[{my_pid}] Loop {loop_count} ALIVE. Players: {len(players)}, Actions: {len(queued_actions)}")

            current_actions = dict(queued_actions)
            queued_actions.clear()

            for sid, action_data in current_actions.items():
                if sid not in players: continue
                player = players[sid]
                action_type = action_data.get('type')
                details = action_data.get('details', {})

                if action_type == 'move' or action_type == 'look':
                    dx, dy = details.get('dx', 0), details.get('dy', 0)
                    player['char'] = details.get('newChar', player['char'])
                    if action_type == 'move':
                        nx, ny = player['x'] + dx, player['y'] + dy
                        sc, tm = False, "" # scene_changed, transition_message
                        if nx < 0: player['scene_x'] -= 1; player['x'] = GRID_WIDTH - 1; sc = True; tm = f"West {player['scene_x']},{player['scene_y']}"
                        elif nx >= GRID_WIDTH: player['scene_x'] += 1; player['x'] = 0; sc = True; tm = f"East {player['scene_x']},{player['scene_y']}"
                        else: player['x'] = nx
                        if ny < 0: player['scene_y'] -= 1; player['y'] = GRID_HEIGHT - 1; sc = True
                            if not tm: tm = f"North {player['scene_x']},{player['scene_y']}"
                        elif ny >= GRID_HEIGHT: player['scene_y'] += 1; player['y'] = 0; sc = True
                            if not tm: tm = f"South {player['scene_x']},{player['scene_y']}"
                        else:
                            if not (nx < 0 or nx >= GRID_WIDTH): player['y'] = ny
                        if sc: socketio.emit('lore_message', {'message': tm, 'type': 'system'}, room=sid)
                
                elif action_type == 'drink_potion': # simplified for brevity
                    if player['potions'] > 0: player['potions'] -= 1; player['current_health'] = min(player['max_health'], player['current_health'] + 15); socketio.emit('lore_message', {'message': "Potion consumed!", 'type': 'event-good'}, room=sid)
                    else: socketio.emit('lore_message', {'message': "No potions!", 'type': 'event-bad'}, room=sid)
                # ... other actions like say, shout
            
            # Broadcast State
            current_players_snapshot = list(players.values()) # Use snapshot for consistent iteration
            if current_players_snapshot:
                for recip_sid, recip_data in list(players.items()): # Iterate copy in case of disconnects
                    if recip_sid not in players: continue # Check if still connected
                    visible_others = [p for p_id, p in players.items() if p_id != recip_sid and is_visible_server(recip_data, p)]
                    payload = {'self_player_data': recip_data, 'visible_other_players': visible_others}
                    socketio.emit('game_update', payload, room=recip_sid)
                if loop_count % 10 == 1: print(f"[{my_pid}] Tick {loop_count}: Sent 'game_update' to {len(players)} players.")

            elapsed = time.time() - loop_start_time
            sleep_for = GAME_TICK_RATE - elapsed
            if sleep_for > 0: socketio.sleep(sleep_for)
            elif sleep_for < -0.05: print(f"!!! [{my_pid}] LOOP OVERRUN: Tick {loop_count} took {elapsed:.4f}s.")
    except Exception as e_loop:
        print(f"!!!!!!!! [{my_pid}] FATAL ERROR IN GAME_LOOP (PID: {my_pid}): {e_loop} !!!!!!!!")
        traceback.print_exc()

# Socket.IO Handlers
@socketio.on('connect')
def handle_connect_event(auth=None):
    sid, pid = request.sid, os.getpid()
    name = get_player_name(sid)
    players[sid] = {'id': sid, 'name': name, 'scene_x': 0, 'scene_y': 0, 'x': GRID_WIDTH // 2, 'y': GRID_HEIGHT // 2, 'char': random.choice(['^', 'v', '<', '>']), 'max_health': 100, 'current_health': 100, 'max_mana': 175, 'current_mana': 175, 'potions': 7, 'gold': 0}
    queued_actions[sid] = None
    print(f"[{pid}] Connect: {name} ({sid}). Players: {len(players)}")
    others_in_scene = [p for p_id, p in players.items() if p_id != sid and p['scene_x'] == players[sid]['scene_x'] and p['scene_y'] == players[sid]['scene_y']]
    emit_ctx('initial_game_data', {'player_data': players[sid], 'other_players_in_scene': others_in_scene, 'grid_width': GRID_WIDTH, 'grid_height': GRID_HEIGHT, 'tick_rate': GAME_TICK_RATE})
    # Notify others (simplified)
    for p_id_target, p_data_target in players.items():
        if p_id_target != sid and p_data_target['scene_x'] == players[sid]['scene_x'] and p_data_target['scene_y'] == players[sid]['scene_y']:
             socketio.emit('player_entered_your_scene', players[sid], room=p_id_target)


@socketio.on('disconnect')
def handle_disconnect_event():
    sid, pid = request.sid, os.getpid()
    player_left = players.pop(sid, None)
    if sid in queued_actions: del queued_actions[sid]
    if player_left: print(f"[{pid}] Disconnect: {player_left['name']} ({sid}). Players: {len(players)}")
    # Notify others (simplified)
    if player_left:
        for p_id_target, p_data_target in players.items():
             if p_data_target['scene_x'] == player_left['scene_x'] and p_data_target['scene_y'] == player_left['scene_y']:
                socketio.emit('player_exited_your_scene', {'id': sid, 'name': player_left['name']}, room=p_id_target)

@socketio.on('queue_player_action')
def handle_queue_player_action(data):
    sid, pid = request.sid, os.getpid()
    if sid not in players: emit_ctx('action_feedback', {'success': False, 'message': "Player not found."}); return
    queued_actions[sid] = data
    emit_ctx('action_feedback', {'success': True, 'message': "Action noted."})
    # print(f"[{pid}] Action queued for {players[sid]['name']}: {data}") # Can be noisy

# Gunicorn Hook Integration
def start_game_loop_for_worker():
    global _game_loop_started_in_this_process
    my_pid = os.getpid()
    if not _game_loop_started_in_this_process:
        print(f"[{my_pid}] Worker: Attempting to start game_loop task...")
        try:
            socketio.start_background_task(target=game_loop)
            print(f"[{my_pid}] Worker: call to socketio.start_background_task(target=game_loop) COMPLETED.")
            socketio.sleep(0) # ADDED: yield to eventlet hub
            _game_loop_started_in_this_process = True
            print(f"[{my_pid}] Worker: _game_loop_started_in_this_process set to True. Loop should be running.")
        except Exception as e:
            print(f"!!! [{my_pid}] Worker: FAILED TO START GAME LOOP: {e} !!!"); traceback.print_exc()
    else: print(f"[{my_pid}] Worker: Game loop already marked as started.")

if __name__ == '__main__':
    print(f"[{os.getpid()}] Starting Flask-SocketIO server for LOCAL DEVELOPMENT...")
    start_game_loop_for_worker() 
    socketio.run(app, debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), use_reloader=False)
else:
    print(f"[{os.getpid()}] App module loaded by Gunicorn. Game loop starts via post_fork hook.")
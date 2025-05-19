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

def is_visible_server(obs, target):
    if not obs or not target: return False
    if obs['scene_x'] != target['scene_x'] or obs['scene_y'] != target['scene_y']: return False
    return abs(obs['x'] - target['x']) <= MAX_VIEW_DISTANCE and abs(obs['y'] - target['y']) <= MAX_VIEW_DISTANCE

def game_loop():
    print(f">>>> [{os.getpid()}] game_loop FUNCTION ENTERED. Time: {time.time()} <<<<")
    my_pid = os.getpid()
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
                player_ref = players[sid]
                action_type = action_data.get('type')
                details = action_data.get('details', {})

                if action_type == 'move' or action_type == 'look':
                    dx, dy = details.get('dx', 0), details.get('dy', 0)
                    player_ref['char'] = details.get('newChar', player_ref['char'])
                    
                    if action_type == 'move':
                        nx, ny = player_ref['x'] + dx, player_ref['y'] + dy # Use nx, ny for new local coords
                        scene_changed, transition_message = False, ""

                        if nx < 0:
                            player_ref['scene_x'] -= 1
                            player_ref['x'] = GRID_WIDTH - 1
                            scene_changed = True
                            transition_message = f"Emerged west ({player_ref['scene_x']},{player_ref['scene_y']})."
                        elif nx >= GRID_WIDTH:
                            player_ref['scene_x'] += 1
                            player_ref['x'] = 0
                            scene_changed = True
                            transition_message = f"Emerged east ({player_ref['scene_x']},{player_ref['scene_y']})."
                        else:
                            player_ref['x'] = nx # Apply new x if not changing scenes horizontally

                        if ny < 0:
                            player_ref['scene_y'] -= 1
                            player_ref['y'] = GRID_HEIGHT - 1
                            scene_changed = True
                            if not transition_message: # Only set Y message if X didn't set one
                                transition_message = f"Emerged north ({player_ref['scene_x']},{player_ref['scene_y']})."
                        elif ny >= GRID_HEIGHT:
                            player_ref['scene_y'] += 1
                            player_ref['y'] = 0
                            scene_changed = True
                            if not transition_message: # Only set Y message if X didn't set one
                                transition_message = f"Emerged south ({player_ref['scene_x']},{player_ref['scene_y']})."
                        else:
                            # Only apply new y if not changing scenes horizontally (already handled x)
                            # AND not changing scenes vertically (already handled y)
                            if not (nx < 0 or nx >= GRID_WIDTH): # Check original nx for horizontal transition
                                player_ref['y'] = ny
                        
                        if scene_changed:
                            socketio.emit('lore_message', {'message': transition_message, 'type': 'system'}, room=sid)
                
                elif action_type == 'drink_potion':
                    if player_ref['potions'] > 0: 
                        player_ref['potions'] -= 1
                        player_ref['current_health'] = min(player_ref['max_health'], player_ref['current_health'] + 15)
                        socketio.emit('lore_message', {'message': "Potion consumed!", 'type': 'event-good'}, room=sid)
                    else: 
                        socketio.emit('lore_message', {'message': "No potions!", 'type': 'event-bad'}, room=sid)
                
                elif action_type == 'say':
                    message_text = details.get('message', '')
                    if message_text:
                        chat_data = { 'sender_id': sid, 'sender_name': player_ref['name'], 'message': message_text, 'type': 'say', 
                                      'scene_coords': f"({player_ref['scene_x']},{player_ref['scene_y']})" }
                        for p_sid_target, p_data_target in list(players.items()):
                            if p_data_target['scene_x'] == player_ref['scene_x'] and p_data_target['scene_y'] == player_ref['scene_y']:
                                socketio.emit('chat_message', chat_data, room=p_sid_target)

                elif action_type == 'shout':
                    message_text = details.get('message', '')
                    if message_text:
                        if player_ref['current_mana'] >= SHOUT_MANA_COST:
                            player_ref['current_mana'] -= SHOUT_MANA_COST
                            chat_data = { 'sender_id': sid, 'sender_name': player_ref['name'], 'message': message_text, 'type': 'shout', 
                                          'scene_coords': f"({player_ref['scene_x']},{player_ref['scene_y']})" }
                            for p_sid_target, p_data_target in list(players.items()):
                                if abs(p_data_target['scene_x'] - player_ref['scene_x']) <= 1 and \
                                   abs(p_data_target['scene_y'] - player_ref['scene_y']) <= 1:
                                    socketio.emit('chat_message', chat_data, room=p_sid_target)
                            socketio.emit('lore_message', {'message': f"Tome notes: Your voice booms, costing {SHOUT_MANA_COST} mana!", 'type': 'system'}, room=sid)
                        else:
                            socketio.emit('lore_message', {'message': f"Tome warns: You lack the mana to project your voice so powerfully.", 'type': 'event-bad'}, room=sid)
            
            current_players_snapshot = list(players.values())
            if current_players_snapshot:
                for recip_sid, recip_data_loop_start in list(players.items()): 
                    if recip_sid not in players: continue

                    # Use the most current version of recipient_data for visibility checks and payload
                    current_recipient_data = players[recip_sid]
                    visible_others = []
                    for other_p_id, other_p_data in list(players.items()): # Iterate a copy for safety
                        if other_p_id == recip_sid: continue
                        if is_visible_server(current_recipient_data, other_p_data):
                            visible_others.append({'id': other_p_data['id'], 'name': other_p_data['name'], 'x': other_p_data['x'], 'y': other_p_data['y'], 'char': other_p_data['char'], 'scene_x': other_p_data['scene_x'], 'scene_y': other_p_data['scene_y']})
                    
                    payload = {'self_player_data': current_recipient_data, 'visible_other_players': visible_others}
                    socketio.emit('game_update', payload, room=recip_sid)
                
                if loop_count % 10 == 1 and len(players)>0: print(f"[{my_pid}] Tick {loop_count}: Sent 'game_update' to {len(players)} players.")

            elapsed = time.time() - loop_start_time
            sleep_for = GAME_TICK_RATE - elapsed
            if sleep_for > 0: socketio.sleep(sleep_for)
            elif sleep_for < -0.05: print(f"!!! [{my_pid}] LOOP OVERRUN: Tick {loop_count} took {elapsed:.4f}s.")
    except Exception as e_loop:
        print(f"!!!!!!!! [{my_pid}] FATAL ERROR IN GAME_LOOP (PID: {my_pid}): {e_loop} !!!!!!!!")
        traceback.print_exc()

@socketio.on('connect')
def handle_connect_event(auth=None):
    sid, pid = request.sid, os.getpid()
    name = get_player_name(sid)
    players[sid] = {'id': sid, 'name': name, 'scene_x': 0, 'scene_y': 0, 'x': GRID_WIDTH // 2, 'y': GRID_HEIGHT // 2, 
        'char': random.choice(['^', 'v', '<', '>']), 'max_health': 100, 'current_health': 100, 
        'max_mana': 175, 'current_mana': 175, 'potions': 7, 'gold': 0}
    queued_actions[sid] = None 
    print(f"[{pid}] Connect: {name} ({sid}). Players: {len(players)}")
    others_in_scene = []
    for p_sid_iter, p_data_iter in list(players.items()): # Iterate copy
        if p_sid_iter != sid and p_data_iter['scene_x'] == players[sid]['scene_x'] and p_data_iter['scene_y'] == players[sid]['scene_y']:
            others_in_scene.append({'id': p_data_iter['id'], 'name': p_data_iter['name'], 'x': p_data_iter['x'], 'y': p_data_iter['y'], 'char': p_data_iter['char'], 'scene_x': p_data_iter['scene_x'], 'scene_y': p_data_iter['scene_y']})
    emit_ctx('initial_game_data', {'player_data': players[sid], 'other_players_in_scene': others_in_scene, 'grid_width': GRID_WIDTH, 'grid_height': GRID_HEIGHT, 'tick_rate': GAME_TICK_RATE})
    
    new_player_data_for_broadcast = {k: players[sid][k] for k in ['id', 'name', 'x', 'y', 'char', 'scene_x', 'scene_y']}
    for p_id_target, p_data_target in list(players.items()):
        if p_id_target != sid and p_data_target['scene_x'] == players[sid]['scene_x'] and p_data_target['scene_y'] == players[sid]['scene_y']:
             socketio.emit('player_entered_your_scene', new_player_data_for_broadcast, room=p_id_target)
    print(f"[{pid}] Sent initial_game_data to {name} and notified scene members.")


@socketio.on('disconnect')
def handle_disconnect_event():
    sid, pid = request.sid, os.getpid()
    player_left = players.pop(sid, None)
    if sid in queued_actions: del queued_actions[sid]
    if player_left: 
        print(f"[{pid}] Disconnect: {player_left['name']} ({sid}). Players: {len(players)}")
        for p_id_target, p_data_target in list(players.items()):
             if p_data_target['scene_x'] == player_left['scene_x'] and p_data_target['scene_y'] == player_left['scene_y']:
                socketio.emit('player_exited_your_scene', {'id': sid, 'name': player_left['name']}, room=p_id_target)
    else: print(f"[{pid}] Disconnect for SID {sid} but player not found.")

@socketio.on('queue_player_action')
def handle_queue_player_action(data):
    sid, pid = request.sid, os.getpid()
    if sid not in players: emit_ctx('action_feedback', {'success': False, 'message': "Player not found."}); return
    action_type = data.get('type')
    valid_actions = ['move', 'look', 'drink_potion', 'say', 'shout']
    if action_type not in valid_actions:
        emit_ctx('action_feedback', {'success': False, 'message': f"Unknown action: {action_type}."}); return
    queued_actions[sid] = data 
    emit_ctx('action_feedback', {'success': True, 'message': "Action noted."})
    # print(f"[{pid}] Action queued for {players[sid]['name']}: {data}")


def start_game_loop_for_worker():
    global _game_loop_started_in_this_process
    my_pid = os.getpid()
    if not _game_loop_started_in_this_process:
        print(f"[{my_pid}] Worker: Attempting to start game_loop task...")
        try:
            socketio.start_background_task(target=game_loop)
            print(f"[{my_pid}] Worker: call to socketio.start_background_task(target=game_loop) COMPLETED.")
            socketio.sleep(0) 
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
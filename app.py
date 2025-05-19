import eventlet
eventlet.monkey_patch()

import os
import random
from flask import Flask, render_template, request, Blueprint
from flask_socketio import SocketIO, emit as emit_ctx
import time
import traceback

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev_security_key')

GAME_PATH_PREFIX = '/world-of-the-wand'
game_blueprint = Blueprint('game', __name__, template_folder='templates', static_folder='static', static_url_path='/static/game')

@game_blueprint.route('/')
def index_route():
    return render_template('index.html')

app.register_blueprint(game_blueprint, url_prefix=GAME_PATH_PREFIX)
socketio = SocketIO(app, async_mode="eventlet", path=f"{GAME_PATH_PREFIX}/socket.io", logger=True, engineio_logger=True)

@app.route('/')
def health_check():
    return "OK", 200

# Game Settings
GRID_WIDTH = 20
GRID_HEIGHT = 15
GAME_TICK_RATE = 0.75 
SHOUT_MANA_COST = 5
MAX_VIEW_DISTANCE = 8

players = {} 
queued_actions = {} 
_game_loop_started_in_this_process = False


def get_player_name(sid):
    return f"Wizard-{sid[:4]}"

def is_visible_server(observer_player_data, target_player_data):
    if not observer_player_data or not target_player_data: return False
    if observer_player_data['scene_x'] != target_player_data['scene_x'] or \
       observer_player_data['scene_y'] != target_player_data['scene_y']: return False
    dist_x = abs(observer_player_data['x'] - target_player_data['x'])
    dist_y = abs(observer_player_data['y'] - target_player_data['y'])
    return dist_x <= MAX_VIEW_DISTANCE and dist_y <= MAX_VIEW_DISTANCE

def game_loop():
    # ----> IMMEDIATE PRINT ON FUNCTION ENTRY <----
    print(f">>>> [{os.getpid()}] game_loop FUNCTION ENTERED. Time: {time.time()} <<<<")
    my_pid = os.getpid() # Define my_pid after the first print
    try:
        print(f">>>> [{my_pid}] GAME LOOP THREAD HAS SUCCESSFULLY STARTED AND IS RUNNING (Tick rate: {GAME_TICK_RATE}s) <<<<")
        loop_count = 0
        # ... (rest of game_loop as in previous fully working version) ...
        while True:
            loop_start_time = time.time()
            loop_count += 1
            
            if loop_count % 20 == 0 : 
                 print(f"[{my_pid}] Game Loop ALIVE - Tick {loop_count}. Players: {len(players)}. Actions: {len(queued_actions)}")

            current_process_players_snapshot = dict(players) 
            current_process_actions = dict(queued_actions)
            queued_actions.clear()

            for sid, action_data in current_process_actions.items():
                if sid not in players: 
                    continue
                
                player_ref = players[sid] 
                action_type = action_data.get('type')
                details = action_data.get('details', {})

                if action_type == 'move' or action_type == 'look':
                    dx = details.get('dx', 0)
                    dy = details.get('dy', 0)
                    player_ref['char'] = details.get('newChar', player_ref['char'])
                    
                    if action_type == 'move':
                        new_x_local = player_ref['x'] + dx
                        new_y_local = player_ref['y'] + dy
                        scene_changed = False
                        transition_message = ""
                        if new_x_local < 0:
                            player_ref['scene_x'] -= 1
                            player_ref['x'] = GRID_WIDTH - 1
                            scene_changed = True
                            transition_message = f"Emerged west ({player_ref['scene_x']},{player_ref['scene_y']})."
                        elif new_x_local >= GRID_WIDTH:
                            player_ref['scene_x'] += 1
                            player_ref['x'] = 0
                            scene_changed = True
                            transition_message = f"Emerged east ({player_ref['scene_x']},{player_ref['scene_y']})."
                        else:
                            player_ref['x'] = new_x_local
                        if new_y_local < 0:
                            player_ref['scene_y'] -= 1
                            player_ref['y'] = GRID_HEIGHT - 1
                            scene_changed = True 
                            if not transition_message: 
                                transition_message = f"Emerged north ({player_ref['scene_x']},{player_ref['scene_y']})."
                        elif new_y_local >= GRID_HEIGHT:
                            player_ref['scene_y'] += 1
                            player_ref['y'] = 0
                            scene_changed = True 
                            if not transition_message: 
                                transition_message = f"Emerged south ({player_ref['scene_x']},{player_ref['scene_y']})."
                        else:
                            if not (new_x_local < 0 or new_x_local >= GRID_WIDTH): 
                                player_ref['y'] = new_y_local
                        if scene_changed:
                            socketio.emit('lore_message', {'message': transition_message, 'type': 'system'}, room=sid)

                elif action_type == 'drink_potion':
                    if player_ref['potions'] > 0:
                        player_ref['potions'] -= 1
                        player_ref['current_health'] = min(player_ref['max_health'], player_ref['current_health'] + 15)
                        socketio.emit('lore_message', {'message': "Tome notes: You drink a potion, feeling invigorated!", 'type': 'event-good'}, room=sid)
                    else:
                        socketio.emit('lore_message', {'message': "Tome sighs: Your satchel is empty of potions.", 'type': 'event-bad'}, room=sid)
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

            if current_process_players_snapshot:
                all_players_snapshot_after_actions = list(players.values()) 
                num_updates_sent = 0
                for recipient_sid in list(current_process_players_snapshot.keys()): 
                    if recipient_sid not in players: continue
                    recipient_player_data_for_visibility = players[recipient_sid]
                    visible_other_players_list = []
                    for other_p_data in all_players_snapshot_after_actions:
                        if other_p_data['id'] == recipient_sid: continue
                        if is_visible_server(recipient_player_data_for_visibility, other_p_data):
                            visible_other_players_list.append({'id': other_p_data['id'], 'name': other_p_data['name'], 'x': other_p_data['x'], 'y': other_p_data['y'], 'char': other_p_data['char'], 'scene_x': other_p_data['scene_x'], 'scene_y': other_p_data['scene_y']})
                    payload_for_client = {
                        'self_player_data': players[recipient_sid], 
                        'visible_other_players': visible_other_players_list,
                    }
                    socketio.emit('game_update', payload_for_client, room=recipient_sid)
                    num_updates_sent +=1
                if num_updates_sent > 0 and loop_count % 5 == 0 : 
                     print(f"[{my_pid}] Tick {loop_count}: Sent 'game_update' to {num_updates_sent} players.")
            
            elapsed_time = time.time() - loop_start_time
            sleep_duration = GAME_TICK_RATE - elapsed_time
            if sleep_duration > 0:
                socketio.sleep(sleep_duration)
            elif sleep_duration < -0.05: 
                print(f"!!! [{my_pid}] GAME LOOP OVERRUN: Tick {loop_count} took {elapsed_time:.4f}s.")
    except Exception as e_loop: 
        print(f"!!!!!!!! [{my_pid}] FATAL ERROR IN GAME_LOOP ITSELF (pid: {my_pid}): {e_loop} !!!!!!!!")
        traceback.print_exc()

# Socket.IO handlers
@socketio.on('connect')
def handle_connect_event(auth=None):
    # ... (implementation as before, no changes needed here for this debug step) ...
    sid = request.sid; my_pid = os.getpid()
    print(f"[{my_pid}] Connect event for SID {sid}.")
    player_name = get_player_name(sid)
    new_player_data = {
        'id': sid, 'name': player_name, 'scene_x': 0, 'scene_y': 0, 'x': GRID_WIDTH // 2, 'y': GRID_HEIGHT // 2, 
        'char': random.choice(['^', 'v', '<', '>']), 'max_health': 100, 'current_health': 100, 
        'max_mana': 175, 'current_mana': 175, 'potions': 7, 'gold': 0
    }
    players[sid] = new_player_data
    queued_actions[sid] = None 
    print(f"[{my_pid}] Player {player_name} ({sid}) added. Total players: {len(players)}")
    other_players_in_start_scene = []
    for p_sid_iter, p_data_iter in list(players.items()):
        if p_sid_iter != sid and p_data_iter['scene_x'] == new_player_data['scene_x'] and p_data_iter['scene_y'] == new_player_data['scene_y']:
            other_players_in_start_scene.append({'id': p_data_iter['id'], 'name': p_data_iter['name'], 'x': p_data_iter['x'], 'y': p_data_iter['y'], 'char': p_data_iter['char'], 'scene_x': p_data_iter['scene_x'], 'scene_y': p_data_iter['scene_y']})
    emit_ctx('initial_game_data', {'player_data': new_player_data, 'other_players_in_scene': other_players_in_start_scene, 'grid_width': GRID_WIDTH, 'grid_height': GRID_HEIGHT, 'tick_rate': GAME_TICK_RATE})
    new_player_broadcast_data = {'id': new_player_data['id'], 'name': new_player_data['name'], 'x': new_player_data['x'], 'y': new_player_data['y'], 'char': new_player_data['char'], 'scene_x': new_player_data['scene_x'], 'scene_y': new_player_data['scene_y']}
    for p_sid_iter, p_data_iter in list(players.items()):
        if p_sid_iter != sid and p_data_iter['scene_x'] == new_player_data['scene_x'] and p_data_iter['scene_y'] == new_player_data['scene_y']:
            socketio.emit('player_entered_your_scene', new_player_broadcast_data, room=p_sid_iter)
    print(f"[{my_pid}] Sent 'initial_game_data' to {player_name} and 'player_entered_your_scene' to relevant players.")


@socketio.on('disconnect')
def handle_disconnect_event():
    # ... (implementation as before) ...
    sid = request.sid; my_pid = os.getpid()
    player_left_data = players.pop(sid, None)
    if sid in queued_actions: del queued_actions[sid]
    if player_left_data:
        print(f"[{my_pid}] Player {player_left_data['name']} ({sid}) disconnected. Total players: {len(players)}")
        player_left_broadcast_data = {'id': sid, 'name': player_left_data['name']}
        for p_sid_iter, p_data_iter in list(players.items()):
            if p_data_iter['scene_x'] == player_left_data['scene_x'] and p_data_iter['scene_y'] == player_left_data['scene_y']:
                socketio.emit('player_exited_your_scene', player_left_broadcast_data, room=p_sid_iter)
    else: print(f"[{my_pid}] Disconnect for SID {sid} but player not in 'players' dict.")


@socketio.on('queue_player_action')
def handle_queue_player_action(data):
    # ... (implementation as before) ...
    sid = request.sid; my_pid = os.getpid()
    if sid not in players:
        print(f"[{my_pid}] Action from unknown SID {sid}: {data}"); emit_ctx('action_feedback', {'success': False, 'message': "Player not recognized."}); return
    player_name = players[sid]['name']; action_type = data.get('type')
    valid_actions = ['move', 'look', 'drink_potion', 'say', 'shout']
    if action_type not in valid_actions:
        emit_ctx('action_feedback', {'success': False, 'message': f"Unknown action: {action_type}."}); return
    queued_actions[sid] = data 
    emit_ctx('action_feedback', {'success': True, 'message': "Your will is noted..."})
    print(f"[{my_pid}] Action queued for {player_name} ({sid}): {data}")


def start_game_loop_for_worker():
    global _game_loop_started_in_this_process
    my_pid = os.getpid()
    if not _game_loop_started_in_this_process:
        print(f"[{my_pid}] Worker: Attempting to start game_loop background task via start_background_task...")
        try:
            socketio.start_background_task(target=game_loop)
            # ----> ADDED PRINT AFTER THE CALL <----
            print(f"[{my_pid}] Worker: call to socketio.start_background_task(target=game_loop) COMPLETED.")
            _game_loop_started_in_this_process = True
        except Exception as e:
            print(f"!!! [{my_pid}] Worker: FAILED TO START GAME LOOP (exception during start_background_task): {e} !!!")
            traceback.print_exc()
    else: print(f"[{my_pid}] Worker: Game loop already marked as started in this process.")

if __name__ == '__main__':
    my_pid = os.getpid()
    print(f"[{my_pid}] Starting Flask-SocketIO server for LOCAL DEVELOPMENT...")
    start_game_loop_for_worker() 
    socketio.run(app, debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), use_reloader=False)
else:
    my_pid = os.getpid()
    print(f"[{my_pid}] App module loaded by Gunicorn (PID: {my_pid}). Game loop for worker will be started by post_fork hook.")
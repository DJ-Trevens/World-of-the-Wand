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

# Game State
players = {}
queuedActions = {}
_game_loop_started_in_this_process = False # Flag per process

def get_player_name(sid):
    return f"Wizard-{sid[:4]}"

def game_loop():
    my_pid = os.getpid()
    print(f">>>> [{my_pid}] GAME LOOP THREAD HAS STARTED AND IS RUNNING <<<<")
    loop_count = 0
    while True:
        try:
            loop_count += 1
            current_actions_to_process = dict(queuedActions)

            # Optional: Reduce noise if loop is very idle
            if loop_count % 20 == 0 or current_actions_to_process or players:
                print(f"[{my_pid}] Game Loop Iteration: {loop_count}. Players: {len(players)}, Actions Queued: {len(current_actions_to_process)}")

            for sid, actionData in current_actions_to_process.items():
                if actionData and sid in players:
                    player = players[sid]
                    actionType = actionData.get('type')
                    details = actionData.get('details', {})
                    print(f"[{my_pid}] Game Loop: Processing action '{actionType}' for player {player.get('name', sid)} ({sid})")

                    if actionType == 'move' or actionType == 'look':
                        dx = details.get('dx', 0)
                        dy = details.get('dy', 0)
                        newChar = details.get('newChar', player['char'])
                        new_x_local = player['x'] + dx
                        new_y_local = player['y'] + dy
                        scene_changed = False
                        transition_message = ""
                        if new_x_local < 0:
                            player['scene_x'] -= 1
                            player['x'] = GRID_WIDTH - 1
                            scene_changed = True
                            transition_message = f"Tome scribbles: You emerge on the western edge of a new area ({player['scene_x']},{player['scene_y']})."
                        elif new_x_local >= GRID_WIDTH:
                            player['scene_x'] += 1
                            player['x'] = 0
                            scene_changed = True
                            transition_message = f"Tome scribbles: You emerge on the eastern edge of a new area ({player['scene_x']},{player['scene_y']})."
                        else:
                            player['x'] = new_x_local
                        if new_y_local < 0:
                            player['scene_y'] -= 1
                            player['y'] = GRID_HEIGHT - 1
                            scene_changed = True
                            if not transition_message:
                                 transition_message = f"Tome scribbles: You emerge on the northern edge of a new area ({player['scene_x']},{player['scene_y']})."
                        elif new_y_local >= GRID_HEIGHT:
                            player['scene_y'] += 1
                            player['y'] = 0
                            scene_changed = True
                            if not transition_message:
                                transition_message = f"Tome scribbles: You emerge on the southern edge of a new area ({player['scene_x']},{player['scene_y']})."
                        else:
                            if not (new_x_local < 0 or new_x_local >= GRID_WIDTH) :
                                player['y'] = new_y_local
                        player['char'] = newChar
                        if scene_changed:
                            socketio.emit('lore_message', {'message': transition_message, 'type': 'system'}, room=sid)
                        print(f"[{my_pid}] Game Loop: Player {player.get('name', sid)} new state after move/look: {player}")

                    elif actionType == 'drink_potion':
                        if player['potions'] > 0:
                            player['potions'] -= 1
                            player['current_health'] = min(player['max_health'], player['current_health'] + 15)
                            potion_effect_message = "You drink a potion. You feel a warmth spread through you, slightly invigorating!"
                            socketio.emit('lore_message', {'message': f"Tome notes: {potion_effect_message}", 'type': 'event-good'}, room=sid)
                        else:
                            socketio.emit('lore_message', {'message': "Tome sighs: You reach for a potion, but your satchel is empty.", 'type': 'event-bad'}, room=sid)
                    elif actionType == 'say':
                        message_text = details.get('message', '')
                        if message_text:
                            chat_data = { 'sender_name': get_player_name(sid), 'message': message_text, 'type': 'say', 'scene_coords': f"({player['scene_x']},{player['scene_y']})" }
                            for p_sid_target, p_data_target in list(players.items()):
                                if p_data_target['scene_x'] == player['scene_x'] and p_data_target['scene_y'] == player['scene_y']:
                                    socketio.emit('chat_message', chat_data, room=p_sid_target)
                    elif actionType == 'shout':
                        message_text = details.get('message', '')
                        if message_text:
                            if player['current_mana'] >= SHOUT_MANA_COST:
                                player['current_mana'] -= SHOUT_MANA_COST
                                chat_data = { 'sender_name': get_player_name(sid), 'message': message_text, 'type': 'shout', 'scene_coords': f"({player['scene_x']},{player['scene_y']})" }
                                current_scene_x, current_scene_y = player['scene_x'], player['scene_y']
                                adjacent_scenes = [(current_scene_x, current_scene_y), (current_scene_x + 1, current_scene_y), (current_scene_x - 1, current_scene_y), (current_scene_x, current_scene_y + 1), (current_scene_x, current_scene_y - 1)]
                                targeted_sids = set()
                                for p_sid_target, p_data_target in list(players.items()):
                                    if (p_data_target['scene_x'], p_data_target['scene_y']) in adjacent_scenes:
                                        targeted_sids.add(p_sid_target)
                                for target_sid_emit in targeted_sids:
                                    socketio.emit('chat_message', chat_data, room=target_sid_emit)
                                socketio.emit('lore_message', {'message': f"Tome notes: Your voice booms, costing {SHOUT_MANA_COST} mana!", 'type': 'system'}, room=sid)
                            else:
                                socketio.emit('lore_message', {'message': f"Tome warns: You lack the {SHOUT_MANA_COST} mana to project your voice so powerfully.", 'type': 'event-bad'}, room=sid)
                    
                    if sid in queuedActions and queuedActions[sid] == actionData:
                        queuedActions[sid] = None

            current_player_states = list(players.values())
            if current_player_states:
                 if loop_count % 5 == 0 or current_actions_to_process :
                    print(f"[{my_pid}] Game Loop Tick {loop_count}: Emitting game_state_update for {len(current_player_states)} player(s). Data: {current_player_states}")
                 socketio.emit('game_state_update', current_player_states)
            elif loop_count % 60 == 0: # Log less often if no players
                 print(f"[{my_pid}] Game Loop Tick {loop_count}: No players to update.")
            
            socketio.sleep(GAME_TICK_RATE)

        except Exception as e:
            print(f"!!! [{my_pid}] ERROR IN GAME LOOP (Iteration {loop_count}): {e} !!!")
            traceback.print_exc()
            socketio.sleep(1)

# SocketIO event handlers (no change needed in these based on current problem)
@socketio.on('connect')
def handle_connect(auth=None):
    sid = request.sid
    my_pid = os.getpid()
    print(f"[{my_pid}] Connect event for SID {sid}.")

    if sid in players:
        print(f"[{my_pid}] Player {get_player_name(sid)} ({sid}) already in players dict. Re-sending initial_state.")
        # This might be problematic if other_players isn't up-to-date for the *current* state of this player
        otherPlayersInScene = {
            playerID: playerData for playerID, playerData in players.items()
            if playerID != sid and playerData['scene_x'] == players[sid]['scene_x'] and playerData['scene_y'] == players[sid]['scene_y']
        }
        emit_ctx('initial_state', {
            'player': players[sid],
            'grid_width': GRID_WIDTH,
            'grid_height': GRID_HEIGHT,
            'other_players': otherPlayersInScene,
            'tick_rate': GAME_TICK_RATE
        })
        return

    print(f"[{my_pid}] New client connecting: SID {sid}")
    newPlayer = {
        'id': sid, 'name': get_player_name(sid), 'scene_x': 0, 'scene_y': 0,
        'x': GRID_WIDTH // 2, 'y': GRID_HEIGHT // 2, 'char': random.choice(['^', 'v', '<', '>']),
        'max_health': 100, 'current_health': 100, 'max_mana': 175, 'current_mana': 175,
        'potions': 7, 'gold': 0
    }
    players[sid] = newPlayer
    queuedActions[sid] = None
    print(f"[{my_pid}] Player {newPlayer['name']} ({sid}) added to players dict. Active players: {list(players.keys())}")

    otherPlayersInScene = {
        playerID: playerData for playerID, playerData in list(players.items()) # Iterate copy
        if playerID != sid and playerData['scene_x'] == newPlayer['scene_x'] and playerData['scene_y'] == newPlayer['scene_y']
    }

    emit_ctx('initial_state', {
        'player': newPlayer,
        'grid_width': GRID_WIDTH,
        'grid_height': GRID_HEIGHT,
        'other_players': otherPlayersInScene,
        'tick_rate': GAME_TICK_RATE
    })
    print(f"[{my_pid}] Sent initial_state to {newPlayer['name']} ({sid}).")

    player_data_for_others = {
        'id': newPlayer['id'], 'name': newPlayer['name'], 'char': newPlayer['char'],
        'x': newPlayer['x'], 'y': newPlayer['y'],
        'scene_x': newPlayer['scene_x'], 'scene_y': newPlayer['scene_y']
    }
    socketio.emit('player_joined', player_data_for_others, room='/', skip_sid=sid)
    print(f"[{my_pid}] Broadcast player_joined for {newPlayer['name']} ({sid}).")


@socketio.on('disconnect')
def handle_disconnect(reason=None):
    sid = request.sid
    my_pid = os.getpid()
    print(f"[{my_pid}] Disconnect event for SID {sid} (Reason: {reason if reason else 'N/A'}).")
    if sid in players:
        player_data_left = players.pop(sid, None)
        if player_data_left:
            player_id_left = player_data_left['id']
            player_name_left = player_data_left.get('name', 'A wizard')
            
            if sid in queuedActions:
                del queuedActions[sid]
            
            print(f"[{my_pid}] Player {player_name_left} ({player_id_left}) removed. Active players: {list(players.keys())}")
            socketio.emit('player_left', {'id': player_id_left, 'name': player_name_left}, room='/', skip_sid=sid)
            print(f"[{my_pid}] Broadcast player_left for {player_name_left} ({player_id_left}).")
        else:
            print(f"[{my_pid}] Player {sid} was in players keys, but pop returned None.")
    else:
        print(f"[{my_pid}] Player with SID {sid} not found in players list upon disconnect.")


@socketio.on('queue_command')
def handle_queue_command(data):
    sid = request.sid
    my_pid = os.getpid()
    if sid in players:
        player_name = players[sid].get('name', sid)
        actionType = data.get('type')
        print(f"[{my_pid}] Command received from {player_name} ({sid}): {data}")
        if actionType in ['move', 'look', 'cast', 'drink_potion', 'say', 'shout']:
            queuedActions[sid] = data
            if actionType not in ['drink_potion', 'say', 'shout']:
                emit_ctx('action_queued', {'message': "Your will has been noted. Awaiting cosmic alignment..."})
            print(f"[{my_pid}] Command queued for {player_name}. Queued: {queuedActions[sid]}")
        else:
            emit_ctx('action_failed', {'message': "Your old brain is wrought with confusion. (Unknown command type)"})
            print(f"[{my_pid}] Unknown command type from {player_name}: {actionType}")
    else:
        emit_ctx('action_failed', {'message': "Lost soul whispers commands... (Player not found on server)"})
        print(f"[{my_pid}] Command from unknown SID {sid}: {data}")


def start_game_loop_if_not_running(): # Renamed for clarity
    global _game_loop_started_in_this_process
    my_pid = os.getpid()

    if not _game_loop_started_in_this_process:
        print(f"[{my_pid}] Attempting to start game loop background task from start_game_loop_if_not_running()...")
        try:
            # Ensure socketio instance is available. It should be global.
            socketio.start_background_task(target=game_loop)
            _game_loop_started_in_this_process = True
            print(f"[{my_pid}] Game loop background task initiated via start_game_loop_if_not_running(). Watch for 'GAME LOOP THREAD HAS STARTED' message from this PID.")
        except Exception as e:
            print(f"!!! [{my_pid}] FAILED TO START GAME LOOP (from start_game_loop_if_not_running): {e} !!!")
            traceback.print_exc()
    else:
        print(f"[{my_pid}] Game loop already marked as started in this process (PID: {my_pid}).")

# This block runs ONLY when you execute `python app.py` directly
if __name__ == '__main__':
    my_pid = os.getpid()
    print(f"[{my_pid}] Starting Flask-SocketIO server for LOCAL DEVELOPMENT...")
    start_game_loop_if_not_running() # Start the loop for local dev
    socketio.run(app, debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), use_reloader=False)
else:
    # This block runs when Gunicorn imports the app.
    # We do NOT want to start the loop here if Gunicorn is managing it.
    # The post_fork hook in gunicorn_config.py will call start_game_loop_if_not_running().
    my_pid = os.getpid()
    print(f"[{my_pid}] App module loaded by Gunicorn (or other WSGI server). Game loop will be started by post_fork hook if applicable.")
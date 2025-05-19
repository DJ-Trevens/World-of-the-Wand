import eventlet
eventlet.monkey_patch()

import os
import random
from flask import Flask, render_template, request, Blueprint
from flask_socketio import SocketIO, emit
import time

app = Flask(__name__)
# Changed 'SECURITY_KEY' to the standard 'SECRET_KEY'
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev_security_key')

GAME_PATH_PREFIX = '/world-of-the-wand'
game_blueprint = Blueprint('game', __name__, template_folder='templates', static_folder='static', static_url_path='/static/game')

@game_blueprint.route('/')
def index_route():
    return render_template('index.html')

app.register_blueprint(game_blueprint, url_prefix=GAME_PATH_PREFIX)
socketio = SocketIO(app, async_mode="eventlet", path=f"{GAME_PATH_PREFIX}/socket.io", logger=True, engineio_logger=True) # Added logger for more debug

@app.route('/')
def health_check():
    return "OK", 200

# Game Settings
GRID_WIDTH = 20
GRID_HEIGHT = 15
GAME_TICK_RATE = 0.75 # Target, actual might be slightly different due to processing
SHOUT_MANA_COST = 5

# Game State
players = {}
queuedActions = {}
_game_loop_started = False

def get_player_name(sid):
    return f"Wizard-{sid[:4]}"

def game_loop():
    print("GAME LOOP THREAD STARTED") # Confirmation that the loop itself has started
    while True:
        try:
            socketio.sleep(GAME_TICK_RATE)
            # Process queued actions
            for sid, actionData in list(queuedActions.items()): # Use list() for safe iteration if modifying dict
                if actionData and sid in players: # Ensure player still exists
                    player = players[sid]
                    actionType = actionData.get('type')
                    details = actionData.get('details', {})

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
                            if not transition_message: # Avoid overwriting EW message
                                 transition_message = f"Tome scribbles: You emerge on the northern edge of a new area ({player['scene_x']},{player['scene_y']})."
                        elif new_y_local >= GRID_HEIGHT:
                            player['scene_y'] += 1
                            player['y'] = 0
                            scene_changed = True
                            if not transition_message: # Avoid overwriting EW message
                                transition_message = f"Tome scribbles: You emerge on the southern edge of a new area ({player['scene_x']},{player['scene_y']})."
                        else:
                            # Only update Y if not transitioning horizontally (which already sets X)
                            if not (new_x_local < 0 or new_x_local >= GRID_WIDTH) :
                                player['y'] = new_y_local

                        player['char'] = newChar
                        if scene_changed:
                            socketio.emit('lore_message', {'message': transition_message, 'type': 'system'}, room=sid)

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
                            for p_sid, p_data in players.items():
                                if p_data['scene_x'] == player['scene_x'] and p_data['scene_y'] == player['scene_y']:
                                    socketio.emit('chat_message', chat_data, room=p_sid)

                    elif actionType == 'shout':
                        message_text = details.get('message', '')
                        if message_text:
                            if player['current_mana'] >= SHOUT_MANA_COST:
                                player['current_mana'] -= SHOUT_MANA_COST
                                chat_data = { 'sender_name': get_player_name(sid), 'message': message_text, 'type': 'shout', 'scene_coords': f"({player['scene_x']},{player['scene_y']})" }
                                current_scene_x, current_scene_y = player['scene_x'], player['scene_y']
                                adjacent_scenes = [(current_scene_x, current_scene_y), (current_scene_x + 1, current_scene_y), (current_scene_x - 1, current_scene_y), (current_scene_x, current_scene_y + 1), (current_scene_x, current_scene_y - 1)]
                                targeted_sids = set()
                                for p_sid, p_data in players.items():
                                    if (p_data['scene_x'], p_data['scene_y']) in adjacent_scenes:
                                        targeted_sids.add(p_sid)
                                for target_sid in targeted_sids:
                                    socketio.emit('chat_message', chat_data, room=target_sid)
                                socketio.emit('lore_message', {'message': f"Tome notes: Your voice booms, costing {SHOUT_MANA_COST} mana!", 'type': 'system'}, room=sid)
                            else:
                                socketio.emit('lore_message', {'message': f"Tome warns: You lack the {SHOUT_MANA_COST} mana to project your voice so powerfully.", 'type': 'event-bad'}, room=sid)

                    queuedActions[sid] = None # Clear the action after processing

            # Broadcast game state
            current_player_states = list(players.values())
            if current_player_states: # Only emit if there are players
                 print(f"Game Loop Tick: Emitting game_state_update for {len(current_player_states)} player(s).")
                 socketio.emit('game_state_update', current_player_states)
            else:
                 print("Game Loop Tick: No players to update.")

        except Exception as e:
            print(f"!!! ERROR IN GAME LOOP: {e} !!!")
            import traceback
            traceback.print_exc()

@socketio.on('connect')
def handle_connect(auth=None): # auth parameter is for Socket.IO v3+ auth
    sid = request.sid
    print(f"Client connected: SID {sid}")
    newPlayer = {
        'id': sid, 'name': get_player_name(sid), 'scene_x': 0, 'scene_y': 0,
        'x': GRID_WIDTH // 2, 'y': GRID_HEIGHT // 2, 'char': random.choice(['^', 'v', '<', '>']),
        'max_health': 100, 'current_health': 100, 'max_mana': 175, 'current_mana': 175,
        'potions': 7, 'gold': 0
    }
    players[sid] = newPlayer
    queuedActions[sid] = None # Initialize queued action for new player

    # Prepare data about other players already in the same scene for the new player
    otherPlayersInScene = {
        playerID: playerData for playerID, playerData in players.items()
        if playerID != sid and playerData['scene_x'] == newPlayer['scene_x'] and playerData['scene_y'] == newPlayer['scene_y']
    }

    emit('initial_state', {
        'player': newPlayer,
        'grid_width': GRID_WIDTH,
        'grid_height': GRID_HEIGHT,
        'other_players': otherPlayersInScene, # Send only relevant other players
        'tick_rate': GAME_TICK_RATE
    })
    print(f"Sent initial_state to {sid}. Player data: {newPlayer}")

    # Notify other players about the new player
    # Use socketio.emit for broadcasting outside of a specific client's direct emit response context
    # or when needing to skip the current SID more explicitly in a broadcast.
    player_data_for_others = {
        'id': newPlayer['id'], 'name': newPlayer['name'], 'char': newPlayer['char'],
        'x': newPlayer['x'], 'y': newPlayer['y'],
        'scene_x': newPlayer['scene_x'], 'scene_y': newPlayer['scene_y']
    }
    socketio.emit('player_joined', player_data_for_others, skip_sid=sid, broadcast=True)
    print(f"Broadcast player_joined event for {newPlayer['name']} ({sid}) to other clients.")


@socketio.on('disconnect')
def handle_disconnect(reason=None): # reason param added for context
    sid = request.sid
    print(f"Client disconnected: SID {sid} (Reason: {reason if reason else 'N/A'})")
    if sid in players:
        player_id_left = players[sid]['id'] # Get ID before deleting
        del players[sid]
        if sid in queuedActions:
            del queuedActions[sid]
        # Notify other players
        socketio.emit('player_left', {'id': player_id_left}, broadcast=True, skip_sid=sid) # Send dict with id
        print(f"Broadcast player_left event for ID {player_id_left}.")
    else:
        print(f"Player with SID {sid} not found in players list upon disconnect.")


@socketio.on('queue_command')
def handle_queue_command(data):
    sid = request.sid
    if sid in players:
        actionType = data.get('type')
        # Validate actionType to prevent arbitrary data in queuedActions
        if actionType in ['move', 'look', 'cast', 'drink_potion', 'say', 'shout']:
            queuedActions[sid] = data
            # Provide immediate feedback for non-instant actions
            if actionType not in ['drink_potion', 'say', 'shout']: # These give feedback through game events
                emit('action_queued', {'message': "Your will has been noted. Awaiting cosmic alignment..."})
            print(f"Command queued for {sid}: {data}")
        else:
            emit('action_failed', {'message': "Your old brain is wrought with confusion. (Unknown command type received by server)"})
            print(f"Unknown command type from {sid}: {actionType}")
    else:
        # This case should ideally not happen if client only sends commands after connection
        emit('action_failed', {'message': "A lost soul whispers commands, but your connection to it was too weak... (Player not found on server)"})
        print(f"Command received from unknown SID {sid}: {data}")


def start_game_loop():
    global _game_loop_started
    if not _game_loop_started:
        print("Attempting to start game loop background task...")
        socketio.start_background_task(target=game_loop)
        _game_loop_started = True
        print("Game loop background task should be started.")
    else:
        print("Game loop already started.")

# Ensure game loop is started after app and socketio are initialized
# This will run when the script is executed (or module imported by WSGI server)
start_game_loop()

if __name__ == '__main__':
    print("Starting Flask-SocketIO server for development...")
    # The host '0.0.0.0' makes the server accessible externally, port from ENV or 5000
    socketio.run(app, debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
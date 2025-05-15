import eventlet
eventlet.monkey_patch()

import os
import random
from flask import Flask, render_template, request, Blueprint
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECURITY_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev_security_key') #change later!

# Blueprint & Path Config #
GAME_PATH_PREFIX = '/world-of-the-wand'

game_blueprint = Blueprint('game', __name__, template_folder = 'templates', static_folder = 'static', static_url_path = '/static/game')

@game_blueprint.route('/')
def index_route():
    return render_template('index.html')

app.register_blueprint(game_blueprint, url_prefix = GAME_PATH_PREFIX)

socketio = SocketIO(app, async_mode = "eventlet", path = f"{GAME_PATH_PREFIX}/socket.io")

@app.route('/')
def health_check():
    return "OK", 200

# Game #
GRID_WIDTH = 30
GRID_HEIGHT = 15
GAME_TICK_RATE = 2.0 # seconds

# Game State #
players = {}
queuedActions = {}

# Game Loop #
_game_loop_started = False

def game_loop():
    # Background tasks that processes game logic at fixed intervals.
    while True:
        socketio.sleep(GAME_TICK_RATE)
        for sid, actionData in list(queuedActions.items()):
            if actionData and sid in players:
                player = players[sid]
                actionType = actionData.get('type')
                details = actionData.get('details', {})

                if actionType == 'move' or actionType == 'look':
                    dx = details.get('dx', 0)
                    dy = details.get('dy', 0)
                    newChar = details.get('newChar', player['char'])

                    # Updates player position (w/ collision check)
                    newX = player['x'] + dx
                    newY = player['y'] + dy

                    if 0 <= newX < GRID_WIDTH:
                        player['x'] = newX
                    if 0 <= newY < GRID_HEIGHT:
                        player['y'] = newY
                    
                    player['char'] = newChar
                
                # TODO: Implement other action types like 'cast', 'help', etc.

                queuedActions[sid] = None # Clear the action for the player this tick
        # For optimization, later send only data relevant to each client's FOV/range
        current_player_states = list(players.values())
        socketio.emit('game_state_update', current_player_states) # Emits to all connected clients
        
# Event Handling #
@socketio.on('connect')
def handle_connect(auth=None):
    sid = request.sid 
    print(f"Client connected: {sid} (Auth: {auth})")

    newPlayer = {
        'id': sid,
        'x': GRID_WIDTH // 2,
        'y': GRID_HEIGHT // 2,
        'char': random.choice(['^', 'v', '<', '>'])
    }
    players[sid] = newPlayer
    queuedActions[sid] = None 

    otherPlayers = {playerID: playerData for playerID, playerData in players.items() if playerID != sid}
    
    emit('initial_state', {
        'player': newPlayer,
        'grid_width': GRID_WIDTH,
        'grid_height': GRID_HEIGHT,
        'other_players': otherPlayers,
        'tick_rate': GAME_TICK_RATE
    })
    print(f"Sent initial_state to {sid}")

    # Use the `skip_sid` parameter, which is directly supported by the underlying python-socketio server's emit.
    # Still calling it on the flask_socketio `socketio` instance, which should pass it through.
    # If `broadcast=True` is the problematic keyword, this might work around it.
    try:
        print(f"Attempting to emit player_joined for {newPlayer['id']}, skipping sid {sid}")
        socketio.server.emit('player_joined', newPlayer, skip_sid=sid, namespace='/') 
        print(f"Emitted player_joined via socketio.server.emit for {newPlayer['id']}")
    except Exception as e:
        print(f"ERROR emitting player_joined directly via socketio.server.emit: {e}")
        # Fallback: If the above fails, try the Flask-SocketIO instance again,
        try:
            print(f"Falling back to flask_socketio.emit with skip_sid for player_joined for {newPlayer['id']}")
            socketio.emit('player_joined', newPlayer, skip_sid=sid)
            print(f"Fallback flask_socketio.emit with skip_sid for player_joined for {newPlayer['id']} successful.")
        except Exception as e_fallback:
            print(f"ERROR with fallback flask_socketio.emit with skip_sid: {e_fallback}")


# In handle_disconnect:
@socketio.on('disconnect')
def handle_disconnect(reason=None):
    sid = request.sid 
    if sid in players:
        print(f"Client disconnected: {sid} (Reason: {reason})")
        player_data = players[sid]
        del players[sid]
        if sid in queuedActions: 
            del queuedActions[sid]
        
        # Notify all *remaining* clients
        # Try using skip_sid here as well if broadcast=True is consistently problematic
        try:
            print(f"Attempting to emit player_left for {sid}")
            socketio.server.emit('player_left', player_data['id'], skip_sid=sid, namespace='/') # Send player ID
            # Or to send the whole player object that left:
            # socketio.server.emit('player_left', player_data, skip_sid=sid, namespace='/')
            print(f"Emitted player_left via socketio.server.emit for {sid}")
        except Exception as e:
            print(f"ERROR emitting player_left directly via socketio.server.emit: {e}")
            try:
                print(f"Falling back to flask_socketio.emit for player_left for {sid}")
                socketio.emit('player_left', player_data['id'], broadcast=True) # broadcast=True should be fine for disconnect.
                print(f"Fallback flask_socketio.emit for player_left for {sid} successful.")
            except Exception as e_fallback:
                print(f"ERROR with fallback flask_socketio.emit for player_left: {e_fallback}")

@socketio.on('queue_command') # Client sends this event to queue an action
def handle_queue_command(data):
    sid = request.sid
    if sid in players:
        # basic validation of 'data' should be handled here (e.g. schema check)
        actionType = data.get('type')
        if actionType in ['move', 'look']: # TODOL Add other action types
            queuedActions[sid] = data # Store the action to be processed by game_loop()
            emit('action_queued', {'message': "Your will has been noted. Awaiting cosmic alignment..."})
        else:
            emit('action_failed', {'message': "Your old brain is wrought with confusion. (unknown command. Type '?' for help.)"})
    else:
        emit('action_failed', {'message': "A lost soul whispers commands, but your connection to it was too weak... (connection problem)"})

# Server Initialization #
def start_game_loop():
    # Ensures the game loop background task is started only once
    global _game_loop_started
    if not _game_loop_started:
        socketio.start_background_task(target = game_loop)
        _game_loop_started = True

#Start the loop! :)
start_game_loop()
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
    
    # This emit is for the connecting client only
    emit('initial_state', {
        'player': newPlayer,
        'grid_width': GRID_WIDTH,
        'grid_height': GRID_HEIGHT,
        'other_players': otherPlayers, # Ensure client expects this key
        'tick_rate': GAME_TICK_RATE
    })

    # This emit is for ALL OTHER clients
    socketio.emit('player_joined', newPlayer, broadcast = True, include_self = False)
    print(f"Emitted player_joined for {sid} to other clients.")

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

@socketio.on('disconnect')
def handle_disconnect(reason = None):
    sid = request.sid
    if sid in players:
        print(f"Client disconnected: {sid}. Reason: {reason}")
        del players[sid]
        if sid in queuedActions:
            del queuedActions[sid]
        #Notify all other clients that the player left
        socketio.emit('player_left', sid, broadcast = True)

# Server Initialization #
def start_game_loop():
    # Ensures the game loop background task is started only once
    global _game_loop_started
    if not _game_loop_started:
        socketio.start_background_task(target = game_loop)
        _game_loop_started = True

#Start the loop! :)
start_game_loop()
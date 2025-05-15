import eventlet
eventlet.monkey_patch()

import os
import random
from flask import Flask, render_template, request, Blueprint
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECURITY_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev_security_key')

GAME_PATH_PREFIX = '/world-of-the-wand'
game_blueprint = Blueprint('game', __name__, template_folder='templates', static_folder='static', static_url_path='/static/game')

@game_blueprint.route('/')
def index_route():
    return render_template('index.html')

app.register_blueprint(game_blueprint, url_prefix=GAME_PATH_PREFIX)
socketio = SocketIO(app, async_mode="eventlet", path=f"{GAME_PATH_PREFIX}/socket.io")

@app.route('/')
def health_check():
    return "OK", 200

# Game Settings
GRID_WIDTH = 25
GRID_HEIGHT = 20
GAME_TICK_RATE = 2.0

# Game State
players = {}
queuedActions = {}
_game_loop_started = False # Ensure game loop starts only once

def game_loop():
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

                    # Handle local movement and potential scene transitions
                    new_x_local = player['x'] + dx
                    new_y_local = player['y'] + dy
                    
                    scene_changed = False
                    transition_message = ""

                    # Check X-axis scene transition
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

                    # Check Y-axis scene transition
                    # Note: Positive Y for scene coords is often South, Negative Y is North
                    if new_y_local < 0:
                        player['scene_y'] -= 1 
                        player['y'] = GRID_HEIGHT - 1
                        scene_changed = True
                        if not transition_message: # Avoid double message if changing corner
                             transition_message = f"Tome scribbles: You emerge on the northern edge of a new area ({player['scene_x']},{player['scene_y']})."
                    elif new_y_local >= GRID_HEIGHT:
                        player['scene_y'] += 1
                        player['y'] = 0
                        scene_changed = True
                        if not transition_message:
                            transition_message = f"Tome scribbles: You emerge on the southern edge of a new area ({player['scene_x']},{player['scene_y']})."
                    else:
                        # Only update y if not part of x-transition that already set it
                        if not (new_x_local < 0 or new_x_local >= GRID_WIDTH) :
                            player['y'] = new_y_local
                    
                    player['char'] = newChar
                    
                    if scene_changed:
                        # TODO: Load/generate new scene data and send to player.
                        # TODO: Notify players in old/new scenes about player movement.
                        socketio.emit('lore_message', {'message': transition_message, 'type': 'system'}, room=sid)

                queuedActions[sid] = None 
        
        # TODO: Optimize game_state_update to only send relevant data (e.g., players in the same scene).
        # This currently sends all player states to all clients.
        current_player_states = list(players.values())
        socketio.emit('game_state_update', current_player_states)
        
@socketio.on('connect')
def handle_connect(auth=None):
    sid = request.sid 
    newPlayer = {
        'id': sid,
        'scene_x': 0,   # Default scene
        'scene_y': 0,
        'x': 0,         # Spawn at 0,0 of the scene
        'y': 0,
        'char': random.choice(['^', 'v', '<', '>'])
    }
    players[sid] = newPlayer
    queuedActions[sid] = None 

    # For initial state, send only other players in the same scene
    otherPlayersInScene = {
        playerID: playerData for playerID, playerData in players.items()
        if playerID != sid and \
           playerData['scene_x'] == newPlayer['scene_x'] and \
           playerData['scene_y'] == newPlayer['scene_y']
    }
    
    emit('initial_state', {
        'player': newPlayer,
        'grid_width': GRID_WIDTH,
        'grid_height': GRID_HEIGHT,
        'other_players': otherPlayersInScene,
        'tick_rate': GAME_TICK_RATE
    })

    # Notify other players (ideally only those in the same scene)
    # This broadcast needs refinement for scene-based visibility.
    try:
        socketio.server.emit('player_joined', newPlayer, skip_sid=sid, namespace='/') 
    except Exception as e:
        print(f"ERROR emitting player_joined directly: {e}")
        try:
            socketio.emit('player_joined', newPlayer, skip_sid=sid)
        except Exception as e_fallback:
            print(f"ERROR with fallback player_joined: {e_fallback}")

@socketio.on('disconnect')
def handle_disconnect(reason=None):
    sid = request.sid 
    if sid in players:
        player_data = players[sid] # Get player data before deleting
        del players[sid]
        if sid in queuedActions: 
            del queuedActions[sid]
        
        # Notify other players (ideally only those in the same scene)
        # This broadcast needs refinement for scene-based visibility.
        try:
            socketio.server.emit('player_left', player_data['id'], skip_sid=sid, namespace='/')
        except Exception as e:
            print(f"ERROR emitting player_left directly: {e}")
            try:
                socketio.emit('player_left', player_data['id'], broadcast=True) # Fallback
            except Exception as e_fallback:
                print(f"ERROR with fallback player_left: {e_fallback}")

@socketio.on('queue_command')
def handle_queue_command(data):
    sid = request.sid
    if sid in players:
        actionType = data.get('type')
        if actionType in ['move', 'look', 'cast']: # Allow 'cast' to be queued
            queuedActions[sid] = data 
            emit('action_queued', {'message': "Your will has been noted. Awaiting cosmic alignment..."})
        else:
            emit('action_failed', {'message': "Your old brain is wrought with confusion. (unknown command. Type '?' for help.)"})
    else:
        emit('action_failed', {'message': "A lost soul whispers commands, but your connection to it was too weak... (connection problem)"})

def start_game_loop():
    global _game_loop_started
    if not _game_loop_started:
        socketio.start_background_task(target=game_loop)
        _game_loop_started = True

start_game_loop()

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
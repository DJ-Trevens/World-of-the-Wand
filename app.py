import eventlet
eventlet.monkey_patch()

import os
from flask import Flask, render_template
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECURITY_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev_security_key') #change later!
socketio = SocketIO(app, async_mode = 'eventlet')

# Game #
GRID_WIDTH = 20
GRID_HEIGHT = 15

# Player #
# in a real game, this would be a dictionary of players by Session ID
# for now, it's singleplayer for simplicity.
player_state = {
    'id': None, # Set to Session ID on connect
    'x': GRID_WIDTH // 2,
    'y': GRID_HEIGHT // 2,
    'char': '^'
}

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    # in a real game, generate a unique ID or use socket.sid
    # Here, I just update the single player_state
    # Opening multiple tabs will control the same wizard (lol)
    player_state['id'] = 'singleplayer'
    print(f"Client connected: {player_state['id']}")
    # Send initial state to the new client
    emit('initial_state', {
        'player':       player_state,
        'grid_width':   GRID_WIDTH,
        'grid_height':  GRID_HEIGHT
    })

@socketio.on('player_move')
def handle_player_move(data):
    # data will contain {'dx': change_in_x, 'dy': change_in_y, 'new_char": char}
    dx = data.get('dx', 0)
    dy = data.get('dy', 0)
    new_char = data.get('new_char', player_state['char'])

    #Update player position (with boundary checks)
    new_x = player_state['x'] + dx
    new_y = player_state['y'] + dy

    if 0 <= new_x < GRID_WIDTH:
        player_state['x'] = new_x
    if 0 <= new_y < GRID_HEIGHT:
        player_state['y'] = new_y

    # since observable cone might be decided based on the char,
    # maybe determine it server-side based on dx & dy
    player_state['char'] = new_char

    # Broadcast updated state to ALL connected clients
    # later, only send updates to relevant clients
    emit('player_update', player_state, broadcast = True)

@socketio.on('disconnect')
def handle_disconnect():
    print(f"Client disconmnected") # Add logic when support for multiple players is added

#   if __name__ == '__main__':
#       socketio.run(app, debug = True, host = '0.0.0.0')
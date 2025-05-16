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
GRID_WIDTH = 20
GRID_HEIGHT = 15
GAME_TICK_RATE = 1.0
SHOUT_MANA_COST = 5

# Game State
players = {}
queuedActions = {}
_game_loop_started = False

def get_player_name(sid):
    return f"Wizard-{sid[:4]}"

def game_loop():
    while True:
        try: 
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
                            chat_data = {
                                'sender_name': get_player_name(sid),
                                'message': message_text,
                                'type': 'say',
                                'scene_coords': f"({player['scene_x']},{player['scene_y']})"
                            }
                            for p_sid, p_data in players.items():
                                if p_data['scene_x'] == player['scene_x'] and p_data['scene_y'] == player['scene_y']:
                                    socketio.emit('chat_message', chat_data, room=p_sid)
                    
                    elif actionType == 'shout':
                        message_text = details.get('message', '')
                        if message_text:
                            if player['current_mana'] >= SHOUT_MANA_COST:
                                player['current_mana'] -= SHOUT_MANA_COST
                                chat_data = {
                                    'sender_name': get_player_name(sid),
                                    'message': message_text,
                                    'type': 'shout',
                                    'scene_coords': f"({player['scene_x']},{player['scene_y']})"
                                }
                                current_scene_x, current_scene_y = player['scene_x'], player['scene_y']
                                adjacent_scenes = [
                                    (current_scene_x, current_scene_y),      
                                    (current_scene_x + 1, current_scene_y),  
                                    (current_scene_x - 1, current_scene_y),  
                                    (current_scene_x, current_scene_y + 1),  
                                    (current_scene_x, current_scene_y - 1)   
                                ]
                                targeted_sids = set()
                                for p_sid, p_data in players.items():
                                    if (p_data['scene_x'], p_data['scene_y']) in adjacent_scenes:
                                        targeted_sids.add(p_sid)
                                
                                for target_sid in targeted_sids:
                                    socketio.emit('chat_message', chat_data, room=target_sid)
                                socketio.emit('lore_message', {'message': f"Tome notes: Your voice booms, costing {SHOUT_MANA_COST} mana!", 'type': 'system'}, room=sid)
                            else:
                                socketio.emit('lore_message', {'message': f"Tome warns: You lack the {SHOUT_MANA_COST} mana to project your voice so powerfully.", 'type': 'event-bad'}, room=sid)

                    queuedActions[sid] = None 
            
            current_player_states = list(players.values())
            socketio.emit('game_state_update', current_player_states)
        except Exception as e:
            print(f"!!! ERROR IN GAME LOOP: {e} !!!") 
            import traceback
            traceback.print_exc() 
        
@socketio.on('connect')
def handle_connect(auth=None):
    sid = request.sid 
    newPlayer = {
        'id': sid,
        'name': get_player_name(sid),
        'scene_x': 0,
        'scene_y': 0,
        'x': GRID_WIDTH // 2, 
        'y': GRID_HEIGHT // 2,
        'char': random.choice(['^', 'v', '<', '>']),
        'max_health': 100,
        'current_health': 100,
        'max_mana': 175, 
        'current_mana': 175,
        'potions': 7,
    }
    players[sid] = newPlayer
    queuedActions[sid] = None 

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

    try:
        socketio.server.emit('player_joined', { 'id': newPlayer['id'], 'name': newPlayer['name'], 'char': newPlayer['char'], 'x': newPlayer['x'], 'y': newPlayer['y'], 'scene_x': newPlayer['scene_x'], 'scene_y': newPlayer['scene_y'] }, skip_sid=sid, namespace='/') 
    except Exception as e:
        print(f"ERROR emitting player_joined directly: {e}")
        try:
            socketio.emit('player_joined', { 'id': newPlayer['id'], 'name': newPlayer['name'], 'char': newPlayer['char'], 'x': newPlayer['x'], 'y': newPlayer['y'], 'scene_x': newPlayer['scene_x'], 'scene_y': newPlayer['scene_y'] }, skip_sid=sid)
        except Exception as e_fallback:
            print(f"ERROR with fallback player_joined: {e_fallback}")

@socketio.on('disconnect')
def handle_disconnect(reason=None):
    sid = request.sid 
    if sid in players:
        player_data = players[sid]
        del players[sid]
        if sid in queuedActions: 
            del queuedActions[sid]
        
        try:
            socketio.server.emit('player_left', player_data['id'], skip_sid=sid, namespace='/')
        except Exception as e:
            print(f"ERROR emitting player_left directly: {e}")
            try:
                socketio.emit('player_left', player_data['id'], broadcast=True)
            except Exception as e_fallback:
                print(f"ERROR with fallback player_left: {e_fallback}")

@socketio.on('queue_command')
def handle_queue_command(data):
    sid = request.sid
    if sid in players:
        actionType = data.get('type')
        if actionType in ['move', 'look', 'cast', 'drink_potion', 'say', 'shout']:
            queuedActions[sid] = data 
            if actionType not in ['drink_potion', 'say', 'shout']: 
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
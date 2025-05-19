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

# --- Game Settings ---
GRID_WIDTH = 20
GRID_HEIGHT = 15
GAME_TICK_RATE = 0.75  # Seconds per tick
SHOUT_MANA_COST = 5
MAX_VIEW_DISTANCE = 8 # Simple square visibility for server-side culling

# --- Game State (Worker-Specific) ---
players = {}  # { sid: {player_data_dict} }
queued_actions = {}  # { sid: {action_data_dict} }
_game_loop_started_in_this_process = False


def get_player_name(sid):
    return f"Wizard-{sid[:4]}"

# --- Server-Side Visibility Logic ---
def is_visible_server(observer_player_data, target_player_data):
    if not observer_player_data or not target_player_data:
        return False
    # Must be in the same scene
    if observer_player_data['scene_x'] != target_player_data['scene_x'] or \
       observer_player_data['scene_y'] != target_player_data['scene_y']:
        return False
    
    # Simple square distance check for now
    # Client-side can use its more complex cone-of-vision logic
    dist_x = abs(observer_player_data['x'] - target_player_data['x'])
    dist_y = abs(observer_player_data['y'] - target_player_data['y'])
    
    return dist_x <= MAX_VIEW_DISTANCE and dist_y <= MAX_VIEW_DISTANCE


# --- Core Game Loop ---
def game_loop():
    my_pid = os.getpid()
    print(f">>>> [{my_pid}] GAME LOOP THREAD HAS STARTED AND IS RUNNING (Tick rate: {GAME_TICK_RATE}s) <<<<")
    loop_count = 0

    while True:
        loop_start_time = time.time()
        loop_count += 1
        
        # Make a copy of actions to process for this tick
        actions_this_tick = dict(queued_actions)
        queued_actions.clear() # Clear the global queue for the next tick's actions

        if loop_count % 10 == 0 or actions_this_tick or len(players) > 0 : # Log periodically or if activity
            print(f"[{my_pid}] Tick {loop_count}: Processing {len(actions_this_tick)} actions for {len(players)} players.")

        # 1. Process Queued Actions
        for sid, action_data in actions_this_tick.items():
            if sid not in players: # Player might have disconnected
                continue
            
            player = players[sid] # Get a reference to the player's data
            action_type = action_data.get('type')
            details = action_data.get('details', {})
            
            # print(f"[{my_pid}] Tick {loop_count}: Player {player['name']} action: {action_type}")

            # --- Action Logic ---
            if action_type == 'move' or action_type == 'look':
                original_scene_x, original_scene_y = player['scene_x'], player['scene_y']
                dx = details.get('dx', 0)
                dy = details.get('dy', 0)
                player['char'] = details.get('newChar', player['char'])
                
                if action_type == 'move':
                    new_x_local = player['x'] + dx
                    new_y_local = player['y'] + dy
                    scene_changed = False
                    transition_message = ""

                    if new_x_local < 0:
                        player['scene_x'] -= 1; player['x'] = GRID_WIDTH - 1; scene_changed = True
                        transition_message = f"Tome scribbles: You emerge on the western edge of a new area ({player['scene_x']},{player['scene_y']})."
                    elif new_x_local >= GRID_WIDTH:
                        player['scene_x'] += 1; player['x'] = 0; scene_changed = True
                        transition_message = f"Tome scribbles: You emerge on the eastern edge of a new area ({player['scene_x']},{player['scene_y']})."
                    else:
                        player['x'] = new_x_local

                    if new_y_local < 0:
                        player['scene_y'] -= 1; player['y'] = GRID_HEIGHT - 1; scene_changed = True
                        if not transition_message: transition_message = f"Tome scribbles: You emerge on the northern edge of a new area ({player['scene_x']},{player['scene_y']})."
                    elif new_y_local >= GRID_HEIGHT:
                        player['scene_y'] += 1; player['y'] = 0; scene_changed = True
                        if not transition_message: transition_message = f"Tome scribbles: You emerge on the southern edge of a new area ({player['scene_x']},{player['scene_y']})."
                    else:
                        if not (new_x_local < 0 or new_x_local >= GRID_WIDTH): player['y'] = new_y_local
                    
                    if scene_changed:
                        socketio.emit('lore_message', {'message': transition_message, 'type': 'system'}, room=sid)
                        # Scene change notifications for other players are handled by them seeing player in new scene context
                # No specific message for 'look' from server, client handles local feedback

            elif action_type == 'drink_potion':
                if player['potions'] > 0:
                    player['potions'] -= 1
                    player['current_health'] = min(player['max_health'], player['current_health'] + 15)
                    socketio.emit('lore_message', {'message': "Tome notes: You drink a potion, feeling invigorated!", 'type': 'event-good'}, room=sid)
                else:
                    socketio.emit('lore_message', {'message': "Tome sighs: Your satchel is empty of potions.", 'type': 'event-bad'}, room=sid)
            
            elif action_type == 'say':
                message_text = details.get('message', '')
                if message_text:
                    chat_data = { 'sender_id': sid, 'sender_name': player['name'], 'message': message_text, 'type': 'say', 
                                  'scene_coords': f"({player['scene_x']},{player['scene_y']})" }
                    for p_sid_target, p_data_target in list(players.items()):
                        if p_data_target['scene_x'] == player['scene_x'] and p_data_target['scene_y'] == player['scene_y']:
                            socketio.emit('chat_message', chat_data, room=p_sid_target)

            elif action_type == 'shout':
                message_text = details.get('message', '')
                if message_text:
                    if player['current_mana'] >= SHOUT_MANA_COST:
                        player['current_mana'] -= SHOUT_MANA_COST
                        chat_data = { 'sender_id': sid, 'sender_name': player['name'], 'message': message_text, 'type': 'shout', 
                                      'scene_coords': f"({player['scene_x']},{player['scene_y']})" }
                        for p_sid_target, p_data_target in list(players.items()):
                            if abs(p_data_target['scene_x'] - player['scene_x']) <= 1 and \
                               abs(p_data_target['scene_y'] - player['scene_y']) <= 1: # Current and adjacent scenes
                                socketio.emit('chat_message', chat_data, room=p_sid_target)
                        socketio.emit('lore_message', {'message': f"Tome notes: Your voice booms, costing {SHOUT_MANA_COST} mana!", 'type': 'system'}, room=sid)
                    else:
                        socketio.emit('lore_message', {'message': f"Tome warns: You lack the mana to project your voice so powerfully.", 'type': 'event-bad'}, room=sid)
            
            # players[sid] is already updated as 'player' is a reference to the dict item

        # 2. Broadcast Tailored State Updates
        if players: # Only if there are players to update
            all_players_snapshot = list(players.values()) # Use a snapshot for consistent visibility checks

            for recipient_sid, recipient_player_data in list(players.items()): # Iterate copy
                if recipient_sid not in players: continue # Player might have disconnected during this tick

                visible_other_players_list = []
                for other_player in all_players_snapshot:
                    if other_player['id'] == recipient_sid: # Don't send self as "other"
                        continue
                    if is_visible_server(recipient_player_data, other_player):
                        visible_other_players_list.append({
                            'id': other_player['id'], 'name': other_player['name'],
                            'x': other_player['x'], 'y': other_player['y'], 'char': other_player['char'],
                            'scene_x': other_player['scene_x'], 'scene_y': other_player['scene_y']
                        })
                
                # Ensure the recipient_player_data is the most up-to-date version
                # (it would have been updated in the action processing phase if they acted)
                payload_for_client = {
                    'self_player_data': players[recipient_sid], # Send the current state of the recipient
                    'visible_other_players': visible_other_players_list,
                    # Future: current_scene_details, items_on_ground_in_view, etc.
                }
                socketio.emit('game_update', payload_for_client, room=recipient_sid)
            
            if loop_count % 5 == 0 : # Log less frequently
                 print(f"[{my_pid}] Tick {loop_count}: Sent 'game_update' to {len(players)} connected players.")

        # Maintain tick rate
        elapsed_time = time.time() - loop_start_time
        sleep_duration = GAME_TICK_RATE - elapsed_time
        if sleep_duration > 0:
            socketio.sleep(sleep_duration)
        elif sleep_duration < -0.1: 
            print(f"!!! [{my_pid}] GAME LOOP OVERRUN: Tick {loop_count} took {elapsed_time:.3f}s. Budget was {GAME_TICK_RATE}s. Over by {abs(sleep_duration):.3f}s. !!!")

# --- Socket.IO Event Handlers ---
@socketio.on('connect')
def handle_connect_event(auth=None): # Renamed to avoid conflict if there's a flask 'connect'
    sid = request.sid
    my_pid = os.getpid()
    print(f"[{my_pid}] Connect event for SID {sid}.")

    player_name = get_player_name(sid)
    new_player_data = {
        'id': sid, 'name': player_name, 
        'scene_x': 0, 'scene_y': 0,
        'x': GRID_WIDTH // 2, 'y': GRID_HEIGHT // 2, 
        'char': random.choice(['^', 'v', '<', '>']),
        'max_health': 100, 'current_health': 100, 
        'max_mana': 175, 'current_mana': 175,
        'potions': 7, 'gold': 0
    }
    players[sid] = new_player_data
    queued_actions[sid] = None 

    print(f"[{my_pid}] Player {player_name} ({sid}) added. Total players: {len(players)}")

    # Prepare initial state for the new player
    other_players_in_start_scene = []
    for p_sid_iter, p_data_iter in list(players.items()):
        if p_sid_iter != sid and \
           p_data_iter['scene_x'] == new_player_data['scene_x'] and \
           p_data_iter['scene_y'] == new_player_data['scene_y']:
            other_players_in_start_scene.append({
                'id': p_data_iter['id'], 'name': p_data_iter['name'],
                'x': p_data_iter['x'], 'y': p_data_iter['y'], 'char': p_data_iter['char'],
                'scene_x': p_data_iter['scene_x'], 'scene_y': p_data_iter['scene_y']
            })

    emit_ctx('initial_game_data', { # Renamed event for clarity
        'player_data': new_player_data,
        'other_players_in_scene': other_players_in_start_scene,
        'grid_width': GRID_WIDTH,
        'grid_height': GRID_HEIGHT,
        'tick_rate': GAME_TICK_RATE
    })

    # Notify players already in the new player's starting scene
    # This is slightly redundant as they'll see the player in the next game_update,
    # but can provide a faster "X has entered" message if desired client-side.
    new_player_broadcast_data = {
        'id': new_player_data['id'], 'name': new_player_data['name'],
        'x': new_player_data['x'], 'y': new_player_data['y'], 'char': new_player_data['char'],
        'scene_x': new_player_data['scene_x'], 'scene_y': new_player_data['scene_y']
    }
    for p_sid_iter, p_data_iter in list(players.items()):
        if p_sid_iter != sid and \
           p_data_iter['scene_x'] == new_player_data['scene_x'] and \
           p_data_iter['scene_y'] == new_player_data['scene_y']:
            socketio.emit('player_entered_your_scene', new_player_broadcast_data, room=p_sid_iter)
    
    print(f"[{my_pid}] Sent 'initial_game_data' to {player_name} and 'player_entered_your_scene' to relevant players.")


@socketio.on('disconnect')
def handle_disconnect_event(): # Renamed
    sid = request.sid
    my_pid = os.getpid()
    
    player_left_data = players.pop(sid, None) # Remove player and get their data
    if sid in queued_actions:
        del queued_actions[sid]

    if player_left_data:
        print(f"[{my_pid}] Player {player_left_data['name']} ({sid}) disconnected. Total players: {len(players)}")
        player_left_broadcast_data = {'id': sid, 'name': player_left_data['name']}
        # Notify players who were in the same scene as the disconnected player
        for p_sid_iter, p_data_iter in list(players.items()): # Iterate remaining players
            if p_data_iter['scene_x'] == player_left_data['scene_x'] and \
               p_data_iter['scene_y'] == player_left_data['scene_y']:
                socketio.emit('player_exited_your_scene', player_left_broadcast_data, room=p_sid_iter)
    else:
        print(f"[{my_pid}] Disconnect for SID {sid} but player not in 'players' dict.")


@socketio.on('queue_player_action') # Renamed event
def handle_queue_player_action(data):
    sid = request.sid
    my_pid = os.getpid()

    if sid not in players:
        print(f"[{my_pid}] Action from unknown/disconnected SID {sid}: {data}")
        emit_ctx('action_feedback', {'success': False, 'message': "Cannot perform action: Player not recognized."})
        return

    player_name = players[sid]['name']
    action_type = data.get('type')
    # print(f"[{my_pid}] Action '{action_type}' received from {player_name} ({sid}).")

    valid_actions = ['move', 'look', 'drink_potion', 'say', 'shout'] # etc.
    if action_type not in valid_actions:
        emit_ctx('action_feedback', {'success': False, 'message': f"Unknown action type: {action_type}."})
        return
    
    # Overwrite any previous action for this tick; players get one action per tick.
    queued_actions[sid] = data 
    emit_ctx('action_feedback', {'success': True, 'message': "Your will is noted..."})


# --- Gunicorn Hook Integration ---
def start_game_loop_for_worker():
    """Called by gunicorn_config.py in the post_fork hook."""
    global _game_loop_started_in_this_process
    my_pid = os.getpid()

    if not _game_loop_started_in_this_process:
        print(f"[{my_pid}] Worker process: Attempting to start game loop background task...")
        try:
            socketio.start_background_task(target=game_loop)
            _game_loop_started_in_this_process = True
            print(f"[{my_pid}] Worker process: Game loop background task initiated. Watch for 'GAME LOOP THREAD HAS STARTED' message.")
        except Exception as e:
            print(f"!!! [{my_pid}] Worker process: FAILED TO START GAME LOOP: {e} !!!")
            traceback.print_exc()
    else:
        print(f"[{my_pid}] Worker process: Game loop already marked as started in this process.")

# --- Local Development Startup ---
if __name__ == '__main__':
    my_pid = os.getpid()
    print(f"[{my_pid}] Starting Flask-SocketIO server for LOCAL DEVELOPMENT...")
    start_game_loop_for_worker() # For local dev, start it directly
    socketio.run(app, debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), use_reloader=False)
else:
    # This runs when Gunicorn imports app.py for the master or worker (before forking for master)
    my_pid = os.getpid()
    print(f"[{my_pid}] App module loaded by Gunicorn (PID: {my_pid}). Game loop for worker will be started by post_fork hook.")
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
        
        current_process_players = dict(players) # Take a snapshot of players for this tick
        current_process_actions = dict(queued_actions)
        queued_actions.clear()

        if not current_process_players:
            if loop_count % 60 == 0: # Log only occasionally if no players
                print(f"[{my_pid}] Tick {loop_count}: Game loop running, but 'players' dictionary is currently empty in this process.")
        else:
            print(f"[{my_pid}] Tick {loop_count}: Loop start. Players in this process ({len(current_process_players)}): {list(current_process_players.keys())}")

        # 1. Process Queued Actions
        for sid, action_data in current_process_actions.items():
            if sid not in current_process_players:
                print(f"[{my_pid}] Tick {loop_count}: Action for {sid} but player not in current_process_players snapshot.")
                continue
            
            player = current_process_players[sid] # Use the snapshot for reading
            # IMPORTANT: To modify the actual player data, you need to access the global `players` dict
            # For example: players[sid]['x'] += 1
            # The `player` variable here is a copy if current_process_players was a deep copy.
            # If it's a shallow copy (like dict(players)), `player` is a reference to the inner dict, so modifications will reflect.
            # Let's assume shallow copy behavior for now, which is default for dict().

            action_type = action_data.get('type')
            details = action_data.get('details', {})
            print(f"[{my_pid}] Tick {loop_count}: Player {player['name']} ({sid}) action: {action_type}, Details: {details}")

            if action_type == 'move' or action_type == 'look':
                # ... (rest of action logic - ensure it modifies `players[sid]`, not just the local `player` copy if it were a deep copy) ...
                # Example:
                players[sid]['char'] = details.get('newChar', players[sid]['char'])
                if action_type == 'move':
                    # ... calculations for new_x_local, new_y_local ...
                    # Update the main players dictionary
                    # players[sid]['x'] = new_x_local 
                    # players[sid]['y'] = new_y_local
                    # players[sid]['scene_x'] = new_scene_x 
                    # ... etc. ...
                    # (Your existing move logic should be fine here as it modifies player directly)
                    original_scene_x, original_scene_y = players[sid]['scene_x'], players[sid]['scene_y']
                    dx = details.get('dx', 0)
                    dy = details.get('dy', 0)
                    players[sid]['char'] = details.get('newChar', players[sid]['char']) # Update global
                    
                    if action_type == 'move':
                        new_x_local = players[sid]['x'] + dx
                        new_y_local = players[sid]['y'] + dy
                        scene_changed = False
                        transition_message = ""

                        if new_x_local < 0:
                            players[sid]['scene_x'] -= 1; players[sid]['x'] = GRID_WIDTH - 1; scene_changed = True
                            transition_message = f"Tome scribbles: You emerge on the western edge of a new area ({players[sid]['scene_x']},{players[sid]['scene_y']})."
                        elif new_x_local >= GRID_WIDTH:
                            players[sid]['scene_x'] += 1; players[sid]['x'] = 0; scene_changed = True
                            transition_message = f"Tome scribbles: You emerge on the eastern edge of a new area ({players[sid]['scene_x']},{players[sid]['scene_y']})."
                        else:
                            players[sid]['x'] = new_x_local

                        if new_y_local < 0:
                            players[sid]['scene_y'] -= 1; players[sid]['y'] = GRID_HEIGHT - 1; scene_changed = True
                            if not transition_message: transition_message = f"Tome scribbles: You emerge on the northern edge of a new area ({players[sid]['scene_x']},{players[sid]['scene_y']})."
                        elif new_y_local >= GRID_HEIGHT:
                            players[sid]['scene_y'] += 1; players[sid]['y'] = 0; scene_changed = True
                            if not transition_message: transition_message = f"Tome scribbles: You emerge on the southern edge of a new area ({players[sid]['scene_x']},{players[sid]['scene_y']})."
                        else:
                            if not (new_x_local < 0 or new_x_local >= GRID_WIDTH): players[sid]['y'] = new_y_local
                        
                        if scene_changed:
                            socketio.emit('lore_message', {'message': transition_message, 'type': 'system'}, room=sid)
                        print(f"[{my_pid}] Tick {loop_count}: Player {players[sid]['name']} new state after move: {players[sid]}")

            elif action_type == 'drink_potion': # Ensure this modifies players[sid]
                if players[sid]['potions'] > 0:
                    players[sid]['potions'] -= 1
                    players[sid]['current_health'] = min(players[sid]['max_health'], players[sid]['current_health'] + 15)
                    socketio.emit('lore_message', {'message': "Tome notes: You drink a potion, feeling invigorated!", 'type': 'event-good'}, room=sid)
                else:
                    socketio.emit('lore_message', {'message': "Tome sighs: Your satchel is empty of potions.", 'type': 'event-bad'}, room=sid)
            # ... (other actions, ensure they modify players[sid] if needed) ...

        # 2. Broadcast Tailored State Updates
        if current_process_players: # Check the snapshot taken at the start of the tick
            updated_all_players_snapshot = list(players.values()) # Get the latest state after actions

            num_updates_sent = 0
            for recipient_sid, _ in current_process_players.items(): # Iterate based on who was present at tick start
                if recipient_sid not in players: # Player might have disconnected during action processing
                    print(f"[{my_pid}] Tick {loop_count}: Player {recipient_sid} disconnected before game_update could be sent.")
                    continue

                recipient_player_data_for_visibility_check = players[recipient_sid] # Use current data for visibility
                visible_other_players_list = []
                for other_player_data in updated_all_players_snapshot:
                    if other_player_data['id'] == recipient_sid: 
                        continue
                    if is_visible_server(recipient_player_data_for_visibility_check, other_player_data):
                        visible_other_players_list.append({
                            'id': other_player_data['id'], 'name': other_player_data['name'],
                            'x': other_player_data['x'], 'y': other_player_data['y'], 'char': other_player_data['char'],
                            'scene_x': other_player_data['scene_x'], 'scene_y': other_player_data['scene_y']
                        })
                
                payload_for_client = {
                    'self_player_data': players[recipient_sid], # Send the LATEST state of the recipient
                    'visible_other_players': visible_other_players_list,
                }
                # print(f"[{my_pid}] Tick {loop_count}: Preparing to send game_update to {recipient_sid}. Self: {payload_for_client['self_player_data']['x']},{payload_for_client['self_player_data']['y']}. Others: {len(visible_other_players_list)}")
                socketio.emit('game_update', payload_for_client, room=recipient_sid)
                num_updates_sent += 1
            
            if num_updates_sent > 0 : 
                 print(f"[{my_pid}] Tick {loop_count}: Sent 'game_update' to {num_updates_sent} players.")
        
        elapsed_time = time.time() - loop_start_time
        sleep_duration = GAME_TICK_RATE - elapsed_time
        if sleep_duration > 0:
            socketio.sleep(sleep_duration)
        elif sleep_duration < -0.05: # Allow small overrun
            print(f"!!! [{my_pid}] GAME LOOP OVERRUN: Tick {loop_count} took {elapsed_time:.4f}s. Budget was {GAME_TICK_RATE}s. Over by {abs(sleep_duration):.4f}s. !!!")

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
# gunicorn_config.py
import os

# If you need to access your Flask app instance for the socketio object,
# you'd typically import it here. However, for starting a background task
# where the socketio instance is global in app.py, we might be able to
# call a function defined in app.py directly.

# It's cleaner if app.py exposes a function to start the loop.

def post_fork(server, worker):
    # This code runs in each Gunicorn worker process after it's forked.
    worker_pid = os.getpid()
    server.log.info(f"Worker PID {worker_pid}: post_fork hook executing.")
    
    # Assuming your app.py has a function like `start_game_loop_for_worker()`
    # that uses the global `socketio` instance from app.py.
    try:
        from app import start_game_loop_if_not_running # Import the function
        server.log.info(f"Worker PID {worker_pid}: Attempting to start game loop via post_fork.")
        start_game_loop_if_not_running()
    except Exception as e:
        server.log.error(f"Worker PID {worker_pid}: Error in post_fork trying to start game loop: {e}")
        import traceback
        traceback.print_exc()

# You can also set other Gunicorn settings here if needed
# For example, if Render isn't picking up your worker class from the Procfile:
# worker_class = 'eventlet'
# workers = 1 # Already set by Render, but good to be aware
bind = "0.0.0.0:" + os.environ.get("PORT", "10000") # Ensure Gunicorn binds to the port Render expects
# gunicorn_config.py
import os
import traceback # Ensure traceback is imported for logging

# --- Gunicorn Settings ---
# Define the address and port to bind to. Render sets the PORT environment variable.
bind = "0.0.0.0:" + os.environ.get("PORT", "10000")

# Specify the worker class for eventlet (essential for Flask-SocketIO with async_mode="eventlet")
worker_class = 'eventlet'

# Number of worker processes. For Flask-SocketIO with eventlet and no external message queue,
# starting with 1 worker is often the simplest and recommended approach.
# Render might override this based on your plan, but 1 is a good default.
workers = 1

# Optional: Gunicorn logging settings
# loglevel = 'debug'  # For more verbose Gunicorn logs (can be 'info', 'warning', 'error', 'critical')
# accesslog = '-'     # Log access requests to stdout
# errorlog = '-'      # Log Gunicorn errors to stdout (stderr by default)

# --- Server Hooks ---
def post_fork(server, worker):
    """
    This hook is called in a Gunicorn worker process after it has been forked
    from the master and after the worker has loaded the application.
    This is the correct place to start background tasks specific to a worker.
    """
    worker_pid = os.getpid()
    # Use Gunicorn's logger for messages from hooks
    server.log.info(f"Worker PID {worker_pid}: post_fork hook executing.")
    
    try:
        # Import the function from your app.py that starts the game loop
        # Ensure app.py is in the Python path (it should be by default if in the root)
        from app import start_game_loop_if_not_running 
        
        server.log.info(f"Worker PID {worker_pid}: Attempting to start game loop via post_fork from app.start_game_loop_if_not_running.")
        start_game_loop_if_not_running() # Call the function to start the loop
    except ImportError:
        server.log.error(f"Worker PID {worker_pid}: CRITICAL - Could not import 'start_game_loop_if_not_running' from 'app'. Ensure app.py and this function exist.")
        # Optionally re-raise or handle more gracefully if this is a fatal setup error for the worker
    except Exception as e:
        server.log.error(f"Worker PID {worker_pid}: CRITICAL - Error in post_fork when trying to start game loop: {e}")
        # Log the full traceback for debugging
        server.log.error(traceback.format_exc())

# You can also set other Gunicorn settings here if needed
# For example, if Render isn't picking up your worker class from the Procfile:
# worker_class = 'eventlet'
# workers = 1 # Already set by Render, but good to be aware
bind = "0.0.0.0:" + os.environ.get("PORT", "10000") # Ensure Gunicorn binds to the port Render expects
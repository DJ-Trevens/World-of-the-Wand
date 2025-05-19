# gunicorn_config.py
import os
import traceback

# --- Gunicorn Settings ---
bind = "0.0.0.0:" + os.environ.get("PORT", "10000")
worker_class = 'eventlet'
workers = 1
# loglevel = 'info' # Set to 'debug' for more verbose Gunicorn logs if needed
# accesslog = '-'   # Log access to stdout
# errorlog = '-'    # Log Gunicorn errors to stdout

# --- Server Hooks ---
def post_fork(server, worker):
    worker_pid = os.getpid()
    server.log.info(f"Worker PID {worker_pid}: post_fork hook executing.")
    
    try:
        from app import start_game_loop_for_worker # Specific function to call
        server.log.info(f"Worker PID {worker_pid}: Attempting to start game loop via app.start_game_loop_for_worker.")
        start_game_loop_for_worker() # Call the designated function
    except ImportError:
        server.log.error(f"Worker PID {worker_pid}: CRITICAL - Could not import 'start_game_loop_for_worker' from 'app'. Ensure app.py and this function exist.")
    except Exception as e:
        server.log.error(f"Worker PID {worker_pid}: CRITICAL - Error in post_fork when trying to start game loop: {e}")
        server.log.error(traceback.format_exc())
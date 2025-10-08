import logging
import atexit
from flask import Flask, jsonify

from .token_manager import TokenManager
from .order_scheduler import OrderScheduler
from .config import config
from saxo_sdk.client import SaxoClient
from saxo_sdk.formatter import CustomFormatter

# ==============================
# Flask app initialization
# ==============================
app = Flask(__name__)

# ==============================
# Logging setup
# ==============================
# send to root logger
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)  # Set to DEBUG for detailed output, change to INFO to reduce verbosity
# Clear existing handlers (optional, avoids duplicates)
logger.handlers.clear()
# Create a console handler
console_handler = logging.StreamHandler()
# Define and set formatter with clean timestamp
console_handler.setFormatter(CustomFormatter())
# Add handler to logger
logger.addHandler(console_handler)

# Create a file handler to write logs to a file
file_handler = logging.FileHandler("app.log")  # you can change the filename/path
file_handler.setLevel(logging.DEBUG)  # Set the level for file logging
fileformatter = logging.Formatter("[%(levelname)s] %(asctime)s - %(message)s", datefmt="%H:%M:%S")
file_handler.setFormatter(fileformatter)
logger.addHandler(file_handler)

# Initialize TokenManager and OrderScheduler globally
logger.debug("Initializing TokenManager and OrderScheduler...")
token_manager = TokenManager()
order_scheduler = OrderScheduler(token_manager)

# ==============================
# Config loading
# ==============================
logger.debug("Loaded configuration:")
logger.debug(f"REDIRECT_URI: {config.REDIRECT_URI}")
logger.debug(f"SIMULATION_MODE: {config.SIMULATION_MODE}")
logger.debug(f"AUTH_ENDPOINT: {config.AUTH_ENDPOINT}")
logger.debug(f"TOKEN_ENDPOINT: {config.TOKEN_ENDPOINT}")
logger.debug(f"CLIENT_ID: {config.CLIENT_ID}")
logger.debug(f"BASE_URL: {config.BASE_URL}")
logger.debug(f"TOKEN_FILE: {config.TOKEN_FILE}")
logger.debug(f"TOKEN_REFRESH_INTERVAL_SECONDS: {config.TOKEN_REFRESH_INTERVAL_SECONDS}")
logger.debug(f"ORDER_SCHEDULE_TIME: {config.ORDER_SCHEDULE_TIME}")
logger.debug(f"ORDER_DETAILS: {config.ORDER_DETAILS}")



# ==============================
# Background task management
# ==============================
def start_background_tasks():
    logger.info("Starting background tasks...")
    token_manager.start_refresh_thread()
    order_scheduler.start_scheduler_thread()

def stop_background_tasks():
    logger.info("Stopping background tasks...")
    token_manager.stop_refresh_thread()
    order_scheduler.stop_scheduler_thread()

# Register cleanup function to run on app exit
atexit.register(stop_background_tasks)

@app.route('/')
def home():
    logger.info("Home endpoint accessed.")
    return "Saxo Trading App is running!"

@app.route('/status')
def status():
    logger.info("Status endpoint accessed.")
    token_status = "Active" if token_manager.get_access_token() else "Inactive/Expired"
    return jsonify({
        "app_status": "running",
        "token_manager_status": token_status,
        "order_scheduler_status": "running" if order_scheduler._scheduler_thread and order_scheduler._scheduler_thread.is_alive() else "stopped",
        "next_order_time": order_scheduler.order_schedule_time_str
    })

@app.route('/authenticate')
def authenticate():
    logger.info("Authenticate endpoint accessed.")
    try:
        token_manager.authenticate()
        return jsonify({"message": "Authentication initiated. Check console for URL and token file for updates."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def startSaxoServer():
    logger.debug("Starting Flask app...")
    logger.debug("Starting background tasks...")
    start_background_tasks()
    app.run(debug=True, use_reloader=False) # use_reloader=False to prevent threads from starting twice

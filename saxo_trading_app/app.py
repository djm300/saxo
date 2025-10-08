import logging
import atexit
from flask import Flask, jsonify, request, render_template_string, redirect, url_for, render_template

from .order_scheduler import OrderScheduler
from .config import Config
from saxo_sdk.client import SaxoClient
from saxo_sdk.formatter import CustomFormatter
from .dictionary import uic_dict, accounts_by_key, accounts_by_name

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

# ==============================
# Config loading
# ==============================
config = Config()
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

# Initialize SaxoClient and OrderScheduler globally
logger.debug("Initializing SaxoClient and OrderScheduler...")
saxoclient = SaxoClient(
    client_id=config.CLIENT_ID,
    redirect_uri=config.REDIRECT_URI,
    auth_endpoint=config.AUTH_ENDPOINT,
    token_endpoint=config.TOKEN_ENDPOINT,
    token_file=config.TOKEN_FILE,
    baseurl=config.BASE_URL)

order_scheduler = OrderScheduler(saxoclient, config)



# ==============================
# Background task management
# ==============================
def start_background_tasks():
    logger.info("Starting background tasks...")
    saxoclient.start_refresh_thread()
    order_scheduler.start_scheduler_thread()

def stop_background_tasks():
    logger.info("Stopping background tasks...")
    saxoclient.stop_refresh_thread()
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
    return jsonify({
        "app_status": "running",
        "saxoclient state": saxoclient.current_state(),
        "order_scheduler_status": "running" if order_scheduler._scheduler_thread and order_scheduler._scheduler_thread.is_alive() else "stopped",
        "next_order_time": order_scheduler.order_schedule_time_str
    })

@app.route('/authenticate', methods=['GET', 'POST'])
def authenticate():
    logger.info("Authenticate endpoint accessed.")

    if request.method == 'POST':
        # Auth code submission handling
        if saxoclient.current_state() == SaxoClient.STATE_WAITING_FOR_AUTHORIZATION_CODE:
            authorization_code = request.form.get('authorization_code')
            if authorization_code:
                saxoclient.get_token(authorization_code)
            return redirect(url_for('authenticate'))  # assumes your route is named "authenticate"
        elif saxoclient.current_state() == SaxoClient.STATE_WAITING_FOR_TOKEN:
            return redirect(url_for('status'))  # No authentication needed, redirect to status page

    # Handle GET requests and initial state checks
    current_state = saxoclient.current_state()

    logger.info(f"SaxoClient current state: {current_state}")

    auth_url = ""
    if current_state == SaxoClient.STATE_NOT_AUTHENTICATED or current_state == SaxoClient.STATE_ERROR:
        auth_url = saxoclient.get_authorization_url()
        return render_template("authenticate.html", auth_url=auth_url, current_state=current_state), 200
    elif current_state == SaxoClient.STATE_WAITING_FOR_AUTHORIZATION_CODE:
        auth_url = saxoclient.get_authorization_url()
        return render_template("authenticate.html", auth_url=auth_url, current_state=current_state), 200
    elif current_state == SaxoClient.STATE_WAITING_FOR_TOKEN:
        return render_template("authenticate.html", auth_url=auth_url, current_state=current_state), 200
    else:
        return render_template("authenticate.html", auth_url=auth_url, current_state=current_state), 200


@app.route('/portfolio')
def portfolio():
    logger.info("Portfolio endpoint accessed.")
    if not saxoclient._is_authenticated():
        return jsonify({"error": "Not authenticated"}), 401
    portfolio = saxoclient.get_portfolio()
    return jsonify(portfolio)

@app.route('/positions')
def positions():
    logger.info("Positions endpoint accessed.")
    if not saxoclient._is_authenticated():
        return jsonify({"error": "Not authenticated"}), 401
    positions = saxoclient.get_positions()
    return jsonify(positions)

@app.route('/positionstable')
def positionstable():
    logger.info("Positions table endpoint accessed.")
    if not saxoclient._is_authenticated():
        return jsonify({"error": "Not authenticated"}), 401
    raw_data = saxoclient.get_positions()

    positions = []
    for item in raw_data.get("Data", []):
        base = item.get("PositionBase", {})
        dynamic = item.get("PositionView", {})
        positions.append({
            "account_id": accounts_by_key[base.get("AccountId")]["name"],
            "uic": base.get("Uic"),
            "name": uic_dict.get(base.get("Uic"), "N/A"),
            "asset_type": base.get("AssetType"),
            "amount": base.get("Amount"),
            "profit_loss": dynamic.get("ProfitLossOnTrade"),
        })

    positions.sort(key=lambda x: (x["account_id"], x["name"]))

    return render_template('positions.html', positions=positions,raw_data=raw_data)

@app.route('/order1')
def order1():
    logger.info("Positions table endpoint accessed.")
    if not saxoclient._is_authenticated():
        return jsonify({"error": "Not authenticated"}), 401
    # LIMIT order 1 IWDA for a low price in EUR in portfolio Ouders
    order_data={
        'AccountKey': accounts_by_name['Ouders']['id'],
        'Amount': 1,
        'BuySell': 'Buy',
        'OrderType': 'Limit',
        'OrderPrice': 50,  # Set a low limit price to avoid immediate execution
        'Uic': 50629,
        'AssetType': 'Etf',
        'ManualOrder': True,
	    'OrderDuration': {
	        'DurationType': 'DayOrder'
	    }
    }
    saxoclient.place_order(order_data)
    return render_template_string("<html><p>ok</p></html>")
    

def startSaxoServer():
    logger.debug("Starting Flask app...")
    logger.debug("Starting background tasks...")
    start_background_tasks()
    app.run(debug=True, use_reloader=False) # use_reloader=False to prevent threads from starting twice

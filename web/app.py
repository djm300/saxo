import atexit
import logging
import os

from flask import Flask, jsonify, redirect, render_template, request, url_for

from shared.client import SaxoClient
from shared.formatter import CustomFormatter
from shared.runtime import create_client, load_runtime_config

# ==============================
# Flask app initialization
# ==============================
app = Flask(__name__)

# ==============================
# Logging setup
# ==============================
# send to root logger
logger = logging.getLogger()
logger.setLevel(
    logging.DEBUG
)  # Set to DEBUG for detailed output, change to INFO to reduce verbosity
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
config = load_runtime_config()
logger.debug("Loaded configuration:")
logger.debug("Environment: %s", "sim" if config.simulation_mode else "live")
# Initialize SaxoClient globally
logger.debug("Initializing SaxoClient...")
saxoclient = create_client(config)


def _instrument_name(client, uic, asset_type, cache):
    if not uic:
        return "N/A"
    cache_key = (uic, asset_type or "")
    if cache_key in cache:
        return cache[cache_key]
    try:
        instrument = client.get_instrument_by_uic(uic, asset_type=asset_type or "Stock")
        name = instrument.get("Symbol") or instrument.get("Description") or "N/A"
    except Exception:
        name = "N/A"
    cache[cache_key] = name
    return name


# ==============================
# Background task management
# ==============================
def start_background_tasks():
    logger.info("Starting background tasks...")
    saxoclient.start_refresh_thread(config.token_refresh_interval_seconds)


def stop_background_tasks():
    logger.info("Stopping background tasks...")
    saxoclient.stop_refresh_thread()


# Register cleanup function to run on app exit
atexit.register(stop_background_tasks)


@app.route("/")
def home():
    logger.info("Home endpoint accessed.")
    return "Saxo read-only positions app is running!"


@app.route("/status")
def status():
    logger.info("Status endpoint accessed.")
    return jsonify(
        {
            "app_status": "running",
            "saxoclient state": saxoclient.current_state(),
            "mode": "read-only",
        }
    )


@app.route("/authenticate", methods=["GET", "POST"])
def authenticate():
    logger.info("Authenticate endpoint accessed.")

    authorization_code = request.values.get("authorization_code") or request.args.get("code")
    oauth_error = request.args.get("error")
    if oauth_error:
        logger.error("OAuth error returned by provider: %s", oauth_error)

    if authorization_code and saxoclient.current_state() in (
        SaxoClient.STATE_WAITING_FOR_AUTHORIZATION_CODE,
        SaxoClient.STATE_NOT_AUTHENTICATED,
        SaxoClient.STATE_ERROR,
    ):
        saxoclient.get_token(authorization_code)
        if saxoclient._is_authenticated():
            return redirect(url_for("status"))
        return redirect(url_for("authenticate"))

    if (
        request.method == "POST"
        and saxoclient.current_state() == SaxoClient.STATE_WAITING_FOR_TOKEN
    ):
        return redirect(url_for("status"))

    current_state = saxoclient.current_state()
    logger.info(f"SaxoClient current state: {current_state}")

    auth_url = ""
    if current_state in (
        SaxoClient.STATE_NOT_AUTHENTICATED,
        SaxoClient.STATE_ERROR,
        SaxoClient.STATE_WAITING_FOR_AUTHORIZATION_CODE,
    ):
        auth_url = saxoclient.get_authorization_url()

    return render_template(
        "authenticate.html",
        auth_url=auth_url,
        current_state=current_state,
        redirect_uri=config.REDIRECT_URI,
    ), 200


@app.route("/oauth/callback")
def oauth_callback():
    # Provider redirect target: forwards code/error into the existing authenticate flow.
    return redirect(url_for("authenticate", **request.args))


@app.route("/positions")
def positions():
    logger.info("Positions endpoint accessed.")
    if not saxoclient._is_authenticated():
        return jsonify({"error": "Not authenticated"}), 401
    positions = saxoclient.get_positions()
    return jsonify(positions)


@app.route("/positionstable")
def positionstable():
    logger.info("Positions table endpoint accessed.")
    if not saxoclient._is_authenticated():
        return jsonify({"error": "Not authenticated"}), 401
    raw_data = saxoclient.get_positions()

    positions = []
    instrument_cache = {}
    for item in raw_data.get("Data", []):
        base = item.get("PositionBase", {})
        dynamic = item.get("PositionView", {})
        account_id = base.get("AccountId")
        positions.append(
            {
                "account_id": account_id,
                "uic": base.get("Uic"),
                "name": _instrument_name(
                    saxoclient, base.get("Uic"), base.get("AssetType"), instrument_cache
                ),
                "asset_type": base.get("AssetType"),
                "amount": base.get("Amount"),
                "profit_loss": dynamic.get("ProfitLossOnTrade"),
            }
        )

    positions.sort(key=lambda x: (str(x.get("asset_type") or ""), str(x.get("name") or "")))

    return render_template("positions.html", positions=positions, raw_data=raw_data)


def startSaxoServer():
    logger.debug("Starting Flask app...")
    logger.debug("Starting background tasks...")
    start_background_tasks()
    app.run(
        host=os.getenv("SAXO_HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "1").lower() in {"1", "true", "yes", "on"},
        use_reloader=False,
    )  # use_reloader=False to prevent threads from starting twice

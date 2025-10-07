import os
import json
import logging

logger = logging.getLogger()

def load_config_value(key, default=None, json_config=None):
    # 1. Try environment variable
    value = os.environ.get(key)
    if value:
        logger.debug(f"Loaded {key}={value} from environment variable.")
        return value
    # 2. Try JSON config
    if json_config and key in json_config:
        value =  json_config[key]
        logger.debug(f"Loaded {key}={value} from params.json.")
        return value
    # 3. Fallback to default
    logger.debug(f"Using default value {key}={default}.")
    return default

def load_params_json():
    json_config = {}
    try:
        with open("params.json", "r") as f:
            json_config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("params.json not found or invalid. Skipping.")
        pass
    return json_config

# Load parameters from params.json
params_config = load_params_json()

# --- Core Saxo API Configuration ---
REDIRECT_URI = load_config_value(
    "REDIRECT_URI",
    default="https://djm300.github.io/saxo/oauth-redirect.html",
    json_config=params_config
)

# Ensure REDIRECT_URI is a string, not a tuple
if isinstance(REDIRECT_URI, tuple):
    REDIRECT_URI = REDIRECT_URI[0]

SIMULATION_MODE_STR = load_config_value(
    "SIMULATION_MODE",
    default="True", # Default to simulation mode for safety
    json_config=params_config
)
SIMULATION_MODE = (SIMULATION_MODE_STR.lower() == "true")

if SIMULATION_MODE:
    AUTH_ENDPOINT = load_config_value("SAXO_AUTH_ENDPOINT", "https://sim.logonvalidation.net/authorize", json_config=params_config)
    TOKEN_ENDPOINT = load_config_value("SAXO_TOKEN_ENDPOINT", "https://sim.logonvalidation.net/token", json_config=params_config)
    TOKEN_FILE = "saxo_tokens_sim.json"
    CLIENT_ID = load_config_value("SAXO_CLIENT_ID", "89da08eeb25c428a9099f768cdb1696e", json_config=params_config)
    BASE_URL = "https://gateway.saxobank.com/sim/openapi"
    logger.info("Running in SIMULATION mode.")
else:
    AUTH_ENDPOINT = load_config_value("SAXO_AUTH_ENDPOINT", "https://live.logonvalidation.net/authorize", json_config=params_config)
    TOKEN_ENDPOINT = load_config_value("SAXO_TOKEN_ENDPOINT", "https://live.logonvalidation.net/token", json_config=params_config)
    TOKEN_FILE = "saxo_tokens_live.json"
    CLIENT_ID = load_config_value("SAXO_CLIENT_ID", "28d17c462242447f94c4b0767c41a552", json_config=params_config)
    BASE_URL = "https://gateway.saxobank.com/openapi"
    logger.info("Running in LIVE mode.")

# --- Application Specific Configuration ---
TOKEN_REFRESH_INTERVAL_SECONDS = 300 # Refresh token every 5 minutes

# Example Order Details (customize as needed)
ORDER_SCHEDULE_TIME = "09:30" # HH:MM format
ORDER_DETAILS = {
    'AccountKey': "YOUR_ACCOUNT_KEY_HERE", # Replace with actual account key
    'Amount': 1,
    'BuySell': 'Buy',
    'OrderType': 'Limit',
    'OrderPrice': 50,
    'Uic': 50629, # Example UIC for "ETF MSCI World"
    'AssetType': 'Etf',
    'ManualOrder': True,
    'OrderDuration': {
        'DurationType': 'DayOrder'
    }
}

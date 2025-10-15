import os
import json
import logging

logger = logging.getLogger()

# Helper function to extract key from a JSON config or environment variable
def _load_config_value(key, default=None, json_config=None):
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

# Helper function to load params.json if it exists
def _load_params_json():
    json_config = {}
    try:
        with open("params.json", "r") as f:
            json_config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("params.json not found or invalid. Skipping.")
        pass
    return json_config

class Config:
    def __init__(self):
        # Load parameters from params.json
        params_config = _load_params_json()

        # --- Core Saxo API Configuration ---
        self.REDIRECT_URI = _load_config_value(
            "REDIRECT_URI",
            default="https://djm300.github.io/saxo/oauth-redirect.html",
            json_config=params_config
        )
        # Ensure REDIRECT_URI is a string, not a tuple
        if isinstance(self.REDIRECT_URI, tuple):
            self.REDIRECT_URI = self.REDIRECT_URI[0]

        SIMULATION_MODE_STR = _load_config_value(
            "SIMULATION_MODE",
            default="True", # Default to simulation mode for safety
            json_config=params_config
        )
        self.SIMULATION_MODE = (SIMULATION_MODE_STR.lower() == "true")

        if self.SIMULATION_MODE:
            self.AUTH_ENDPOINT = _load_config_value("SIM_AUTH_ENDPOINT", "https://sim.logonvalidation.net/authorize", json_config=params_config)
            self.TOKEN_ENDPOINT = _load_config_value("SIM_TOKEN_ENDPOINT", "https://sim.logonvalidation.net/token", json_config=params_config)
            self.TOKEN_FILE = "saxo_tokens_sim.json"
            self.CLIENT_ID = _load_config_value("SIM_CLIENT_ID", "89da08eeb25c428a9099f768cdb1696e", json_config=params_config)
            self.BASE_URL = "https://gateway.saxobank.com/sim/openapi"
            logger.info("Running in SIMULATION mode.")
        else:
            self.AUTH_ENDPOINT = _load_config_value("LIVE_AUTH_ENDPOINT", "https://live.logonvalidation.net/authorize", json_config=params_config)
            self.TOKEN_ENDPOINT = _load_config_value("LIVE_TOKEN_ENDPOINT", "https://live.logonvalidation.net/token", json_config=params_config)
            self.TOKEN_FILE = "saxo_tokens_live.json"
            self.CLIENT_ID = _load_config_value("LIVE_CLIENT_ID", "28d17c462242447f94c4b0767c41a552", json_config=params_config)
            self.BASE_URL = "https://gateway.saxobank.com/openapi"
            logger.info("Running in LIVE mode.")

        # --- Application Specific Configuration ---
        self.TOKEN_REFRESH_INTERVAL_SECONDS = 300 # Refresh token every 5 minutes

        self.ORDERS = params_config.get("ORDERS", {})
        logger.debug(f"Loaded ORDERS: {self.ORDERS}")



if __name__ == "__main__":
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s - %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(console_handler)



    # Global instance of Config to be imported by other modules
    config = Config()

    logger.debug("Config called directly. Printing configuration:")
    logger.debug(f"Simulation is {config.SIMULATION_MODE}")
    logger.debug(f'REDIRECT_URI: {config.REDIRECT_URI}')
    logger.debug(f'Client ID: {config.CLIENT_ID}')
    logger.debug(f'AUTH_ENDPOINT: {config.AUTH_ENDPOINT}')
    logger.debug(f'TOKEN_ENDPOINT: {config.TOKEN_ENDPOINT}')
    logger.debug(f'BASE_URL: {config.BASE_URL}')    
    logger.debug(f'TOKEN_FILE: {config.TOKEN_FILE}')
    logger.debug(f'TOKEN_REFRESH_INTERVAL_SECONDS: {config.TOKEN_REFRESH_INTERVAL_SECONDS}')
    logger.debug("End of configuration.")

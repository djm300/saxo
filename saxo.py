import os
import json
from saxo_sdk.client import SaxoClient
from saxo_sdk.formatter import CustomFormatter
import logging
import json




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


# Load parameters from params.json if it exists
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

def load_config():
    json_config = {}
    try:
        with open("params.json", "r") as f:
            json_config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass  # Silently skip if params.json is missing or invalid

    CLIENT_ID = load_config_value(
        "CLIENT_ID", 
        default="c310e92ffc7c481190119ea98c507a2e", 
        json_config=json_config
    )
    REDIRECT_URI = load_config_value(
        "REDIRECT_URI", 
        default="https://djm300.github.io/saxo/oauth-redirect.html", 
        json_config=json_config
    ),
    SIMULATION_MODE = load_config_value(
        "SIMULATION_MODE", 
        default=True, 
        json_config=json_config
    )
    return CLIENT_ID, REDIRECT_URI, SIMULATION_MODE

CLIENT_ID, REDIRECT_URI, SIMULATION_MODE = load_config()

if isinstance(REDIRECT_URI, tuple):
    REDIRECT_URI = REDIRECT_URI[0]  # Unpack if it's a single-element tuple


# --- Environment Configuration ---
# Determine if running in simulation or live mode
if SIMULATION_MODE != "False":
    SIMULATION_MODE = True
else:
    SIMULATION_MODE = False

# Define endpoints based on mode
if SIMULATION_MODE:
    AUTH_ENDPOINT = os.environ.get("SAXO_AUTH_ENDPOINT", "https://sim.logonvalidation.net/authorize")
    TOKEN_ENDPOINT = os.environ.get("SAXO_TOKEN_ENDPOINT", "https://sim.logonvalidation.net/token")
    TOKEN_FILE = "saxo_tokens_sim.json" # File to store simulation tokens
    logging.info("Running in SIMULATION mode.")
else:
    AUTH_ENDPOINT = os.environ.get("SAXO_AUTH_ENDPOINT", "https://live.logonvalidation.net/authorize")
    TOKEN_ENDPOINT = os.environ.get("SAXO_TOKEN_ENDPOINT", "https://live.logonvalidation.net/token")
    TOKEN_FILE = "saxo_tokens_live.json" # File to store live tokens
    logging.info("Running in LIVE mode.")

#CLIENT_ID = ''
#CLIENT_ID = input("CLIENT_ID not set in environment. Please enter it: ")

# --- Main Execution ---
def main():
    logging.info("Initializing SaxoClient...")
    client = SaxoClient(
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT_URI,
        auth_endpoint=AUTH_ENDPOINT,
        token_endpoint=TOKEN_ENDPOINT,
        token_file=TOKEN_FILE
    )




'''
    # --- Authentication Flow ---
    # Check if tokens exist and are valid, otherwise initiate authorization
    if not client.auth_client.tokens or client.auth_client._is_access_token_expired():
        logging.info("No valid token found or token expired. Initiating authorization flow.")
        auth_url = client.get_authorization_url()
        logging.info(f"Please visit this URL in your browser to authorize the application:")
        logging.info(f"{auth_url}")
        
        # Prompt user to paste the authorization code received after redirection
        code = input("Paste the authorization code from the redirect URL here: ").strip()
        
        if code:
            try:
                token_data = client.get_token(code)
                logging.info("Authorization successful! Tokens acquired and saved.")
                # print(f"Access Token (first 20 chars): {token_data.get('access_token', '')[:20]}...")
            except Exception as e:
                logging.error(f"Error acquiring token: {e}")
                return
        else:
            logging.error("No authorization code provided. Exiting.")
            return
    else:
        logging.info("Using existing valid access token.")
        # print(f"Access Token (first 20 chars): {client.auth_client.tokens.get('access_token', '')[:20]}...")
'''


'''
    # --- Portfolio Functionality Example ---
    print("\n--- Fetching Portfolio ---")
    try:
        portfolio = client.get_portfolio()
        print("Portfolio Data:")
        print(json.dumps(portfolio, indent=2))
        
        positions = client.get_positions()
        print("\nPositions Data:")
        print(json.dumps(positions, indent=2))
    except Exception as e:
        print(f"Error fetching portfolio data: {e}")
    */

    print("\nSaxo SDK example usage finished.")
'''
if __name__ == "__main__":
    main()

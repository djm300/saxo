import os
import json
from saxo_sdk.client import SaxoClient
import logging

# ==============================
# Logging setup
# ==============================
logging.basicConfig(
    level=logging.DEBUG,  # change to INFO for less output
    format="[%(levelname)s] %(asctime)s - %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)



# --- Configuration ---
# It's recommended to load sensitive information from environment variables or a config file
# For demonstration purposes, we'll use placeholders.
# In a real application, you would replace these with your actual SAXO API credentials.
CLIENT_ID = os.environ.get("SAXO_CLIENT_ID", "c310e92ffc7c481190119ea98c507a2e") # Example from saxo-auth.py
CLIENT_SECRET = os.environ.get("SAXO_CLIENT_SECRET", "67f8314ea810459e8ddc725a4cfd5568") # Example from saxo-auth.py
REDIRECT_URI = os.environ.get("SAXO_REDIRECT_URI", "https://djm300.github.io/saxo/oauth-redirect.html")

# --- Environment Configuration ---
# Determine if running in simulation or live mode
SIMULATION_MODE = os.environ.get("SIMULATION", "True").lower() == "true"

# Define endpoints based on mode
if SIMULATION_MODE:
    AUTH_ENDPOINT = os.environ.get("SAXO_AUTH_ENDPOINT", "https://sim.logonvalidation.net/authorize")
    TOKEN_ENDPOINT = os.environ.get("SAXO_TOKEN_ENDPOINT", "https://sim.logonvalidation.net/token")
    TOKEN_FILE = "saxo_tokens_sim.json" # File to store simulation tokens
    logging.debug("Running in SIMULATION mode.")
else:
    AUTH_ENDPOINT = os.environ.get("SAXO_AUTH_ENDPOINT", "https://live.logonvalidation.net/authorize")
    TOKEN_ENDPOINT = os.environ.get("SAXO_TOKEN_ENDPOINT", "https://live.logonvalidation.net/token")
    TOKEN_FILE = "saxo_tokens_live.json" # File to store live tokens
    logging.debug("Running in LIVE mode.")

    CLIENT_ID = ''
    CLIENT_ID = input("CLIENT_ID not set in environment. Please enter it: ")

    CLIENT_SECRET = ''
    CLIENT_SECRET = input("CLIENT_ID not set in environment. Please enter it: ")
# --- Main Execution ---
def main():
    logging.info("Initializing SaxoClient...")
    client = SaxoClient(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        auth_endpoint=AUTH_ENDPOINT,
        token_endpoint=TOKEN_ENDPOINT,
        token_file=TOKEN_FILE,
        scope="" # Empty string 
    )

    # --- Authentication Flow ---
    # Check if tokens exist and are valid, otherwise initiate authorization
    if not client.auth_client.tokens or client.auth_client._is_expired():
        print("No valid token found or token expired. Initiating authorization flow.")
        auth_url = client.get_authorization_url()
        print(f"Please visit this URL in your browser to authorize the application:")
        print(f"{auth_url}")
        
        # Prompt user to paste the authorization code received after redirection
        code = input("Paste the authorization code from the redirect URL here: ").strip()
        
        if code:
            try:
                token_data = client.get_token(code)
                print("Authorization successful! Tokens acquired and saved.")
                # print(f"Access Token (first 20 chars): {token_data.get('access_token', '')[:20]}...")
            except Exception as e:
                print(f"Error acquiring token: {e}")
                return
        else:
            print("No authorization code provided. Exiting.")
            return
    else:
        print("Using existing valid access token.")
        # print(f"Access Token (first 20 chars): {client.auth_client.tokens.get('access_token', '')[:20]}...")

    # --- Portfolio Functionality Example ---
    '''
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

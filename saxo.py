import os
import json
from saxo_sdk.client import SaxoClient
from saxo_sdk.formatter import CustomFormatter
import logging
import json

uic_dict = {
    50629: "ETF MSCI World",
    1636: "ASML",
    36465: "WisdomTree GOLD",
    10307078: "Pinduoduo",
    773599: "Google",
    36962: "EVS",
    261: "MSFT",
    8953538: "Lithium",
    37609176: "NOVO",
    43337: "Lotus",
    25449122: "Bitcoin ETF",
    6460562: "S&P500 ETF",
    46634080: "ASR opties"
}

# Single source of account data
accounts_by_key = {
    "98900/1575456EUR": {'name': "Ouders", 'id': "zHBpid7mvLiq476MPFcX7TKO2Ei1gNDDWsz-S0ZDAzA="},
    "98900/1622448EUR": {'name': "Kinderen", 'id': "||I-eOXemnJUt|T53kVP|qDxTqPUysN36UILHCsJVlc="},
    "98900/1599306EUR": {'name': "AutoInvest", 'id': "s2sy3q0vZkcNK0-qLEFrN-jN-XLgBpFHrN7zVZcFJK4="}
}

# Build secondary lookup dictionaries
accounts_by_name = {v['name']: {'key': k, 'id': v['id']} for k, v in accounts_by_key.items()}
accounts_by_id = {v['id']: {'key': k, 'name': v['name']} for k, v in accounts_by_key.items()}


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
    return REDIRECT_URI, SIMULATION_MODE

REDIRECT_URI, SIMULATION_MODE = load_config()

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
    CLIENT_ID = "89da08eeb25c428a9099f768cdb1696e" #  simulation client ID
    logging.info("Running in SIMULATION mode.")
else:
    AUTH_ENDPOINT = os.environ.get("SAXO_AUTH_ENDPOINT", "https://live.logonvalidation.net/authorize")
    TOKEN_ENDPOINT = os.environ.get("SAXO_TOKEN_ENDPOINT", "https://live.logonvalidation.net/token")
    TOKEN_FILE = "saxo_tokens_live.json" # File to store live tokens
    CLIENT_ID = "28d17c462242447f94c4b0767c41a552" # live client ID
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
        token_file=TOKEN_FILE,
        baseurl="https://gateway.saxobank.com/sim/openapi" if SIMULATION_MODE else "https://gateway.saxobank.com/openapi"
    )


    # --- Portfolio Functionality Example ---
    print("\n--- Fetching Portfolio ---")
    try:
        portfolio = client.get_portfolio()
        #print("Portfolio Data:", json.dumps(portfolio, indent=2))
        print("Available Cash:", json.dumps(portfolio.get("CashBalance", {}), indent=2))
        
        positions = client.get_positions()
        #print("Positions Data:", json.dumps(positions, indent=2))   
        # Extract data into a summary table
        position_list = positions.get("Data", [])
        positions_summary = []

        for position in position_list:
            uic = position.get("PositionBase", {}).get("Uic", "N/A")
            type = position.get("PositionBase", {}).get("AssetType", "N/A")
            accountid = position.get("PositionBase", {}).get("AccountId", "N/A")
            accountname = ''
            if accountid != "N/A":
                if accountid in accounts_by_id:
                    accountname = accounts_by_id[accountid]
                else:
                    accountname = "N/A"
            name = ''
            if uic != "N/A":
                if uic in uic_dict:
                    name = uic_dict[uic]
                elif type == "Stock":
                    instrument = client.get_instrument_by_uic(uic)
                    name = instrument.get("Symbol", "N/A")
            price = position.get("PositionView", {}).get("CurrentPrice", "N/A")
            amount = position.get("PositionBase", {}).get("Amount", "N/A")
            profitlossontrade = position.get("PositionView", {}).get("ProfitLossOnTrade", "N/A")


            positions_summary.append([uic, name, type, price, amount, profitlossontrade, accountname])

        # Print the summary table
        for row in positions_summary:
            print(f"{row[0]:<20} {row[1]:<15} {row[2]:<10} {row[3]:<15} {row[4]:<15}"  f"{row[5]:<15} {row[6]:<10}")


        #print(client.get_instrument_by_uic(50629).get("Symbol", "N/A"))

        #accounts = client.get_accounts()
        #print("Account Data:", json.dumps(accounts, indent=2))


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
        order = client.place_order(order_data)

    except Exception as e:
        print(f"Error fetching data: {e}")


if __name__ == "__main__":
    main()

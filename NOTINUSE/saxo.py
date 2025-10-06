import requests
import json
import time

# === CONFIG ===
BASE_URL = "https://gateway.saxobank.com/sim/openapi"  # SIM (sandbox). Use https://gateway.saxobank.com/openapi for live.
CLIENT_ID = "21326625"
CLIENT_SECRET = "QsmwRUP48WD3tBTQeq|INg=="
REDIRECT_URI = "https://yourapp/callback"
ACCESS_TOKEN = None
REFRESH_TOKEN = None

# === AUTHENTICATION ===
def authenticate():
    """
    Normally you’d use OAuth2 authorization code flow.
    For a skeleton, assume you’ve already obtained an access token.
    """
    global ACCESS_TOKEN
    ACCESS_TOKEN = "paste_access_token_here"  # Temporary for testing
    return ACCESS_TOKEN

def headers():
    return {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

# === ACCOUNT INFO ===
def get_accounts():
    url = f"{BASE_URL}/port/v1/accounts/me"
    resp = requests.get(url, headers=headers())
    resp.raise_for_status()
    return resp.json()

# === TRADES / ORDERS ===
def get_orders():
    url = f"{BASE_URL}/trade/v2/orders"
    resp = requests.get(url, headers=headers())
    resp.raise_for_status()
    return resp.json()

def place_order(account_id, uic, buy_sell="Buy", amount=1):
    """
    Place a market order, e.g. to buy an ETF.
    - account_id: string from get_accounts()
    - uic: Saxo instrument ID (for ETF, stock, etc.)
    """
    url = f"{BASE_URL}/trade/v2/orders"
    order = {
        "AccountKey": account_id,
        "Uic": uic,
        "AssetType": "Stock",     # Or "ETF", "Bond", etc.
        "BuySell": buy_sell,
        "Amount": amount,
        "OrderType": "Market",
        "OrderDuration": {"DurationType": "DayOrder"}
    }
    resp = requests.post(url, headers=headers(), data=json.dumps(order))
    resp.raise_for_status()
    return resp.json()

# === EXAMPLE USAGE ===
if __name__ == "__main__":
    authenticate()

    print("Accounts:")
    accounts = get_accounts()
    print(json.dumps(accounts, indent=2))

    print("\nOrders:")
    orders = get_orders()
    print(json.dumps(orders, indent=2))

    # Example: Place ETF order
    # etf_uic = 123456  # Find correct UIC from Saxo's instrument search
    # account_id = accounts["Data"][0]["AccountKey"]
    # result = place_order(account_id, etf_uic, "Buy", 10)
    # print(json.dumps(result, indent=2))

import os
import json
from saxo_sdk.client import SaxoClient

# --- Configuration ---
# It's recommended to load sensitive information from environment variables or a config file
# For demonstration purposes, we'll use placeholders.
# In a real application, you would replace these with your actual SAXO API credentials.
CLIENT_ID = os.environ.get("SAXO_CLIENT_ID", "c310e92ffc7c481190119ea98c507a2e") # Example from saxo-auth.py
CLIENT_SECRET = os.environ.get("SAXO_CLIENT_SECRET", "67f8314ea810459e8ddc725a4cfd5568") # Example from saxo-auth.py
REDIRECT_URI = os.environ.get("SAXO_REDIRECT_URI", "https://djm300.github.io/saxo/oauth-redirect.html")
AUTH_ENDPOINT = os.environ.get("SAXO_AUTH_ENDPOINT", "https://sim.logonvalidation.net/authorize")
TOKEN_ENDPOINT = os.environ.get("SAXO_TOKEN_ENDPOINT", "https://sim.logonvalidation.net/token")
TOKEN_FILE = "saxo_tokens.json" # File to store tokens

# --- Main Execution ---
def main():
    print("Initializing SaxoClient...")
    client = SaxoClient(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        auth_endpoint=AUTH_ENDPOINT,
        token_endpoint=TOKEN_ENDPOINT,
        token_file=TOKEN_FILE,
        scope="trading portfolio" # Example scope, adjust as needed
    )

    # --- Authentication Flow ---
    # Check if tokens exist and are valid, otherwise initiate authorization
    if not client.auth_client.tokens or client.auth_client._is_expired():
        print("No valid token found or token expired. Initiating authorization flow.")
        auth_url = client.get_authorization_url()
        print(f"Please visit this URL in your browser to authorize the application:")
        print(auth_url)
        
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

    # --- Orders Functionality Example ---
    print("\n--- Placing a Sample Order ---")
    # NOTE: This is a placeholder. Actual order details depend on SAXO API specifications.
    # You would need to know the correct instrument IDs, order types, etc.
    sample_order_details = {
        "instrument_id": "YOUR_INSTRUMENT_ID", # e.g., "EURUSD" or a specific ID
        "order_type": "LIMIT",
        "price": 1.1000,
        "quantity": 1000,
        "side": "BUY"
    }
    
    # To actually place an order, you'd need valid credentials and a real instrument ID.
    # For this example, we'll just show how the method would be called.
    print("Attempting to place a sample order (using placeholder data)...")
    try:
        # In a real scenario, you'd replace sample_order_details with actual data
        # and uncomment the line below.
        # placed_order = client.place_order(sample_order_details)
        # print("Order placed successfully:")
        # print(json.dumps(placed_order, indent=2))
        
        # For demonstration, we'll just print the placeholder response
        print("Placeholder response for placing order:")
        print(json.dumps({"message": "Order placed placeholder", "order_details": sample_order_details}, indent=2))

        # Example of getting order status (requires a real order ID)
        # print("\n--- Fetching Order Status ---")
        # order_id_to_check = "example_order_id_from_response" # Replace with actual ID
        # order_status = client.get_order_status(order_id_to_check)
        # print(f"Status for order {order_id_to_check}:")
        # print(json.dumps(order_status, indent=2))

    except Exception as e:
        print(f"Error during order placement or status check: {e}")

    print("\n--- Fetching All Orders ---")
    try:
        all_orders = client.get_all_orders()
        print("All Orders:")
        print(json.dumps(all_orders, indent=2))
    except Exception as e:
        print(f"Error fetching all orders: {e}")

    print("\nSaxo SDK example usage finished.")

if __name__ == "__main__":
    main()

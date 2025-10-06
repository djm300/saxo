import logging

# Set up logger for this module
logger = logging.getLogger(__name__)

from .auth import AuthorizationCodeClient
from .portfolio import PortfolioClient
from .orders import OrderClient

class SaxoClient:
    def __init__(self, client_id, client_secret, redirect_uri, auth_endpoint, token_endpoint, token_file='tokens.json', scope="required_scope"):
        self.auth_client = AuthorizationCodeClient(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            auth_endpoint=auth_endpoint,
            token_endpoint=token_endpoint,
            token_file=token_file
        )
        self.portfolio = PortfolioClient(self.auth_client)
        self.orders = OrderClient(self.auth_client)
        self.scope = scope
        logger.info("SaxoClient initialized.")

    def get_authorization_url(self):
        """Get the authorization URL for the user to visit."""
        return self.auth_client.get_authorization_url(scope=self.scope)

    def get_token(self, code):
        """Exchange authorization code for tokens."""
        return self.auth_client.get_token(code)

    def refresh_token(self):
        """Refresh the access token."""
        return self.auth_client.refresh_token()

    def get_portfolio(self):
        """Get the user's portfolio."""
        return self.portfolio.get_portfolio()

    def get_positions(self):
        """Get current positions."""
        return self.portfolio.get_positions()

    def place_order(self, order_details):
        """Place a new order."""
        return self.orders.place_order(order_details)

    def get_order_status(self, order_id):
        """Get the status of a specific order."""
        return self.orders.get_order_status(order_id)

    def get_all_orders(self):
        """Get all orders."""
        return self.orders.get_all_orders()

# Example usage (optional, for testing purposes)
if __name__ == "__main__":
    # Replace with your actual credentials and endpoints
    client = SaxoClient(
        client_id="YOUR_CLIENT_ID",
        client_secret="YOUR_CLIENT_SECRET",
        auth_endpoint="https://sim.logonvalidation.net/authorize",
        token_endpoint="https://sim.logonvalidation.net/token",
        redirect_uri="https://djm300.github.io/saxo/oauth-redirect.html"
    )

    # If no valid token exists, get the authorization URL and prompt for code
    if not client.auth_client.tokens or client.auth_client._is_expired():
        auth_url = client.get_authorization_url()
        print(f"Please visit this URL to authorize: {auth_url}")
        code = input("Paste the authorization code here: ").strip()
        client.get_token(code)
        print("Token acquired.")
    else:
        print("Using existing valid token.")

    # Example of using portfolio and order functionalities
    print("\n--- Portfolio ---")
    portfolio_data = client.get_portfolio()
    print(portfolio_data)

    print("\n--- Orders ---")
    # Example order details (replace with actual structure)
    example_order = {
        "instrument_id": "YOUR_INSTRUMENT_ID", # e.g., "EURUSD" or a specific ID
        "order_type": "LIMIT",
        "price": 100.50,
        "quantity": 10,
        "side": "BUY"
    }
    placed_order = client.place_order(example_order)
    print(placed_order)

    if "order_details" in placed_order:
        order_id = "example_order_id" # Replace with actual order ID from response
        order_status = client.get_order_status(order_id)
        print(order_status)

    all_orders = client.get_all_orders()
    print(all_orders)

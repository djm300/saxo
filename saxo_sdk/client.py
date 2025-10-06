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
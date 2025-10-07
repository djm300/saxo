import logging
import requests # Import the requests library

# Set up logger for this module
logger = logging.getLogger(__name__)

from .auth import AuthorizationCodeClient

class SaxoClient:
    def __init__(self, client_id, redirect_uri, auth_endpoint, token_endpoint, token_file='tokens.json', scope="required_scope", baseurl="https://gateway.saxobank.com/sim/openapi"):
        """Initialize the SaxoClient with authentication and service clients."""
        self.auth_client = AuthorizationCodeClient(
            client_id=client_id,
            redirect_uri=redirect_uri,
            auth_endpoint=auth_endpoint,
            token_endpoint=token_endpoint,
            token_file=token_file,
            baseurl=baseurl # This baseurl will be used for API calls
        )
        # Saxo doesn't use Oauth scopes in the traditional sense, but we include it for compatibility
        self.scope = scope
        logger.info("SaxoClient initialized.")



    def _make_api_request(self, method, endpoint, data=None, params=None):
        """
        Helper method to make API requests.
        Handles base URL, authorization headers, and response parsing.
        """
        if not self.auth_client.tokens or self.auth_client._is_access_token_expired():
            logger.warning("Token expired or not found. Attempting to refresh.")
            try:
                self.refresh_token()
            except Exception as e:
                logger.error(f"Failed to refresh token: {e}")
                raise ConnectionError("Authentication token is invalid or expired, and refresh failed.") from e

        access_token = self.auth_client.tokens.get('access_token')
        if not access_token:
            raise ConnectionError("Access token not available.")

        url = f"{self.auth_client.baseurl}{endpoint}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json" # Assuming JSON for most requests
        }

        try:
            response = requests.request(method, url, headers=headers, data=data, params=params)
            response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise ConnectionError(f"API request to {url} failed.") from e

    def get_authorization_url(self):
        """Get the authorization URL for the user to visit."""
        return self.auth_client.get_authorization_url(scope=self.scope)

    def get_token(self, code):
        """Exchange authorization code for tokens."""
        return self.auth_client.get_token(code)

    def refresh_token(self):
        """Refresh the access token."""
        # Ensure the auth_client has the necessary logic to handle token refresh
        # and update self.auth_client.tokens
        refreshed_tokens = self.auth_client.refresh_token()
        # The AuthorizationCodeClient should handle saving the refreshed tokens
        return refreshed_tokens

    def get_portfolio(self):
        """Get the user's portfolio."""
        # Refactored to use the template method
        logger.info("Fetching portfolio via SaxoClient helper.")
        return self._make_api_request("GET", "/port/v1/balances/me")

    def get_positions(self):
        """Get current positions."""
        # Refactored to use the template method
        logger.info("Fetching positions via SaxoClient helper.")
        return self._make_api_request("GET", "/port/v1/positions/me")

    def place_order(self, order_details):
        """Place a new order."""
        # Refactored to use the template method
        logger.info("Placing order via SaxoClient helper.")
        # Assuming order placement is a POST request to an orders endpoint
        # The exact endpoint needs to be confirmed from SAXO API docs
        return self._make_api_request("POST", "/trade/v1/orders", data=order_details)

    def get_order_status(self, order_id):
        """Get the status of a specific order."""
        # Refactored to use the template method
        logger.info(f"Fetching status for order {order_id} via SaxoClient helper.")
        return self._make_api_request("GET", f"/trade/v1/orders/{order_id}")

    def get_all_orders(self):
        """Get all orders."""
        # Refactored to use the template method
        logger.info("Fetching all orders via SaxoClient helper.")
        return self._make_api_request("GET", "/trade/v1/orders")

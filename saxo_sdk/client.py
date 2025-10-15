import logging
import requests # Import the requests library
import threading

# Set up logger for this module
logger = logging.getLogger(__name__)

from .auth import AuthorizationCodeClient, lifetime_seconds_to_datetime, relative_seconds_to_lifetime_seconds

class SaxoClient:
    # Define possible states for the client
    STATE_NOT_AUTHENTICATED = "not_authenticated"
    STATE_WAITING_FOR_AUTHORIZATION_CODE = "waiting_for_authorization_code"
    STATE_WAITING_FOR_TOKEN = "waiting_for_token"
    STATE_AUTHENTICATED = "authenticated"
    STATE_REFRESHING = "refreshing"
    STATE_ERROR = "error"

    def __init__(self, client_id, redirect_uri, auth_endpoint, token_endpoint, token_file='tokens.json', scope="required_scope", baseurl="https://gateway.saxobank.com/sim/openapi"):
        """Initialize the SaxoClient with authentication and service clients."""
        self._state = self.STATE_NOT_AUTHENTICATED  # Initial state
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
        if not(self.auth_client._is_access_token_expired()):
            self.transition(self.STATE_AUTHENTICATED)
        else:
            self.transition(self.STATE_NOT_AUTHENTICATED) # Set initial state

    def transition(self, new_state):
        """
        Transitions the client to a new state.
        Logs the state change.
        """
        if new_state not in [
            self.STATE_NOT_AUTHENTICATED,
            self.STATE_WAITING_FOR_AUTHORIZATION_CODE,
            self.STATE_WAITING_FOR_TOKEN,
            self.STATE_AUTHENTICATED,
            self.STATE_REFRESHING,
            self.STATE_ERROR,
        ]:
            logger.warning(f"Attempted to transition to an unknown state: {new_state}")
            return

        if self._state != new_state:
            logger.info(f"SaxoClient state transition: {self._state} -> {new_state}")
            self._state = new_state

        if new_state == self.STATE_ERROR:
            logger.error("SaxoClient has entered an ERROR state.")
            self.transition(self.STATE_NOT_AUTHENTICATED)
            self.get_authorization_url()

    def current_state(self):
        """Returns the current state of the client."""
        return self._state

    #########################
    # Authentication methods
    #########################
    def get_authorization_url(self):
        """Get the authorization URL for the user to visit."""
        self.transition(self.STATE_WAITING_FOR_AUTHORIZATION_CODE)
        return self.auth_client.get_authorization_url(scope=self.scope)

    def get_token(self, code):
        """Exchange authorization code for tokens."""
        self.transition(self.STATE_WAITING_FOR_TOKEN)
        try:
            tokens = self.auth_client.get_token(code)
            self.transition(self.STATE_AUTHENTICATED)
            return tokens
        except Exception as e:
            logger.error(f"Failed to get token: {e}")
            self.transition(self.STATE_ERROR)

    def refresh_token(self):
        """Refresh the access token."""
        self.transition(self.STATE_REFRESHING)
        try:
            refreshed_tokens = self.auth_client.refresh_token()
            self.transition(self.STATE_AUTHENTICATED)
            return refreshed_tokens
        except Exception as e:
            logger.error(f"Failed to refresh token: {e}")
            self.transition(self.STATE_ERROR)
            raise

    def _is_authenticated(self):
        """Check if the client is authenticated."""
        return self._state == self.STATE_AUTHENTICATED

    def authenticate_interactive(self):
        """Initiate the authentication process."""
        auth_url = self.get_authorization_url()
        print(f"Please go to the following URL to authorize the application:\n{auth_url}")
        print("After authorization, you will be redirected to your redirect URI.")
        print("Copy the 'code' parameter from the URL and paste it below.")
        code = input("Enter the authorization code: ").strip()
        self.get_token(code)
        print("Authentication successful. Tokens saved.")

    def start_refresh_thread(self, interval=60):
        """Start a background thread to refresh the token periodically."""
        if not hasattr(self, '_refresh_thread') or not self._refresh_thread.is_alive():
            logger.info("Starting token refresh thread...")
            self._stop_event = threading.Event()
            self._refresh_thread = threading.Thread(target=self._refresh_loop, args=(interval,), daemon=True)
            self._refresh_thread.start()
        else:
            logger.info("Token refresh thread is already running.")

    def stop_refresh_thread(self):
        """Stop the background token refresh thread."""
        if hasattr(self, '_refresh_thread') and self._refresh_thread.is_alive():
            logger.info("Stopping token refresh thread...")
            self._stop_event.set()
            self._refresh_thread.join()
        else:
            logger.info("No active token refresh thread to stop.")

    def _refresh_loop(self, interval):
        """Background thread to refresh token periodically."""
        while not self._stop_event.is_set():
            if self.auth_client._is_access_token_expired():
                logger.info("Access token expired or about to expire; refreshing...")
                self.transition(self.STATE_REFRESHING)
                refreshed = self.auth_client.refresh_token()
                if refreshed:
                    logger.info("Token refresh successful.")
                    self.transition(self.STATE_AUTHENTICATED)
                else:
                    logger.error("Token refresh failed; user re-authorization required.")
                    self.get_authorization_url()
                    self.transition(self.STATE_WAITING_FOR_AUTHORIZATION_CODE)
            else:
                expires_at = self.auth_client.tokens.get("access_token_expires_at", 0)
                self.transition(self.STATE_AUTHENTICATED)
                logger.debug(f"Access token valid until {lifetime_seconds_to_datetime(expires_at)}.")
            self._stop_event.wait(interval)




    #########################
    # API methods
    #########################
    def _make_api_request(self, method, endpoint, data=None, params=None):
        """
        Helper method to make API requests.
        Handles base URL, authorization headers, and response parsing.
        """
        if not self.auth_client.tokens or self.auth_client._is_access_token_expired():
            logger.warning("Token expired or not found. Attempting to refresh.")
            self.transition(self.STATE_REFRESHING)
            try:
                self.refresh_token()
                self.transition(self.STATE_AUTHENTICATED)
            except Exception as e:
                logger.error(f"Failed to refresh token: {e}")
                self.transition(self.STATE_ERROR)
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
            response = requests.request(method, url, headers=headers, json=data, params=params)
            #logger.debug(f"API Request: {method} {url} - Status Code: {response.status_code}")
            #logger.debug(f"Headers: {headers}   Data: {data}   Params: {params}")
            #logger.debug(f"Response Text: {response.text}")
            #logger.debug(f"Response Headers: {response.headers}")
            #logger.debug(f"Response Content: {response.content}")
            response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise ConnectionError(f"API request to {url} failed.") from e

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
    
    def get_accounts(self):
        """Get current accounts."""
        # Refactored to use the template method
        logger.info("Fetching accounts via SaxoClient helper.")
        return self._make_api_request("GET", "/port/v1/accounts/me")   

    def get_instrument_by_uic(self,uic):
        # Refactored to use the template method
        logger.info("Fetching accounts via SaxoClient helper.")
        return self._make_api_request("GET", f"/ref/v1/instruments/details/{uic}/Stock")         

    def place_order(self, order_details):
        """Place a new order."""
        # Refactored to use the template method
        logger.info("Placing order via SaxoClient helper.")
        # Assuming order placement is a POST request to an orders endpoint
        # The exact endpoint needs to be confirmed from SAXO API docs
        return self._make_api_request("POST", "/trade/v2/orders", data=order_details)

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

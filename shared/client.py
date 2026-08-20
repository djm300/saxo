import logging
import threading
from datetime import datetime, timedelta, timezone

import requests  # Import the requests library

from .auth import AuthorizationCodeClient, lifetime_seconds_to_datetime, token_file_lock

# Set up logger for this module
logger = logging.getLogger(__name__)


class AuthenticationError(ConnectionError):
    """The API rejected the request because credentials are unavailable/invalid."""


class RateLimitError(ConnectionError):
    """The API rate limit was exceeded."""


class SaxoAPIError(ConnectionError):
    """A non-authentication Saxo API failure."""


class SaxoClient:
    # Define possible states for the client
    STATE_NOT_AUTHENTICATED = "not_authenticated"
    STATE_WAITING_FOR_AUTHORIZATION_CODE = "waiting_for_authorization_code"
    STATE_WAITING_FOR_TOKEN = "waiting_for_token"
    STATE_AUTHENTICATED = "authenticated"
    STATE_REFRESHING = "refreshing"
    STATE_ERROR = "error"

    def __init__(
        self,
        client_id,
        redirect_uri,
        auth_endpoint,
        token_endpoint,
        token_file="tokens.json",
        scope="required_scope",
        baseurl="https://gateway.saxobank.com/sim/openapi",
        trading_enabled=False,
    ):
        """Initialize the SaxoClient with authentication and service clients."""
        self._state = self.STATE_NOT_AUTHENTICATED  # Initial state
        self._refresh_lock = threading.Lock()
        self.trading_enabled = trading_enabled
        self.auth_client = AuthorizationCodeClient(
            client_id=client_id,
            redirect_uri=redirect_uri,
            auth_endpoint=auth_endpoint,
            token_endpoint=token_endpoint,
            token_file=token_file,
            baseurl=baseurl,  # This baseurl will be used for API calls
        )
        # Saxo doesn't use Oauth scopes in the traditional sense, but we include it for compatibility
        self.scope = scope
        logger.info("SaxoClient initialized.")
        if not (self.auth_client._is_access_token_expired()):
            self.transition(self.STATE_AUTHENTICATED)
        else:
            self.transition(self.STATE_NOT_AUTHENTICATED)  # Set initial state

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
            with token_file_lock(self.auth_client.token_file):
                tokens = self.auth_client.get_token(code)
            if tokens and self.auth_client.tokens.get("access_token"):
                self.transition(self.STATE_AUTHENTICATED)
            else:
                self.transition(self.STATE_ERROR)
            return tokens
        except Exception as e:
            logger.error(f"Failed to get token: {e}")
            self.transition(self.STATE_ERROR)

    def refresh_token(self):
        """Refresh the access token."""
        # A request and a long-running serve session can notice expiry at the
        # same time. Serialize refreshes to avoid rotating tokens concurrently.
        with self._refresh_lock:
            with token_file_lock(self.auth_client.token_file):
                # Another process may have refreshed while this process was
                # waiting for the lock. Prefer its fresh token.
                latest_tokens = self.auth_client._load_tokens()
                if isinstance(latest_tokens, dict) and latest_tokens:
                    self.auth_client.tokens = latest_tokens
                    if not self.auth_client._is_access_token_expired():
                        self.transition(self.STATE_AUTHENTICATED)
                        return latest_tokens
                self.transition(self.STATE_REFRESHING)
                try:
                    refreshed_tokens = self.auth_client.refresh_token()
                    if refreshed_tokens and self.auth_client.tokens.get("access_token"):
                        self.transition(self.STATE_AUTHENTICATED)
                    else:
                        logger.warning("Token refresh did not return usable tokens.")
                        self.transition(self.STATE_NOT_AUTHENTICATED)
                    return refreshed_tokens
                except Exception as e:
                    logger.error(f"Failed to refresh token: {e}")
                    # Authentication policy belongs to the runtime session; do
                    # not initiate an interactive flow from a refresh operation.
                    self.transition(self.STATE_NOT_AUTHENTICATED)
                    raise

    def ensure_access_token(self):
        """Ensure a usable access token exists, refreshing it when necessary."""
        if self.auth_client.tokens and not self.auth_client._is_access_token_expired():
            self.transition(self.STATE_AUTHENTICATED)
            return

        try:
            refreshed_tokens = self.refresh_token()
        except Exception as exc:
            raise AuthenticationError("Authentication token refresh failed.") from exc
        if not refreshed_tokens or not self.auth_client.tokens.get("access_token"):
            self.transition(self.STATE_NOT_AUTHENTICATED)
            raise AuthenticationError("Authentication token is unavailable or expired.")

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
        tokens = self.get_token(code)
        if tokens and self.auth_client.tokens.get("access_token"):
            print("Authentication successful. Tokens saved.")
            return True
        print("Authentication failed. No access token was saved.")
        return False

    def start_refresh_thread(self, interval=60):
        """Start a background thread to refresh the token periodically."""
        if not hasattr(self, "_refresh_thread") or not self._refresh_thread.is_alive():
            logger.info("Starting token refresh thread...")
            self._stop_event = threading.Event()
            self._refresh_thread = threading.Thread(
                target=self._refresh_loop, args=(interval,), daemon=True
            )
            self._refresh_thread.start()
        else:
            logger.info("Token refresh thread is already running.")

    def stop_refresh_thread(self):
        """Stop the background token refresh thread."""
        if hasattr(self, "_refresh_thread") and self._refresh_thread.is_alive():
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
                try:
                    self.ensure_access_token()
                    logger.info("Token refresh successful.")
                except AuthenticationError:
                    logger.error("Token refresh failed; user re-authorization is required.")
                    break
            else:
                expires_at = self.auth_client.tokens.get("access_token_expires_at", 0)
                self.transition(self.STATE_AUTHENTICATED)
                logger.debug(
                    f"Access token valid until {lifetime_seconds_to_datetime(expires_at)}."
                )
            self._stop_event.wait(interval)

    #########################
    # API methods
    #########################
    def _make_api_request(self, method, endpoint, data=None, params=None):
        """
        Helper method to make API requests.
        Handles base URL, authorization headers, and response parsing.
        """
        method = method.upper()
        if method != "GET" and not self.trading_enabled:
            raise PermissionError(
                "Trading is disabled. Set TRADING_ENABLED=true and use --execute."
            )

        if not self.auth_client.tokens or self.auth_client._is_access_token_expired():
            logger.warning("Token expired or not found. Attempting to refresh.")
            try:
                self.ensure_access_token()
            except Exception as e:
                logger.error(f"Failed to refresh token: {e}")
                self.transition(self.STATE_NOT_AUTHENTICATED)
                raise ConnectionError(
                    "Authentication token is invalid or expired, and refresh failed."
                ) from e

        access_token = self.auth_client.tokens.get("access_token")
        if not access_token:
            raise ConnectionError("Access token not available.")

        url = f"{self.auth_client.baseurl}{endpoint}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",  # Assuming JSON for most requests
        }

        try:
            response = requests.request(method, url, headers=headers, json=data, params=params)
            # logger.debug(f"API Request: {method} {url} - Status Code: {response.status_code}")
            # logger.debug(f"Headers: {headers}   Data: {data}   Params: {params}")
            # logger.debug(f"Response Text: {response.text}")
            # logger.debug(f"Response Headers: {response.headers}")
            # logger.debug(f"Response Content: {response.content}")
            response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)
            return response.json()
        except requests.exceptions.HTTPError as e:
            status_code = getattr(response, "status_code", None)
            if status_code in (401, 403):
                raise AuthenticationError("Saxo authentication was rejected.") from e
            if status_code == 429:
                raise RateLimitError("Saxo API rate limit exceeded.") from e
            detail = getattr(response, "text", "")
            raise SaxoAPIError(
                f"Saxo API request failed with HTTP {status_code}: {endpoint}"
                + (f" - {detail[:500]}" if detail else "")
            ) from e
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise SaxoAPIError(f"API request to {url} failed.") from e

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

    def get_instrument_by_uic(self, uic, asset_type="Stock"):
        # Refactored to use the template method
        logger.info("Fetching instrument details via SaxoClient helper.")
        return self._make_api_request("GET", f"/ref/v1/instruments/details/{uic}/{asset_type}")

    def get_balances(self):
        return self._make_api_request("GET", "/port/v1/balances/me")

    def get_orders(self):
        return self._make_api_request(
            "GET", "/port/v1/orders/me", params={"FieldGroups": "DisplayAndFormat"}
        )

    def get_order_history(self, limit=200, today=True):
        """Get historical order activities, optionally limited to the local day."""
        params = {"EntryType": "All", "$top": limit, "FieldGroups": "DisplayAndFormat"}
        if today:
            local_now = datetime.now().astimezone()
            start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1) - timedelta(microseconds=1)
            params.update(
                {
                    "FromDateTime": start.astimezone(timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "ToDateTime": end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                }
            )
        return self._make_api_request(
            "GET",
            "/cs/v1/audit/orderactivities",
            params=params,
        )

    def search_instruments(self, query, asset_type=None):
        params = {"Keywords": query}
        if asset_type:
            params["AssetTypes"] = asset_type
        return self._make_api_request("GET", "/ref/v1/instruments", params=params)

    def get_quote(self, uic, asset_type="Stock", account_key=None):
        params = {"Uic": uic, "AssetType": asset_type}
        if account_key:
            params["AccountKey"] = account_key
        return self._make_api_request("GET", "/trade/v1/infoprices", params=params)

    def place_order(self, order):
        request = dict(order)
        request["WithAdvice"] = False
        return self._make_api_request("POST", "/trade/v2/orders", data=request)

    def cancel_orders(self, order_ids, account_key):
        ids = ",".join(str(order_id) for order_id in order_ids)
        return self._make_api_request(
            "DELETE", f"/trade/v2/orders/{ids}", params={"AccountKey": account_key}
        )

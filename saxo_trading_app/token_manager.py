import json
import os
import time
import threading
import logging
from datetime import datetime, timedelta

# Assuming saxo_sdk is accessible in the Python path
# If not, you might need to adjust sys.path or install it as a package
from saxo_sdk.client import SaxoClient
from .config import config

logger = logging.getLogger()


class TokenManager:
    def __init__(self):
        self.client_id = config.CLIENT_ID
        self.redirect_uri = config.REDIRECT_URI
        self.auth_endpoint = config.AUTH_ENDPOINT
        self.token_endpoint = config.TOKEN_ENDPOINT
        self.token_file = config.TOKEN_FILE
        self.base_url = config.BASE_URL
        self.refresh_interval = config.TOKEN_REFRESH_INTERVAL_SECONDS

        self._refresh_thread = None
        self._stop_event = threading.Event()

        # Initialize SaxoClient for token handling and API interactions
        self.saxo_client = SaxoClient(
            client_id=self.client_id,
            redirect_uri=self.redirect_uri,
            auth_endpoint=self.auth_endpoint,
            token_endpoint=self.token_endpoint,
            baseurl=self.base_url,
            token_file=self.token_file
        )
        # Load tokens through the SaxoClient's auth_client
        # The SaxoClient's auth_client will handle loading tokens from the file
        self.saxo_client.auth_client._load_tokens()

    def get_access_token(self):
        # The SaxoClient's _make_api_request method handles token refresh automatically.
        # If we need the token directly, we can access it from the auth_client.
        # We should ensure it's refreshed if needed before returning.
        # The SaxoClient's auth_client has its own _is_access_token_expired method.
        if not self.saxo_client.auth_client.tokens or self.saxo_client.auth_client._is_access_token_expired():
            logger.info("Access token expired or not found. Attempting to refresh via SaxoClient.")
            self.refresh_access_token()
        return self.saxo_client.auth_client.tokens.get("access_token")

    def refresh_access_token(self):
        logger.info("Attempting to refresh access token via SaxoClient.")
        try:
            self.saxo_client.refresh_token()
            logger.info("Access token refreshed successfully via SaxoClient.")
        except Exception as e:
            logger.error(f"Error during token refresh via SaxoClient: {e}. Re-authenticating.")
            self.authenticate()

    def get_authorization_url(self):
        logger.info("Generating authorization URL via SaxoClient...")
        try:
            auth_url = self.saxo_client.get_authorization_url()
            logger.info(f"Authorization URL generated: {auth_url}")
            return auth_url
        except Exception as e:
            logger.error(f"Error generating authorization URL via SaxoClient: {e}")
            raise

    def exchange_code_for_tokens(self, code):
        logger.info("Exchanging authorization code for tokens via SaxoClient...")
        try:
            self.saxo_client.get_token(code) # Use SaxoClient's get_token method
            # The get_token method in SaxoClient (which calls AuthorizationCodeClient's get_token)
            # already handles saving the tokens internally.
            if not self.saxo_client.auth_client.tokens:
                raise Exception("Token exchange failed: No tokens received.")
            logger.info("Tokens exchanged and loaded successfully via SaxoClient.")
        except Exception as e:
            logger.error(f"Error exchanging code for tokens via SaxoClient: {e}")
            raise

    def authenticate(self):
        logger.info("Authentication required. Please direct the user to the authorization URL obtained from get_authorization_url() and then use exchange_code_for_tokens(code) with the received code.")
        # This method now serves as a high-level indicator that authentication is needed.
        # The actual interaction (redirect, input box) is expected to be handled by the calling application.
        # If tokens are still not available after this call, it implies the external authentication flow hasn't completed.
        if not self.saxo_client.auth_client.tokens:
            logger.warning("Authentication flow initiated, but tokens are still not available. Ensure the external authentication process is completed.")

    def _refresh_loop(self):
        while not self._stop_event.is_set():
            try:
                self.refresh_access_token()
            except Exception as e:
                logger.error(f"Error in refresh loop: {e}")
            self._stop_event.wait(self.refresh_interval)

    def start_refresh_thread(self):
        if self._refresh_thread is None or not self._refresh_thread.is_alive():
            logger.info(f"Starting token refresh thread (interval: {self.refresh_interval} seconds).")
            self._stop_event.clear()
            self._refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
            self._refresh_thread.start()
        else:
            logger.info("Token refresh thread is already running.")

    def stop_refresh_thread(self):
        if self._refresh_thread and self._refresh_thread.is_alive():
            logger.info("Stopping token refresh thread.")
            self._stop_event.set()
            self._refresh_thread.join()

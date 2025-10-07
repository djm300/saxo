import requests
import base64
import hashlib
import os
import json
import time
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

# ==============================
# Base OAuth2 Client
# ==============================
class OAuth2Client:
    def __init__(self, client_id, client_secret, redirect_uri, auth_endpoint, token_endpoint, baseurl):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.auth_endpoint = auth_endpoint
        self.token_endpoint = token_endpoint
        self.baseurl = baseurl

    def _get_auth_url(self, **params):
        """Build authorization URL with provided parameters."""
        default_params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri
        }
        default_params.update(params)
        url = self.auth_endpoint + '?' + '&'.join(f"{k}={v}" for k, v in default_params.items())
        logger.debug(f"Built authorization URL: {url}")
        return url

    def _exchange_for_token(self, code, code_verifier):
        """Exchange the authorization code for an access token."""
        logger.debug("Exchanging authorization code for token...")
        response = requests.post(self.token_endpoint, data={
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': self.redirect_uri,
            'code_verifier': code_verifier
        })
        logger.debug(f"Token endpoint status: {response.status_code}")


        logger.debug("Request Details:\n"
                    "    URL: %s\n"
                    "    Method: %s\n"
                    "    Headers: %s\n"
                    "    Body: %s",
                    response.request.url,
                    response.request.method,
                    response.request.headers,
                    response.request.body)
        import curlify
        logger.debug("Request as cURL: %s", curlify.to_curl(response.request))

        response.raise_for_status()
        return response.json()

# ==============================
# Decorator for error handling
# ==============================
def handle_oauth_errors(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"{func.__name__} failed: {e}")
            return {"error": str(e)}
    return wrapper

def lifetime_seconds_to_datetime(lifetime_seconds):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(lifetime_seconds))

def relative_seconds_to_lifetime_seconds(seconds):
    return int(time.time()) + int(seconds)

# ==============================
# Authorization Code + PKCE Client
# ==============================
class AuthorizationCodeClient(OAuth2Client):
    def __init__(self, client_id, client_secret, redirect_uri, auth_endpoint, token_endpoint, baseurl, token_file='tokens.json' ):
        super().__init__(client_id, client_secret, redirect_uri, auth_endpoint, token_endpoint, baseurl)
        self.code_verifier = None
        self.code_challenge = None
        self.token_file = token_file
        self.tokens = self._load_tokens() or {}

        # Check if token is expired and attempt refresh
        if self.tokens:
            # Log token expiry details
            # Check if they exist first
            if 'access_token_expires_at' in self.tokens:
                logger.debug(f"Access token expiry at {lifetime_seconds_to_datetime(self.tokens.get('access_token_expires_at', 0))}")
            else:
                logger.error("No access_token_expires_at found in tokens.")
            if 'refresh_token_expires_at' in self.tokens:
                logger.debug(f"Refresh token expiry at {lifetime_seconds_to_datetime(self.tokens.get('refresh_token_expires_at', 0))}")
            else:
                logger.error("No refresh_token_expires_at found in tokens.")

            # Check expiration
            if self._is_access_token_expired():
                # Assume refresh_token is present and valid
                refreshed = self.refresh_token()
                if refreshed:
                    logger.info("Token refresh successful.")
                else:
                    logger.warning("Automatic token refresh failed; user re-authorization required.")

            else:
                logger.info("Existing token is valid.")
            expires_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.tokens.get("access_token_expires_at", 0)))
            logger.info(f"Loaded existing token, valid until {expires_at}.")

    # --- PKCE helpers ---
    def _generate_code_verifier(self):
        verifier = base64.urlsafe_b64encode(os.urandom(64)).decode('utf-8').rstrip('=')
        logger.debug(f"Generated code_verifier (len={len(verifier)}) "+verifier)
        self.code_verifier = verifier
        return verifier

    def _generate_code_challenge(self, verifier):
        digest = hashlib.sha256(verifier.encode('utf-8')).digest()
        challenge = base64.urlsafe_b64encode(digest).decode('utf-8').rstrip('=')
        logger.debug("Generated code_challenge "+challenge)
        self.code_challenge = challenge
        return challenge

    # --- Token storage ---
    # Since expires_in is relative, we compute absolute expiry time when saving
    # and store that as access_token_expires_at (epoch seconds).
    # and remove expires_in from the stored data.
    # same for refresh_token_expires_in.
    def _save_tokens(self, token_data):
        """Save tokens to file, computing absolute expiry timestamp."""
        if 'expires_in' in token_data:
            logger.debug("Saving new access token...")
            logger.debug("Current time: "+str(int(time.time())))
            logger.debug("Relative expires_in: "+str(int(token_data['expires_in'])))
            logger.debug("Computed access_token_expires_at: "+str(int(time.time()) + int(token_data['expires_in'])))
            logger.debug("Access token expiry at "+lifetime_seconds_to_datetime(int(time.time()) + int(token_data['expires_in'])))
            token_data['access_token_expires_at'] = int(time.time()) + int(token_data['expires_in'])
            token_data.pop('expires_in', None)

        if 'refresh_token_expires_in' in token_data:
            logger.debug("Saving new refresh token...")
            logger.debug("Current time: "+str(int(time.time())))
            logger.debug("Relative refresh_token_expires_in: "+str(int(token_data['refresh_token_expires_in'])))
            logger.debug("Computed refresh_token_expires_in: "+str(int(time.time()) + int(token_data['refresh_token_expires_in'])))
            logger.debug("Refresh token expiry at "+lifetime_seconds_to_datetime(int(time.time()) + int(token_data['refresh_token_expires_in'])))
            token_data['refresh_token_expires_at'] = int(time.time()) + int(token_data['refresh_token_expires_in'])
            token_data.pop('refresh_token_expires_in', None)



        with open(self.token_file, 'w') as f:
            json.dump(token_data, f, indent=2)
        os.chmod(self.token_file, 0o600)
        logger.info(f"Tokens saved to {self.token_file}")
        self.tokens = token_data

    def _load_tokens(self):
        if not os.path.exists(self.token_file):
            logger.debug("No token file found.")
            return None
        try:
            with open(self.token_file, 'r') as f:
                data = json.load(f)
            logger.debug(f"Loaded tokens from {self.token_file}")
            return data
        except Exception as e:
            logger.error(f"Failed to load tokens: {e}")
            return None

    def _is_access_token_expired(self, skew=30):
        """Return True if the access token is expired (with a small time skew)."""
        exp = self.tokens.get('access_token_expires_at')
        if not exp:
            logger.error("No access_token_expires_at in token; treating as expired.")
            return True
        expired = (time.time() + skew) >= exp
        logger.debug(f"Access token expiry check: now={time.time()}, expires_at={exp}, expired={expired}")
        if expired:
            logger.warning("Access token is expired or about to expire.")
        else:
            logger.info("Access token is still valid.")
        return expired


    def _is_refresh_token_expired(self, skew=30):
        """Return True if the refresh  token is expired (with a small time skew)."""
        exp = self.tokens.get('refresh_token_expires_at')
        if not exp:
            logger.debug("No refresh_token_expires_at in token; treating as expired.")
            return True
        expired = (time.time() + skew) >= exp
        logger.debug(f"Refresh Token expiry check: now={time.time()}, expires_at={exp}, expired={expired}")
        if expired:
            logger.warning("Refresh token is expired or about to expire.")
        else:
            logger.info("Refresh token is still valid.")
        return expired


    # --- Authorization flow ---
    @handle_oauth_errors
    def get_authorization_url(self, **params):
        """Return an authorization URL for the user to visit."""
        code_verifier = self._generate_code_verifier()
        code_challenge = self._generate_code_challenge(code_verifier)
        params['response_type'] = 'code'
        params['code_challenge'] = code_challenge
        params['code_challenge_method'] = 'S256'
        url = self._get_auth_url(**params)
        logger.debug("Open this URL in a browser to authorize:")
        logger.debug(url)
        return url

    @handle_oauth_errors
    def get_token(self, code):
        """Exchange authorization code for tokens."""
        token_data = self._exchange_for_token(code, self.code_verifier)
        if token_data is None:
            logger.error("Token exchange failed; no token data received.")
            return None
        else:
            token_data['code_verifier'] = self.code_verifier
        self._save_tokens(token_data)
        return token_data

    # --- Refresh flow ---
    @handle_oauth_errors
    def refresh_token(self):
        """Refresh the access token using stored refresh token."""
        refresh_token = self.tokens.get('refresh_token')
        code_verifier = self.tokens.get('code_verifier')
        client_id = "c310e92ffc7c481190119ea98c507a2e"
        refresh_token_expiration = self.tokens.get('refresh_token_expires_at')

        if not refresh_token:
            logger.warning("No refresh token available.")
            return None

        if self._is_refresh_token_expired():
            logger.warning("Refresh token is expired; cannot refresh access token.")
            return None

        logger.debug("Attempting token refresh...")
        response = requests.post(self.token_endpoint, data={
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'code_verifier': code_verifier
        })
        logger.debug(f"Refresh token endpoint status: {response.status_code}")


        logger.debug("Request Details:\n"
                    "    URL: %s\n"
                    "    Method: %s\n"
                    "    Headers: %s\n"
                    "    Body: %s",
                    response.request.url,
                    response.request.method,
                    response.request.headers,
                    response.request.body)
        import curlify
        logger.debug("Request as cURL: %s", curlify.to_curl(response.request))


        if response.status_code != 200:
            logger.error(f"Token refresh failed ({response.status_code})")
            logger.debug(f"Failed response: {response.text}")
            return None

        new_tokens = response.json()
        if 'refresh_token' not in new_tokens:
            # Some providers return only new access_token
            new_tokens['refresh_token'] = refresh_token
            return None

        if 'refresh_token' in new_tokens:
            new_tokens['refresexpires_at'] = int(time.time()) + int(new_tokens.get('refresh_token_expires_in', 3600))
            logging.debug("Refresh token used for new access token.")
            logging.debug("f{new_tokens}")
            logging.debug("Refresh token expiry updated.")
            logging.debug(f"New access token expires at {lifetime_seconds_to_datetime(new_tokens['expires_at'])})")

            self._save_tokens(new_tokens)
            return new_tokens

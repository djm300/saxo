import base64
import hashlib
import json
import logging
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import httpx

# ==============================
# Logging setup
# ==============================
logger = logging.getLogger()
_http2_client = httpx.Client(http2=True)


@contextmanager
def token_file_lock(token_file):
    """Serialize token mutations across CLI processes."""
    if not isinstance(token_file, (str, os.PathLike)):
        yield
        return
    token_path = Path(os.path.abspath(os.path.expanduser(token_file)))
    lock_path = token_path.with_name(token_path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+b") as lock_handle:
        if os.name == "nt":
            import msvcrt

            lock_handle.seek(0)
            lock_handle.write(b"0")
            lock_handle.flush()
            while True:
                try:
                    lock_handle.seek(0)
                    msvcrt.locking(lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.1)
            try:
                yield
            finally:
                lock_handle.seek(0)
                msvcrt.locking(lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


# ==============================
# Base OAuth2 Client
# ==============================
class OAuth2Client:
    def __init__(self, client_id, redirect_uri, auth_endpoint, token_endpoint, baseurl):
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self.auth_endpoint = auth_endpoint
        self.token_endpoint = token_endpoint
        self.baseurl = baseurl

    def _get_auth_url(self, **params):
        """Build authorization URL with provided parameters."""
        default_params = {"client_id": self.client_id, "redirect_uri": self.redirect_uri}
        default_params.update(params)
        url = self.auth_endpoint + "?" + "&".join(f"{k}={v}" for k, v in default_params.items())
        logger.debug(f"Built authorization URL: {url}")
        return url

    def _exchange_for_token(self, code, code_verifier):
        """Exchange the authorization code for an access token."""
        logger.debug("Exchanging authorization code for token...")
        response = _http2_client.post(
            self.token_endpoint,
            data={
                "client_id": self.client_id,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
                "code_verifier": code_verifier,
            },
        )
        logger.debug(f"Token endpoint status: {response.status_code}")

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
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(lifetime_seconds))


# ==============================
# Authorization Code + PKCE Client
# ==============================
class AuthorizationCodeClient(OAuth2Client):
    def __init__(
        self,
        client_id,
        redirect_uri,
        auth_endpoint,
        token_endpoint,
        baseurl,
        token_file="tokens.json",
    ):
        super().__init__(client_id, redirect_uri, auth_endpoint, token_endpoint, baseurl)
        self.code_verifier = None
        self.code_challenge = None
        self.token_file = token_file
        self._cleanup_stale_token_temps()
        self.tokens = self._load_tokens() or {}

        # Check if token is expired and attempt refresh
        if self.tokens:
            # Log token expiry details
            # Check if they exist first
            if "access_token_expires_at" in self.tokens:
                logger.debug(
                    f"Access token expiry at {lifetime_seconds_to_datetime(self.tokens.get('access_token_expires_at', 0))}"
                )
            else:
                logger.error("No access_token_expires_at found in tokens.")
            if "refresh_token_expires_at" in self.tokens:
                logger.debug(
                    f"Refresh token expiry at {lifetime_seconds_to_datetime(self.tokens.get('refresh_token_expires_at', 0))}"
                )
            else:
                logger.error("No refresh_token_expires_at found in tokens.")

    # --- PKCE helpers ---
    def _generate_code_verifier(self):
        verifier = base64.urlsafe_b64encode(os.urandom(64)).decode("utf-8").rstrip("=")
        logger.debug("Generated PKCE code verifier.")
        self.code_verifier = verifier
        return verifier

    def _generate_code_challenge(self, verifier):
        digest = hashlib.sha256(verifier.encode("utf-8")).digest()
        challenge = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
        logger.debug("Generated code_challenge " + challenge)
        self.code_challenge = challenge
        return challenge

    # --- Token storage ---
    def _cleanup_stale_token_temps(self, max_age_seconds=3600):
        """Remove abandoned atomic-write files left by interrupted processes."""
        token_path = Path(os.path.abspath(os.path.expanduser(self.token_file)))
        directory = token_path.parent
        cutoff = time.time() - max_age_seconds
        for temporary_path in directory.glob(".saxo-token-*"):
            try:
                if temporary_path.is_file() and temporary_path.stat().st_mtime < cutoff:
                    temporary_path.unlink()
            except OSError:
                logger.debug("Could not remove stale token temporary file: %s", temporary_path)

    # Since expires_in is relative, we compute absolute expiry time when saving
    # and store that as access_token_expires_at (epoch seconds).
    # and remove expires_in from the stored data.
    # same for refresh_token_expires_in.
    def _save_tokens(self, token_data):
        """Save tokens to file, computing absolute expiry timestamp."""
        if "expires_in" in token_data:
            logger.debug("Saving new access token...")
            logger.debug("Current time: " + str(int(time.time())))
            logger.debug("Relative expires_in: " + str(int(token_data["expires_in"])))
            logger.debug(
                "Computed access_token_expires_at: "
                + str(int(time.time()) + int(token_data["expires_in"]))
            )
            logger.debug(
                "Access token expiry at "
                + lifetime_seconds_to_datetime(int(time.time()) + int(token_data["expires_in"]))
            )
            token_data["access_token_expires_at"] = int(time.time()) + int(token_data["expires_in"])
            token_data.pop("expires_in", None)

        if "refresh_token_expires_in" in token_data:
            logger.debug("Saving new refresh token...")
            logger.debug("Current time: " + str(int(time.time())))
            logger.debug(
                "Relative refresh_token_expires_in: "
                + str(int(token_data["refresh_token_expires_in"]))
            )
            logger.debug(
                "Computed refresh_token_expires_in: "
                + str(int(time.time()) + int(token_data["refresh_token_expires_in"]))
            )
            logger.debug(
                "Refresh token expiry at "
                + lifetime_seconds_to_datetime(
                    int(time.time()) + int(token_data["refresh_token_expires_in"])
                )
            )
            token_data["refresh_token_expires_at"] = int(time.time()) + int(
                token_data["refresh_token_expires_in"]
            )
            token_data.pop("refresh_token_expires_in", None)

        token_path = os.path.abspath(os.path.expanduser(self.token_file))
        os.makedirs(os.path.dirname(token_path), mode=0o700, exist_ok=True)
        fd, temporary_path = tempfile.mkstemp(
            prefix=".saxo-token-", dir=os.path.dirname(token_path), text=True
        )
        descriptor = fd
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(token_data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            try:
                os.chmod(temporary_path, 0o600)
            except OSError:
                pass
            os.replace(temporary_path, token_path)
        finally:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            try:
                # Attempt removal directly. This remains reliable even when
                # os.path.exists is mocked or the atomic replace already ran.
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass
            except OSError:
                logger.debug("Could not remove temporary token file: %s", temporary_path)
        try:
            os.chmod(token_path, 0o600)
        except OSError:
            logger.debug("Could not apply POSIX token-file permissions on this platform.")
        logger.info("Tokens saved to the configured user credential store.")
        self.tokens = token_data

    def _load_tokens(self):
        token_path = os.path.abspath(os.path.expanduser(self.token_file))
        if not os.path.exists(token_path):
            logger.debug("No token file found.")
            return None
        try:
            with open(token_path) as f:
                data = json.load(f)
            logger.debug("Loaded tokens from the configured user credential store.")
            return data
        except Exception as e:
            logger.error(f"Failed to load tokens: {e}")
            return None

    def _is_access_token_expired(self, skew=600):
        """Return True if the access token is expired (with a small time skew)."""
        # 10 minutes = 600 seconds
        # min_validity = 10 * 60

        if not self.tokens:
            logger.debug("No tokens loaded; treating access token as expired.")
            return True

        exp = self.tokens.get("access_token_expires_at")
        if exp is None:
            logger.debug("No access_token_expires_at in token; treating as expired.")
            return True

        try:
            exp = float(exp)
        except (TypeError, ValueError):
            logger.warning("Invalid access_token_expires_at value; treating as expired.")
            return True

        if (exp - time.time()) < skew:
            logger.info("Access token is expiring soon or has expired; treating as expired.")
            return True
        else:
            logger.debug(f"Access token valid until {lifetime_seconds_to_datetime(exp)}")
            return False

    def _is_refresh_token_expired(self, skew=30):
        """Return True if the refresh  token is expired (with a small time skew)."""
        exp = self.tokens.get("refresh_token_expires_at")
        if not exp:
            logger.debug("No refresh_token_expires_at in token; treating as expired.")
            return True
        expired = (time.time() + skew) >= exp
        return expired

    # --- Authorization flow ---
    def get_authorization_url(self, **params):
        """Return an authorization URL for the user to visit."""
        if self.code_verifier is None:
            self.code_verifier = self._generate_code_verifier()
            self.code_challenge = self._generate_code_challenge(self.code_verifier)
        else:
            logger.debug("Reusing the existing PKCE challenge.")
        params["response_type"] = "code"
        params["code_challenge"] = self.code_challenge
        params["code_challenge_method"] = "S256"
        url = self._get_auth_url(**params)
        logger.debug("Open this URL in a browser to authorize:")
        logger.debug(url)
        return url

    def get_token(self, code):
        """Exchange authorization code for tokens."""
        token_data = self._exchange_for_token(code, self.code_verifier)
        if token_data is None:
            logger.error("Token exchange failed; no token data received.")
            return None
        else:
            token_data["code_verifier"] = self.code_verifier
        self._save_tokens(token_data)
        return token_data

    # --- Refresh flow ---
    # attempt to refresh the access token using the stored refresh token
    # if successful, save the new tokens
    def refresh_token(self):
        """Refresh the access token using stored refresh token."""
        refresh_token = self.tokens.get("refresh_token")
        code_verifier = self.tokens.get("code_verifier")

        if not refresh_token:
            logger.warning("No refresh token available.")
            return None

        if self._is_refresh_token_expired():
            logger.warning("Refresh token is expired; cannot refresh access token.")
            return None

        logger.debug("Attempting token refresh...")
        response = _http2_client.post(
            self.token_endpoint,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "code_verifier": code_verifier,
            },
        )
        logger.debug(f"Refresh token endpoint status: {response.status_code}")

        if response.status_code != 200 and response.status_code != 201:
            logger.error(f"Token refresh failed ({response.status_code})")
            logger.debug(f"Failed response: {response.text}")
            return None

        new_tokens = response.json()

        # Some providers return only a new access token and keep refresh token unchanged.
        if "refresh_token" not in new_tokens:
            logger.warning("No new refresh token received; retaining old refresh token.")
            new_tokens["refresh_token"] = refresh_token
            if self.tokens.get("refresh_token_expires_at") is not None:
                new_tokens["refresh_token_expires_at"] = self.tokens.get("refresh_token_expires_at")
        else:
            logger.info("Received new refresh token.")
            new_tokens["refresh_token_expires_at"] = int(time.time()) + int(
                new_tokens.get("refresh_token_expires_in", 3600)
            )
            new_tokens.pop("refresh_token_expires_in", None)
            logging.debug(
                f"New refresh token expires at {lifetime_seconds_to_datetime(new_tokens['refresh_token_expires_at'])}"
            )

        if code_verifier and "code_verifier" not in new_tokens:
            new_tokens["code_verifier"] = code_verifier

        self._save_tokens(new_tokens)
        return new_tokens

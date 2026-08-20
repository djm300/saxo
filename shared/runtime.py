import json
import logging
import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from shared.client import SaxoClient


@dataclass(frozen=True)
class SaxoRuntimeConfig:
    redirect_uri: str
    simulation_mode: bool
    auth_endpoint: str
    token_endpoint: str
    token_file: str
    client_id: str
    base_url: str
    token_refresh_interval_seconds: int = 300
    trading_enabled: bool = False


def load_config_value(key, default=None, json_config=None, logger=None):
    value = os.environ.get(key)
    if value is not None and value != "":
        if logger:
            logger.debug("Loaded %s=%s from environment variable.", key, value)
        return value

    if json_config and key in json_config:
        value = json_config[key]
        if logger:
            logger.debug("Loaded %s=%s from params.json.", key, value)
        return value

    if logger:
        logger.debug("Using default value %s=%s.", key, default)
    return default


def parse_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def default_token_file(environment="sim"):
    """Return the per-user token path for the current operating system.

    TOKEN_FILE remains an explicit override for deployments and tests.
    """
    suffix = "sim" if environment == "sim" else "live"
    if sys.platform.startswith("win"):
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        directory = root / "Saxo"
    elif sys.platform == "darwin":
        directory = Path.home() / "Library" / "Application Support" / "Saxo"
    else:
        directory = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "saxo"
    return str(directory / f"tokens-{suffix}.json")


def load_runtime_config(params_path="params.json", logger=None, environment=None):
    json_config = {}
    try:
        with open(params_path) as file:
            json_config = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    redirect_uri = load_config_value(
        "REDIRECT_URI",
        default="https://djm300.github.io/saxo/oauth-redirect.html",
        json_config=json_config,
        logger=logger,
    )
    simulation_mode = parse_bool(
        load_config_value("SIMULATION_MODE", default=True, json_config=json_config, logger=logger)
    )
    if environment is not None:
        simulation_mode = environment != "live"

    if simulation_mode:
        auth_endpoint = os.environ.get(
            "SAXO_AUTH_ENDPOINT", "https://sim.logonvalidation.net/authorize"
        )
        token_endpoint = os.environ.get(
            "SAXO_TOKEN_ENDPOINT", "https://sim.logonvalidation.net/token"
        )
        token_file = load_config_value(
            "TOKEN_FILE",
            default=default_token_file("sim"),
            json_config=json_config,
            logger=logger,
        )
        client_id = "89da08eeb25c428a9099f768cdb1696e"
        base_url = "https://gateway.saxobank.com/sim/openapi"
    else:
        auth_endpoint = os.environ.get(
            "SAXO_AUTH_ENDPOINT", "https://live.logonvalidation.net/authorize"
        )
        token_endpoint = os.environ.get(
            "SAXO_TOKEN_ENDPOINT", "https://live.logonvalidation.net/token"
        )
        token_file = load_config_value(
            "TOKEN_FILE",
            default=default_token_file("live"),
            json_config=json_config,
            logger=logger,
        )
        client_id = "28d17c462242447f94c4b0767c41a552"
        base_url = "https://gateway.saxobank.com/openapi"

    trading_enabled = parse_bool(
        load_config_value("TRADING_ENABLED", default=False, json_config=json_config, logger=logger)
    )
    refresh_interval = int(
        load_config_value(
            "TOKEN_REFRESH_INTERVAL_SECONDS",
            default=300,
            json_config=json_config,
            logger=logger,
        )
    )

    return SaxoRuntimeConfig(
        redirect_uri=redirect_uri,
        simulation_mode=simulation_mode,
        auth_endpoint=auth_endpoint,
        token_endpoint=token_endpoint,
        token_file=token_file,
        client_id=client_id,
        base_url=base_url,
        token_refresh_interval_seconds=refresh_interval,
        trading_enabled=trading_enabled,
    )


def create_client(config):
    client = SaxoClient(
        client_id=config.client_id,
        redirect_uri=config.redirect_uri,
        auth_endpoint=config.auth_endpoint,
        token_endpoint=config.token_endpoint,
        token_file=config.token_file,
        baseurl=config.base_url,
    )
    client.trading_enabled = config.trading_enabled
    return client


def ensure_authenticated(client):
    if client._is_authenticated():
        return

    logging.info("No valid token available at startup.")
    tokens = getattr(getattr(client, "auth_client", None), "tokens", {}) or {}
    if tokens.get("refresh_token"):
        logging.info("Attempting refresh-token login before interactive auth.")
        refreshed = client.refresh_token()
        if refreshed and client._is_authenticated():
            logging.info("Refresh-token login successful.")
            return
        logging.warning("Refresh-token login failed; falling back to interactive auth if possible.")

    if sys.stdin.isatty() and not parse_bool(os.environ.get("SAXO_NONINTERACTIVE", False)):
        if not client.authenticate_interactive():
            raise RuntimeError("Interactive authentication failed.")
        return

    auth_url = client.get_authorization_url()
    raise RuntimeError(
        "Authentication required but no interactive terminal is available. "
        f"Authorize via: {auth_url}"
    )


class AuthenticationSession:
    """Own the authentication lifecycle for one CLI process.

    Short-lived commands use the session as a one-shot boundary. ``serve``
    additionally starts the client's refresh worker and stops it on shutdown.
    The web layer never owns this lifecycle.
    """

    def __init__(self, client, refresh_interval_seconds=300):
        self.client = client
        self.refresh_interval_seconds = refresh_interval_seconds
        self._refresh_thread = None
        self._stop_event = None

    def authenticate(self):
        ensure_authenticated(self.client)
        return self.client

    def start_refresh(self):
        if self._refresh_thread and self._refresh_thread.is_alive():
            return
        logging.info("Starting token refresh worker.")
        self._stop_event = threading.Event()
        self._refresh_thread = threading.Thread(
            target=self._refresh_loop,
            name="saxo-token-refresh",
            daemon=True,
        )
        self._refresh_thread.start()

    def _refresh_loop(self):
        while not self._stop_event.wait(self.refresh_interval_seconds):
            try:
                self.client.ensure_access_token()
            except Exception as exc:
                logging.error("Background token refresh failed: %s", exc)
                break

    def close(self):
        if self._refresh_thread and self._refresh_thread.is_alive():
            logging.info("Stopping token refresh worker.")
            self._stop_event.set()
            self._refresh_thread.join()
        self._refresh_thread = None

        # A shutdown refresh is a check, not an unconditional token rotation.
        # If the token became stale while the command was running, persist the
        # replacement before the process exits.
        try:
            self.client.ensure_access_token()
        except Exception as exc:
            logging.warning("Could not refresh the token during CLI shutdown: %s", exc)

    def __enter__(self):
        return self.authenticate()

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

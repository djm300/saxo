import json
import logging
import os
import sys
from dataclasses import dataclass

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


def load_runtime_config(params_path="params.json", logger=None):
    json_config = {}
    try:
        with open(params_path, "r") as file:
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

    if simulation_mode:
        auth_endpoint = os.environ.get("SAXO_AUTH_ENDPOINT", "https://sim.logonvalidation.net/authorize")
        token_endpoint = os.environ.get("SAXO_TOKEN_ENDPOINT", "https://sim.logonvalidation.net/token")
        token_file = load_config_value(
            "TOKEN_FILE",
            default="tokens.json",
            json_config=json_config,
            logger=logger,
        )
        client_id = "89da08eeb25c428a9099f768cdb1696e"
        base_url = "https://gateway.saxobank.com/sim/openapi"
    else:
        auth_endpoint = os.environ.get("SAXO_AUTH_ENDPOINT", "https://live.logonvalidation.net/authorize")
        token_endpoint = os.environ.get("SAXO_TOKEN_ENDPOINT", "https://live.logonvalidation.net/token")
        token_file = load_config_value(
            "TOKEN_FILE",
            default="tokens.json",
            json_config=json_config,
            logger=logger,
        )
        client_id = "28d17c462242447f94c4b0767c41a552"
        base_url = "https://gateway.saxobank.com/openapi"

    return SaxoRuntimeConfig(
        redirect_uri=redirect_uri,
        simulation_mode=simulation_mode,
        auth_endpoint=auth_endpoint,
        token_endpoint=token_endpoint,
        token_file=token_file,
        client_id=client_id,
        base_url=base_url,
    )


def create_client(config):
    return SaxoClient(
        client_id=config.client_id,
        redirect_uri=config.redirect_uri,
        auth_endpoint=config.auth_endpoint,
        token_endpoint=config.token_endpoint,
        token_file=config.token_file,
        baseurl=config.base_url,
    )


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

    if sys.stdin.isatty():
        if not client.authenticate_interactive():
            raise RuntimeError("Interactive authentication failed.")
        return

    auth_url = client.get_authorization_url()
    raise RuntimeError(
        "Authentication required but no interactive terminal is available. "
        f"Authorize via: {auth_url}"
    )

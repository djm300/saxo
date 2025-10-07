# Saxo Trading App - Development Plan

This document outlines the plan for building the Saxo trading application using Flask and threading, incorporating existing configuration and token management logic.

## Objective
Create a Python Flask application that manages Saxo access/refresh tokens in one thread and sends a scheduled order in another thread.

## Proposed Architecture
```
saxo_trading_app/
├── app.py              # Main Flask app
├── token_manager.py    # Token management logic
├── order_scheduler.py  # Order scheduling logic
├── config.py           # Config for API keys, schedule
└── requirements.txt    # Flask, requests, etc.
```

## Detailed Plan

1.  **Create Project Directory:** Create a new directory `saxo_trading_app`.
2.  **`config.py`:**
    *   Reuse `load_config_value` and `load_config` functions from `saxo.py` to handle loading configuration from environment variables and `params.json`.
    *   Define constants for `AUTH_ENDPOINT`, `TOKEN_ENDPOINT`, `CLIENT_ID`, `REDIRECT_URI`, and `SIMULATION_MODE` based on the loaded configuration and simulation mode, similar to `saxo.py`.
    *   Define `TOKEN_FILE` (e.g., `saxo_tokens_sim.json` or `saxo_tokens_live.json`) based on `SIMULATION_MODE`.
    *   Add new configuration parameters specific to the Flask app and order scheduling, such as:
        *   `ORDER_SCHEDULE_TIME`: The time at which the order should be placed (e.g., "HH:MM").
        *   `ORDER_DETAILS`: A dictionary containing instrument details, quantity, order type, etc.
        *   `TOKEN_REFRESH_INTERVAL_SECONDS`: How often the token refresh thread should run.
3.  **`requirements.txt`:**
    *   List initial dependencies: `Flask`, `requests`.
4.  **`token_manager.py`:**
    *   Implemented a `TokenManager` class as a wrapper for `saxo_sdk.client.SaxoClient`.
    *   This class now initializes and holds a single instance of `SaxoClient`.
    *   Delegates all token loading, saving, refreshing, and expiration checks to the `SaxoClient`'s internal `auth_client`.
    *   Provides `get_authorization_url()` to retrieve the URL for initiating the OAuth flow.
    *   Offers `exchange_code_for_tokens(code)` which correctly delegates to `self.saxo_client.get_token(code)` to process the authorization code received from the redirect.
    *   The `authenticate()` method is non-blocking and guides external applications on how to handle user interaction (e.g., presenting an input box or redirecting).
    *   The background token refresh thread continues to operate, leveraging the `SaxoClient`'s refresh capabilities.
5.  **`order_scheduler.py`:**
    *   Implemented an `OrderScheduler` class.
    *   Its `__init__` method now accepts an already initialized `SaxoClient` instance (expected to be managed by `TokenManager`).
    *   The `_place_order` method uses this shared `SaxoClient` instance to place orders, eliminating the creation of a separate `SaxoClient` and ensuring consistent token state.
    *   It will run in a separate thread and wait until the `ORDER_SCHEDULE_TIME` from `config.py` to send the order.
6.  **`app.py`:**
    *   Initialize the Flask application.
    *   Instantiate `TokenManager` and `OrderScheduler`, passing necessary configurations.
    *   Start the token refresh thread from `TokenManager`.
    *   Start the order scheduling thread from `OrderScheduler`.
    *   (Optional) Implement basic Flask routes for health checks or status monitoring.
    *   Ensure proper shutdown of threads when the Flask app stops.
7.  **Testing:**
    *   Set up a testing environment.
    *   Test token refresh functionality.
    *   Test order placement (initially with a simulated order or in a demo environment).

# saxo
Python tools for Saxo Bank OpenAPI access.

## Layout

- `cli/` - command-line portfolio, orders, and follow/TUI commands
- `web/` - Flask app for auth and portfolio views
- `shared/` - auth, client, config, formatter, and account lookup helpers

## Configuration

Configuration is loaded from environment variables first, then `params.json`, then defaults.

Common values:

- `REDIRECT_URI`
- `SIMULATION_MODE`
- `TOKEN_FILE`

In `params.json`, orders can be configured under `ORDERS`, with each order using `ORDER_SCHEDULE_TIME` and the API payload fields needed by Saxo.

## CLI

Run the CLI entry point with:

```bash
python -m cli portfolio --format text
python -m cli orders --format json
python -m cli follow ASML
```

Useful flags:

- `--params PATH` to read a different config file
- `--verbose` to enable informational logs

## Web app

Start the Flask app with:

```bash
python -m web
```

It exposes routes for:

- `/status`
- `/authenticate`
- `/portfolio`
- `/positions`
- `/positionstable`

## Notes

- Tokens default to `tokens.json`.
- `SIMULATION_MODE=true` uses Saxo SIM endpoints.
- `SIMULATION_MODE=false` uses Saxo LIVE endpoints.

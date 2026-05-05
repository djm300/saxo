# saxo
Python tools for Saxo Bank OpenAPI access.

## Layout

- `cli/` - command-line positions command
- `web/` - Flask app for auth and position views
- `shared/` - auth, client, config, formatter, and account lookup helpers
- `pyproject.toml` - packaging metadata and console scripts

## Configuration

Configuration is loaded from environment variables first, then `params.json`, then defaults.

Common values:

- `REDIRECT_URI`
- `SIMULATION_MODE`
- `TOKEN_FILE`

The OAuth redirect page is published from GitHub Pages at:

`https://djm300.github.io/saxo/oauth-redirect.html`

The Pages workflow publishes only `docs/oauth-redirect.html`, so that file is
the source for the published redirect URL.

## Install

Editable install for local work:

```bash
pip install -e ".[cli]"
```

That provides:

- `saxo-cli` for the command-line utility
- `saxo-web` for the Flask app

## CLI

Run the CLI entry point with:

```bash
saxo-cli positions --format text
```

Useful flags:

- `--params PATH` to read a different config file
- `--verbose` to enable informational logs

## Test coverage

Run the suite with line coverage reporting via the standard library:

```bash
python3 scripts/coverage.py
```

Pass extra pytest arguments after the script name:

```bash
python3 scripts/coverage.py tests/test_client.py -k token
```

Coverage summaries are written to `.coverage-trace/`.

## Web app

Start the Flask app with:

```bash
saxo-web
```

It exposes routes for:

- `/status`
- `/authenticate`
- `/positions`
- `/positionstable`

Container example:

```bash
docker build -t saxo-tools .
docker run --rm -p 5000:5000 \
  -v "$PWD/params.json:/app/params.json:ro" \
  -v "$PWD/tokens.json:/app/tokens.json" \
  saxo-tools
```

The app binds to `0.0.0.0:5000` by default inside the container. Override with
`PORT`, `SAXO_HOST`, or `FLASK_DEBUG` if needed.

## Notes

- Tokens default to `tokens.json`.
- `SIMULATION_MODE=true` uses Saxo SIM endpoints.
- `SIMULATION_MODE=false` uses Saxo LIVE endpoints.
- Saxo OpenAPI access in this app is read-only; API helpers reject non-GET requests.
- Keep `params.json` and `tokens.json` out of the image; mount them at runtime instead.

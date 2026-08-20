# saxo
Python tools for Saxo Bank OpenAPI access.

## Layout

- `cli/` - command-line positions command
- `web/` - Flask app for auth and position views
- `shared/` - authentication, client, runtime configuration, normalization, and formatting helpers
- `scripts/` - local linting, coverage, and standalone-binary build helpers
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
saxo-cli positions --json
```

Useful flags:

- `--params PATH` to read a different config file
- `--verbose` to enable informational logs

The CLI is read-only and JSON-first. It includes `account`, `balances`, `portfolio`,
`positions`, `position`, `orders`, `instrument`, and `quote`. `--env sim|live`
selects the explicitly requested Saxo environment; no order execution command is
provided. Saxo option-chain endpoints vary by account permissions and are kept out
of the initial normalized layer until a representative API response is available.

See [docs/CLI.md](docs/CLI.md) for colored command examples, JSON output, exit
codes, and platform-specific credential storage locations.

See [architecture.md](architecture.md) for the component boundaries and request flow.

## Standalone binary

Build a single-file CLI executable locally:

```bash
python -m pip install -e ".[build]"
python scripts/build_binary.py --clean
```

The output is `dist/saxo-cli.exe` on Windows and `dist/saxo-cli` on Linux/macOS. The
binary includes the Python runtime and application dependencies, but deliberately
does not embed `params.json`, OAuth credentials, or tokens. It uses the same
external configuration and per-user credential locations as the Python CLI.

Example:

```console
dist\saxo-cli.exe --env sim positions --json
```

The installed console script is always invoked as:

```console
saxo-cli quote ASR --json
```

For a checkout without installing the package, use the repository launcher
(`saxo-cli.cmd` on Windows or `./saxo-cli` on Unix). If the installed package or
binary directory is on `PATH`, the same command works from any directory.

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

## Local linting

Linting is local and does not require GitHub Actions:

```bash
python -m pip install -e ".[dev]"
python scripts/lint.py
python scripts/lint.py --fix
```

Ruff settings live in `pyproject.toml`. The wrapper also works on Windows with
`python scripts\lint.py`.

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
  -v saxo-config:/root/.config/saxo \
  saxo-tools
```

The app binds to `0.0.0.0:5000` by default inside the container. Override with
`PORT`, `SAXO_HOST`, or `FLASK_DEBUG` if needed.

## Notes

- Tokens default to a per-user OS credential location; see [docs/CLI.md](docs/CLI.md).
- `SIMULATION_MODE=true` uses Saxo SIM endpoints.
- `SIMULATION_MODE=false` uses Saxo LIVE endpoints.
- Saxo OpenAPI access in this app is read-only; API helpers reject non-GET requests.
- Keep credentials out of `params.json`, the image, and source control.

# saxo
Python tools for Saxo Bank OpenAPI access.

## Layout

- `cli/` - command-line positions command
- `web/` - Flask app for position views
- `shared/` - authentication, client, runtime configuration, normalization, and formatting helpers
- `scripts/` - local linting, coverage, and standalone-binary build helpers
- `pyproject.toml` - packaging metadata and console scripts

## Configuration

Configuration is loaded from environment variables first, then `params.json`, then defaults.

Common values:

- `REDIRECT_URI`
- `SIMULATION_MODE`
- `TOKEN_FILE`
- `TRADING_ENABLED`
- `SAXO_WEB_SECRET`
- `SAXO_INSTRUMENT_CACHE`

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
- `saxo-cli serve` for the Flask app

## CLI

Run the CLI entry point with:

```bash
saxo-cli positions --json
```

Useful flags:

- `--params PATH` to read a different config file
- `--verbose` to enable informational logs

The CLI is JSON-first. It includes `account`, `balances`, `portfolio`,
`positions`, `position`, `orders`, `order-history`, `instrument`, `quote`, and
explicit order preview/execution commands. `--env sim|live` selects the Saxo
environment. Actual writes require both `--execute` and `TRADING_ENABLED=true`.

### Luna portfolio autopilot

The repository-scoped `$saxo-investment-bot` skill runs an autonomous, manually
invoked portfolio review in Saxo SIM. Discovery is open-ended: there is no fixed
symbol universe or cap on holdings, research candidates, watchlist entries,
regions, sectors, or sequential research batches. Deterministic validation still
enforces long-only cash equities/ETFs, a 10% position ceiling, 15% cash floor,
five-order limit, and 20% per-run/40% rolling-seven-day turnover ceilings.

A dedicated alternative-signals scout uses current public web evidence—such as
insider and activist filings, government awards, clinical/regulatory events,
short interest and positioning, physical-economy data, hiring/product activity,
and attention anomalies—to surface less-obvious company-specific candidates.
Signals require primary-source confirmation, publication-lag tracking, an exact
issuer mapping, and a plausible economic mechanism. Broad beta can still win,
but only after this differentiated discovery gate is documented.

```console
python scripts/run_investment_bot.py
```

The launcher selects a Luna-compatible Codex binary, verifies login, pins the
parent and configured researchers to `gpt-5.6-luna` with medium reasoning, and
enables execution only for the child process. It prints timestamped prompts,
activity, progress, and conclusions to the terminal and mirrors sanitized lines
to `investbot.log`. The agent executor refuses live
endpoints regardless of general CLI configuration. Generated run artifacts stay
local under `agent/runs/` and are never committed automatically. A timestamped,
one-line conclusion for every completed, blocked, or failed review is appended to
the local `investbot.log`; duplicate run entries and sensitive-looking content are
rejected.

Useful lower-level commands:

```console
saxo-cli --env sim chart SPY --horizon 1440 --count 120 --json
saxo-cli --env sim agent snapshot --json
saxo-cli --env sim agent performance --json
saxo-cli --env sim agent validate agent/runs/RUN_ID/plan.json --json
saxo-cli --env sim agent execute agent/runs/RUN_ID/plan.json --execute --json
```

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

## Simulation smoke test

Run the CLI smoke test against simulation. It requires a valid simulation token;
if one is not available, it starts the normal interactive CLI login flow:

```bash
python scripts/smoke_test.py
```

The script forces `SIMULATION_MODE=True`, passes `--env sim` to every command,
and treats any authentication-required response as a failure. It never falls
back to live authentication. The smoke test intentionally runs the Python CLI
source (`python -m cli`), not the compiled executable. The `serve` command is
not included because a successful server command is intentionally long-running.

To perform a real simulation write test, explicitly opt in:

```bash
python scripts/smoke_test.py --execute-orders
```

This places one deliberately low-priced ASR limit order in the simulation account
and immediately cancels it. The flag forces `TRADING_ENABLED=True` only in the
smoke-test subprocess; live mode is never permitted.

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

Start the Flask app through the CLI:

```bash
saxo-cli serve
```

The CLI authenticates first using the normal terminal token prompt and passes
the authenticated client to the web app. The dashboard shows positions, working
orders, today's order history, and token lifetimes. It supports an explicit token
refresh action and, when trading is enabled, €1,000 market buys and sell-all
market orders. It has no login flow of its own. Normal mode prints a URL
protected by a generated `?secret=...` value;
`SAXO_WEB_SECRET` supplies a stable value. `saxo-cli serve --dev` disables this
check and enables hot reload for trusted local development.

It exposes routes for:

- `/status`
- `/positions`
- `/positionstable`
- `/api/positions`
- `/api/orders`
- `/api/order-history`
- `/api/status`
- `/api/auth/refresh` (POST)
- `/api/positions/buy` (POST)
- `/api/positions/sell` (POST)
- `/api/orders/cancel` (POST)

The dashboard is a single-column view. Position and order rows display the
instrument's true company name (truncated to 20 characters, with the ticker in
the tooltip). Buy orders use the whole-share floor of `1000 / current_price` and
are submitted as market orders. All order mutations remain disabled unless
`TRADING_ENABLED=true`.

Position instrument names are cached for five days in `instrument-cache.json`
beside the configured token file. The file is shared safely by concurrent web
server/reloader processes and keeps SIM/LIVE entries separate. Set
`SAXO_INSTRUMENT_CACHE` to choose another path.

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
- Trading mutations require `TRADING_ENABLED=true` and an explicit execution action.
- Keep credentials out of `params.json`, the image, and source control.

# Saxo CLI guide

The CLI is designed for shell scripts and AI agents. Data commands emit JSON by
default when stdout is piped, and every response identifies the Saxo environment.
Read commands are safe by default. Order commands remain previews unless both
execution is explicitly requested and trading is enabled.

## Quick start

<span style="color:#2563eb"><strong>Blue</strong></span> commands are safe read
operations. <span style="color:#16a34a"><strong>Green</strong></span> values are
examples and should be replaced with your own symbol or date.

<pre><span style="color:#2563eb">saxo-cli auth status
saxo-cli --env sim positions --json
saxo-cli portfolio --json</span></pre>

If authentication is needed, run `saxo-cli auth login` from an interactive
terminal. Normal read commands do not prompt when stdout is non-interactive;
they return a structured error instead.

## Commands

Start the local web view with:

```console
saxo-cli serve
```

`serve` authenticates in the terminal using the same token prompt as the other
CLI commands, then starts the web server on `127.0.0.1:5000`. It prints a URL
containing a generated `?secret=...` value; clients must retain that query
parameter on dashboard API requests. Set `SAXO_WEB_SECRET` for a stable secret.
`saxo-cli serve --dev` disables the secret and enables Flask hot reload, so it
should only be used on a trusted local machine. Override the listener with
`--host` and `--port` when needed.

| Command | Purpose | Example |
|---|---|---|
| `account` | Account metadata without secrets | `saxo-cli account --json` |
| `balances` | Cash, equity, availability, and margin | `saxo-cli balances --json` |
| `positions` | All normalized holdings | `saxo-cli positions --json` |
| `position SYMBOL` | Holdings matching one symbol | `saxo-cli position ASR --json` |
| `portfolio` | Local concentration and asset-class summary | `saxo-cli portfolio --json` |
| `instrument QUERY` | Resolve symbols to UIC and asset type | `saxo-cli instrument ASR --asset-type Stock` |
| `quote SYMBOL` | Bid, ask, midpoint, last, and market state | `saxo-cli quote ASR --json` |
| `orders` | Read-only order information | `saxo-cli orders --json` |
| `order-history` | Today's order activities, newest first | `saxo-cli order-history --json` |

## Order previews and execution

Market and limit order commands are preview-only unless explicitly enabled:

```console
saxo-cli order place ASR --side buy --quantity 1 --type market --json
saxo-cli order place ASR --side buy --quantity 1 --type limit --limit 60 --json
saxo-cli order cancel 123456 --account-key ACCOUNT_KEY --json
```

These return `"will_execute": false` and make no write request. To deliberately
execute a write, set `TRADING_ENABLED=true` in the environment or configuration
and add `--execute`:

```console
TRADING_ENABLED=true saxo-cli order place ASR --side sell --quantity 1 \
  --type limit --limit 80 --execute --json
```

The write endpoints are Saxo Trade V2. The CLI does not execute orders during its
smoke test; it tests only the preview payloads.

Use `--env sim` or `--env live` explicitly when switching environments:

<pre><span style="color:#d97706">saxo-cli --env sim portfolio --json</span>
<span style="color:#dc2626">saxo-cli --env live quote ASR --json</span></pre>

The live example is colored red because it accesses the live environment, even
though the command itself is read-only.

## Example JSON

```json
{
  "environment": "sim",
  "timestamp": "2026-08-20T08:00:00+00:00",
  "positions": [
    {
      "symbol": "ASR",
      "asset_type": "Stock",
      "uic": 12345,
      "quantity": 600,
      "currency": "EUR",
      "market_price": 69.28,
      "market_value": 41568
    }
  ]
}
```

JSON can be consumed directly by `jq`:

<pre><span style="color:#2563eb">saxo-cli positions --json | jq '.positions[] | {symbol, market_value}'</span></pre>

## Authentication and credential storage

OAuth tokens are never printed in command output. Unless `TOKEN_FILE` is set,
tokens are stored in a per-user location, with separate files for simulation and
live environments:

| Operating system | Default location |
|---|---|
| Windows | `%APPDATA%\Saxo\tokens-sim.json` and `tokens-live.json` |
| macOS | `~/Library/Application Support/Saxo/tokens-sim.json` and `tokens-live.json` |
| Linux and other Unix | `$XDG_CONFIG_HOME/saxo/tokens-sim.json`, or `~/.config/saxo/` if unset |

Set `TOKEN_FILE` when a deployment needs a custom location. The CLI creates the
parent directory, uses restrictive file permissions where supported, and keeps
the credential path out of normal logs.

The web dashboard also keeps `instrument-cache.json` beside the token file.
Successful UIC-to-symbol resolutions remain valid for five days and are shared
across dashboard server processes, including the development reloader. SIM and
LIVE cache keys are isolated. Override its location with
`SAXO_INSTRUMENT_CACHE`; deleting the file safely forces instrument names to be
resolved again.

<pre><span style="color:#2563eb">saxo-cli auth status
saxo-cli auth login</span></pre>

### Authentication lifecycle

Each CLI invocation owns its authentication session. A normal command loads the
cached token, refreshes it only when expired or close to expiry, executes the
operation, performs a final refresh check, and exits. The final check is
conditional and does not rotate a still-valid token.

`saxo-cli serve` keeps the authenticated client alive for the lifetime of the
web server. It runs a background refresh check at the configured interval and
stops that worker, then performs the final refresh check, when the server exits.
The web interface never performs login or OAuth callbacks.

The refresh interval defaults to 300 seconds and can be configured with
`TOKEN_REFRESH_INTERVAL_SECONDS` in the environment or `params.json`.

Do not put access tokens, refresh tokens, passwords, or client secrets in
`params.json`, shell history, source control, or command-line arguments.

## Exit codes

`0` means success. JSON errors use the shape
`{"error":{"code":"...","message":"..."}}`. The CLI reserves distinct
codes for missing instruments, ambiguous instruments, authentication failures,
and generic errors.

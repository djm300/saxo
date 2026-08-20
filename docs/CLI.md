# Saxo CLI guide

The CLI is designed for shell scripts and AI agents. Data commands emit JSON by
default when stdout is piped, and every response identifies the Saxo environment.
It is read-only: this project does not expose an order-execution command.

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

<pre><span style="color:#2563eb">saxo-cli auth status
saxo-cli auth login</span></pre>

Do not put access tokens, refresh tokens, passwords, or client secrets in
`params.json`, shell history, source control, or command-line arguments.

## Exit codes

`0` means success. JSON errors use the shape
`{"error":{"code":"...","message":"..."}}`. The CLI reserves distinct
codes for missing instruments, ambiguous instruments, authentication failures,
and generic errors.

# Saxo tools architecture

The project is a small Python trading utility. The CLI and web app share
the same authentication, HTTP client, runtime configuration, and normalized data
logic.

```text
CLI (cli/) ───────────────┐
                          ├─> runtime configuration ─> SaxoClient ─> Saxo OpenAPI
Web app (web/) ───────────┘             │                 │
                                       ▼                 ▼
                              credential storage    raw Saxo responses
                                       │                 │
                                       └──────> domain normalization
                                                       │
                                                       ▼
                                             JSON / HTML presentation
```

## Components

### `cli/`

`cli/saxocli.py` defines the `saxo-cli` command-line interface. It parses
commands, creates a configured client, handles authentication errors, and emits
JSON suitable for shell scripts and agents. It contains no OAuth or HTTP details.

### `web/`

`web/app.py` provides the Flask dashboard for positions, working orders, today's
order history, token lifetime status, and explicit position-closing market
orders. `saxo-cli serve` authenticates and configures the shared `SaxoClient`,
then injects it into the web server. The web layer has no independent OAuth or
launch path. Requests require the generated/configured URL secret unless
`serve --dev` is used.

### `shared/runtime.py`

This is the single configuration boundary. It loads environment variables,
`params.json`, and safe defaults; selects simulation/live endpoints; chooses the
platform-specific token path; creates clients; and owns the process-level
authentication session.

### Authentication lifecycle

Authentication has one owner per CLI process: `AuthenticationSession` in
`shared/runtime.py`. It receives the configured `SaxoClient`, ensures that a
usable access token exists, and controls the lifetime of any periodic refresh
worker. `web/app.py` receives an already-authenticated client and has no token
or OAuth lifecycle of its own.

For a normal one-shot CLI command, the flow is:

```text
create client → load token file → refresh if expired/near expiry
→ execute command → final refresh check → process exits
```

The final refresh is conditional. It persists a replacement only if the token
became stale while the command was running; it does not rotate a valid token
unnecessarily.

For `saxo-cli serve`, the flow is:

```text
create client → authenticate → start refresh worker → serve HTTP
                                              ↓
                              stop worker → final refresh check → exit
```

The worker uses the same client refresh method as API requests. Refreshes are
serialized by a client-level lock, preventing a request and the background
worker from rotating tokens concurrently. If background refresh fails, the
worker stops and the next API request reports the authentication failure; the
web layer does not attempt interactive login.

### `shared/auth.py`

This module implements OAuth authorization-code plus PKCE, token refresh, expiry
checks, and secure local token persistence. Token files are written atomically and
are never included in command output or debug request dumps.

### `shared/client.py`

`SaxoClient` is the Saxo OpenAPI adapter. Endpoint methods cover accounts,
balances, positions, orders, order history, instrument lookup, quotes, and the
explicitly gated order mutations used by the CLI and dashboard. Raw Saxo field
names stop at this boundary.

### Instrument metadata cache

Position responses identify instruments primarily by UIC, so rendering a large
portfolio otherwise requires one instrument-details request per position.
`web/app.py` stores successful UIC resolutions in `instrument-cache.json` beside
the configured token file. Entries are keyed by Saxo base URL, asset type, and
UIC, and expire after five days. This separates SIM and LIVE values while
allowing concurrent `saxo-cli serve` workers and Flask's development reloader
processes to share the same cache.

Cache reads and writes use the cross-process file lock from `shared/auth.py`.
Writes use a temporary file plus atomic replacement so readers never observe a
partially written JSON document. Failed API resolutions are not persisted. Set
`SAXO_INSTRUMENT_CACHE` to override the default cache path.

### `shared/domain.py`

This is the normalized domain layer. It converts Saxo responses into stable
agent-facing names and performs local portfolio calculations such as weights,
asset-class totals, and option-roll economics. It is independent of Flask and
argument parsing.

### `docs/`

`docs/CLI.md` documents commands, examples, JSON output, environment selection,
and credential locations. `docs/oauth-redirect.html` is the OAuth redirect asset.

## Request flow

1. The CLI loads `SaxoRuntimeConfig` and creates an `AuthenticationSession`.
2. `create_client()` constructs `SaxoClient` with the selected environment and
   user credential path.
3. The session loads a cached token and refreshes it when necessary.
4. An operation calls the relevant `SaxoClient` endpoint method.
5. The caller passes the raw response to the domain normalizers.
6. Position presentation resolves instrument names through the shared metadata
   cache, calling Saxo only for absent or expired entries.
7. The CLI serializes normalized data as JSON, while the web app renders HTML.

## Deliberate boundaries

- There is no database, server-side job queue, MCP dependency, or autonomous
  trading loop.
- Order writes require both an explicit execution action and
  `TRADING_ENABLED=true`; previews remain non-mutating.
- `TOKEN_FILE` can override the default credential location for deployment, but
  the default is platform-specific and separates simulation from live tokens.
- `shared/config.py` was removed because it duplicated runtime configuration and
  was not used by the CLI or web app.

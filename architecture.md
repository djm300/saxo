# Saxo tools architecture

The project is a small, read-only Python application. The CLI and web app share
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

`web/app.py` provides the legacy Flask view for authentication and positions. It
uses the same runtime configuration and `SaxoClient` as the CLI. The web layer is
presentation-only; it does not contain a separate API client.
`python -m web` is the supported local entry point for starting it.

### `shared/runtime.py`

This is the single configuration boundary. It loads environment variables,
`params.json`, and safe defaults; selects simulation/live endpoints; chooses the
platform-specific token path; creates clients; and performs non-interactive
authentication checks.

### `shared/auth.py`

This module implements OAuth authorization-code plus PKCE, token refresh, expiry
checks, and secure local token persistence. Token files are written atomically and
are never included in command output or debug request dumps.

### `shared/client.py`

`SaxoClient` is the read-only Saxo OpenAPI adapter. Its request helper rejects all
non-GET methods. Endpoint methods cover accounts, balances, positions, orders,
instrument lookup, and quotes. Raw Saxo field names stop at this boundary.

### `shared/domain.py`

This is the normalized domain layer. It converts Saxo responses into stable
agent-facing names and performs local portfolio calculations such as weights,
asset-class totals, and option-roll economics. It is independent of Flask and
argument parsing.

### `docs/`

`docs/CLI.md` documents commands, examples, JSON output, environment selection,
and credential locations. `docs/oauth-redirect.html` is the OAuth redirect asset.

## Request flow

1. The CLI or web app loads `SaxoRuntimeConfig`.
2. `create_client()` constructs `SaxoClient` with the selected environment and
   user credential path.
3. The client loads a cached token or refreshes it when necessary.
4. A read operation calls one `SaxoClient` endpoint method.
5. The caller passes the raw response to the domain normalizers.
6. The CLI serializes normalized data as JSON, while the web app renders HTML.

## Deliberate boundaries

- There is no database, server-side job queue, MCP dependency, or autonomous
  trading loop.
- There is no write-capable client method or order execution command.
- `TOKEN_FILE` can override the default credential location for deployment, but
  the default is platform-specific and separates simulation from live tokens.
- `shared/config.py` was removed because it duplicated runtime configuration and
  was not used by the CLI or web app.

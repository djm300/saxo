#!/usr/bin/env bash
set -euo pipefail

# Authentication is handled by the CLI so authorization codes and PKCE
# verifiers are never copied into shell history or committed to this project.
exec saxo-cli auth login "$@"

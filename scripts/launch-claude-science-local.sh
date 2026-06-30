#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_CLI="$ROOT/_local/Claude Science.app/Contents/Resources/bin/claude-science"
DATA_DIR="${CLAUDE_SCIENCE_LOCAL_DATA_DIR:-$ROOT/_local/data}"
CONFIG_FILE="${CLAUDE_SCIENCE_LOCAL_CONFIG:-$ROOT/_local/config.toml}"
PORT="${CLAUDE_SCIENCE_LOCAL_PORT:-18765}"
SANDBOX_PORT="${CLAUDE_SCIENCE_LOCAL_SANDBOX_PORT:-18766}"
PROXY_BASE="${ANTHROPIC_BASE_URL:-http://127.0.0.1:18080}"

if [[ ! -x "$APP_CLI" ]]; then
  echo "Claude Science copy not found at: $APP_CLI" >&2
  echo "Copy /Applications/Claude Science.app into _local/ first." >&2
  exit 1
fi

mkdir -p "$DATA_DIR"

export ANTHROPIC_BASE_URL="$PROXY_BASE"
export ANTHROPIC_AUTH_TOKEN="${ANTHROPIC_AUTH_TOKEN:-local-mtplx}"
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"

exec "$APP_CLI" \
  serve \
  --data-dir "$DATA_DIR" \
  --config "$CONFIG_FILE" \
  --port "$PORT" \
  --sandbox-port "$SANDBOX_PORT" \
  --no-auto-update \
  "$@"

#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_CLI="$ROOT/_local/Claude Science.app/Contents/Resources/bin/claude-science"
DATA_DIR="${CLAUDE_SCIENCE_LOCAL_DATA_DIR:-$ROOT/_local/data}"
CONFIG_FILE="${CLAUDE_SCIENCE_LOCAL_CONFIG:-$ROOT/_local/config.toml}"

exec "$APP_CLI" url \
  --data-dir "$DATA_DIR" \
  --config "$CONFIG_FILE"

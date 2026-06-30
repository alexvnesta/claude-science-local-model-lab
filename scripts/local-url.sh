#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_CLI="$ROOT/_local/Claude Science.app/Contents/Resources/bin/claude-science"

exec "$APP_CLI" url \
  --data-dir "$ROOT/_local/data" \
  --config "$ROOT/_local/config.toml"


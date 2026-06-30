#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/lib.sh"
load_proxy_profile "$ROOT"

mkdir -p "$ROOT/_local"
PID_FILE="$ROOT/_local/proxy.pid"
LOG_FILE="$ROOT/_local/proxy.log"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Proxy already running with PID $(cat "$PID_FILE")"
  exit 0
fi

python3 "$ROOT/scripts/daemonize.py" \
  --cwd "$ROOT" \
  --pid-file "$PID_FILE" \
  --log-file "$LOG_FILE" \
  -- \
  "$ROOT/scripts/run-proxy.sh"

sleep 1
if ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Proxy failed to start. Log:" >&2
  tail -n 80 "$LOG_FILE" >&2 || true
  exit 1
fi

echo "Proxy started with PID $(cat "$PID_FILE")"
echo "Log: $LOG_FILE"
curl --fail --show-error --silent "http://${PROXY_HOST:-127.0.0.1}:${PROXY_PORT:-18080}/healthz"
printf '\n'

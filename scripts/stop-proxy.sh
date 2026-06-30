#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT/_local/proxy.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "No proxy pid file."
  exit 0
fi

PID="$(cat "$PID_FILE")"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "Stopped proxy PID $PID"
else
  echo "Proxy PID $PID was not running."
fi
rm -f "$PID_FILE"


#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${OPENROUTER_ENV_FILE:-}"
if [[ -n "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
fi

if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
  echo "Set OPENROUTER_API_KEY or OPENROUTER_ENV_FILE before running this smoke." >&2
  exit 1
fi

choose_openrouter_model() {
  OPENROUTER_API_KEY="$OPENROUTER_API_KEY" python3 - <<'PY'
import json
import os
import sys
import urllib.request

request = urllib.request.Request(
    "https://openrouter.ai/api/v1/models",
    headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
)
with urllib.request.urlopen(request, timeout=20) as response:
    payload = json.loads(response.read().decode("utf-8"))

ids = [
    str(item.get("id"))
    for item in payload.get("data", [])
    if isinstance(item, dict) and item.get("id")
]
preferred_terms = ("qwen", "llama", "mistral", "gemma", "deepseek")
free_ids = [model_id for model_id in ids if model_id.endswith(":free")]
preferred_free = [
    model_id
    for model_id in free_ids
    if any(term in model_id.lower() for term in preferred_terms)
]
if preferred_free:
    print(preferred_free[0])
elif free_ids:
    print(free_ids[0])
else:
    print("No :free OpenRouter models found; set OPENROUTER_MODEL explicitly.", file=sys.stderr)
    sys.exit(2)
PY
}

if [[ -z "${OPENROUTER_MODEL:-}" ]]; then
  OPENROUTER_MODEL="$(choose_openrouter_model)"
  export OPENROUTER_MODEL
fi

LOG_FILE="$ROOT/_local/openrouter-smoke-proxy.log"
RESPONSE_FILE="$ROOT/_local/openrouter-smoke-response.json"
mkdir -p "$ROOT/_local"

echo "OpenRouter smoke model: $OPENROUTER_MODEL"
echo "Proxy log: $LOG_FILE"

choose_port() {
  python3 - <<'PY'
import socket
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
}

PROXY_PID=""
PORT=""

start_proxy() {
  for _ in $(seq 1 8); do
    PORT="$(choose_port)"
    : >"$LOG_FILE"
    (
      cd "$ROOT"
      PROXY_PROFILE=profiles/openrouter.env.example \
      PROXY_HOST=127.0.0.1 \
      PROXY_PORT="$PORT" \
      PROXY_TOOL_MODE=drop \
      PROXY_STREAM_MODE=buffered \
      PROXY_REQUEST_TIMEOUT="${PROXY_REQUEST_TIMEOUT:-120}" \
      ./scripts/run-proxy.sh
    ) >"$LOG_FILE" 2>&1 &
    PROXY_PID=$!
    echo "trying proxy port: $PORT" >>"$LOG_FILE"

    for _ in $(seq 1 40); do
      if curl --silent --max-time 1 "http://127.0.0.1:$PORT/healthz" >/dev/null; then
        return 0
      fi
      if ! kill -0 "$PROXY_PID" >/dev/null 2>&1; then
        break
      fi
      sleep 0.25
    done

    kill "$PROXY_PID" >/dev/null 2>&1 || true
    wait "$PROXY_PID" >/dev/null 2>&1 || true
  done
  echo "Proxy did not start; last log follows." >&2
  sed -n '1,120p' "$LOG_FILE" >&2
  return 1
}

start_proxy

cleanup() {
  if [[ -n "${PROXY_PID:-}" ]]; then
    kill "$PROXY_PID" >/dev/null 2>&1 || true
    wait "$PROXY_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

curl --fail --silent --show-error --max-time "${SMOKE_TIMEOUT_SECONDS:-120}" \
  "http://127.0.0.1:$PORT/v1/messages" \
  -H 'content-type: application/json' \
  -H 'anthropic-version: 2023-06-01' \
  -d '{"model":"claude-opus-4-8","max_tokens":32,"temperature":0,"messages":[{"role":"user","content":"Reply with exactly: OPENROUTER_PROXY_OK"}]}' \
  >"$RESPONSE_FILE"

python3 - "$RESPONSE_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    payload = json.load(handle)

text = "".join(
    block.get("text", "")
    for block in payload.get("content", [])
    if isinstance(block, dict) and block.get("type") == "text"
)
if "OPENROUTER_PROXY_OK" not in text:
    print("OpenRouter smoke response did not contain marker.", file=sys.stderr)
    print(text[:500], file=sys.stderr)
    sys.exit(1)
print("OpenRouter smoke passed.")
PY

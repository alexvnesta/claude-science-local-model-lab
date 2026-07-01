#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/lib.sh"

ENV_FILE="${PROVIDER_ENV_FILE:-${OPENROUTER_ENV_FILE:-}}"
if [[ -n "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
fi

CALLER_UPSTREAM_OPENAI_BASE_URL_SET="${UPSTREAM_OPENAI_BASE_URL+x}"
CALLER_UPSTREAM_OPENAI_BASE_URL_VALUE="${UPSTREAM_OPENAI_BASE_URL-}"
CALLER_UPSTREAM_OPENAI_MODEL_SET="${UPSTREAM_OPENAI_MODEL+x}"
CALLER_UPSTREAM_OPENAI_MODEL_VALUE="${UPSTREAM_OPENAI_MODEL-}"
CALLER_UPSTREAM_API_KEY_SET="${UPSTREAM_API_KEY+x}"
CALLER_UPSTREAM_API_KEY_VALUE="${UPSTREAM_API_KEY-}"
CALLER_PROXY_PROVIDER_NAME_SET="${PROXY_PROVIDER_NAME+x}"
CALLER_PROXY_PROVIDER_NAME_VALUE="${PROXY_PROVIDER_NAME-}"
CALLER_PROXY_HOST_SET="${PROXY_HOST+x}"
CALLER_PROXY_HOST_VALUE="${PROXY_HOST-}"
CALLER_PROXY_PORT_SET="${PROXY_PORT+x}"
CALLER_PROXY_PORT_VALUE="${PROXY_PORT-}"

load_proxy_profile "$ROOT"

if [[ -n "$CALLER_UPSTREAM_OPENAI_BASE_URL_SET" ]]; then
  UPSTREAM_OPENAI_BASE_URL="$CALLER_UPSTREAM_OPENAI_BASE_URL_VALUE"
fi
if [[ -n "$CALLER_UPSTREAM_OPENAI_MODEL_SET" ]]; then
  UPSTREAM_OPENAI_MODEL="$CALLER_UPSTREAM_OPENAI_MODEL_VALUE"
fi
if [[ -n "$CALLER_UPSTREAM_API_KEY_SET" ]]; then
  UPSTREAM_API_KEY="$CALLER_UPSTREAM_API_KEY_VALUE"
fi
if [[ -n "$CALLER_PROXY_PROVIDER_NAME_SET" ]]; then
  PROXY_PROVIDER_NAME="$CALLER_PROXY_PROVIDER_NAME_VALUE"
fi
if [[ -n "$CALLER_PROXY_HOST_SET" ]]; then
  PROXY_HOST="$CALLER_PROXY_HOST_VALUE"
fi
if [[ -n "$CALLER_PROXY_PORT_SET" ]]; then
  PROXY_PORT="$CALLER_PROXY_PORT_VALUE"
fi

UPSTREAM_OPENAI_BASE_URL="${UPSTREAM_OPENAI_BASE_URL:-${MTPLX_OPENAI_BASE_URL:-http://127.0.0.1:8030/v1}}"
UPSTREAM_OPENAI_MODEL="${UPSTREAM_OPENAI_MODEL:-${MTPLX_OPENAI_MODEL:-mtplx-qwen36-27b-optimized-quality}}"
UPSTREAM_API_KEY="${UPSTREAM_API_KEY:-${MTPLX_API_KEY:-local-mtplx}}"
PROXY_PROVIDER_NAME="${PROXY_PROVIDER_NAME:-<auto>}"
PROXY_HOST="${PROXY_HOST:-127.0.0.1}"
PROXY_PORT="${PROXY_PORT:-18080}"
TIMEOUT="${DOCTOR_TIMEOUT_SECONDS:-5}"

ok() {
  printf 'ok: %s\n' "$*"
}

warn() {
  printf 'warn: %s\n' "$*" >&2
}

fail() {
  printf 'fail: %s\n' "$*" >&2
  exit 1
}

printf 'profile: %s\n' "${PROXY_PROFILE:-<none>}"
printf 'provider_name: %s\n' "$PROXY_PROVIDER_NAME"
printf 'upstream_base: %s\n' "$UPSTREAM_OPENAI_BASE_URL"
printf 'upstream_model: %s\n' "$UPSTREAM_OPENAI_MODEL"
if [[ -n "$UPSTREAM_API_KEY" ]]; then
  printf 'upstream_api_key: present (%s chars)\n' "${#UPSTREAM_API_KEY}"
else
  printf 'upstream_api_key: absent\n'
fi
printf 'proxy: http://%s:%s\n' "$PROXY_HOST" "$PROXY_PORT"

cd "$ROOT"

if git check-ignore -q _local/proxy.log; then
  ok "_local/ is ignored by git"
else
  fail "_local/ is not ignored by git"
fi

APP_CLI="$ROOT/_local/Claude Science.app/Contents/Resources/bin/claude-science"
if [[ -x "$APP_CLI" ]]; then
  ok "isolated Claude Science app copy exists"
else
  warn "isolated Claude Science app copy not found at _local/Claude Science.app"
fi

if curl --silent --show-error --max-time "$TIMEOUT" \
  -H "Authorization: Bearer $UPSTREAM_API_KEY" \
  "$UPSTREAM_OPENAI_BASE_URL/models" >/dev/null; then
  ok "upstream /models reachable"
else
  warn "upstream /models not reachable; start the provider or check the profile"
fi

if curl --silent --show-error --max-time "$TIMEOUT" \
  "http://$PROXY_HOST:$PROXY_PORT/healthz" >/dev/null; then
  ok "proxy /healthz reachable"
else
  warn "proxy /healthz not reachable; start the proxy for live app checks"
fi

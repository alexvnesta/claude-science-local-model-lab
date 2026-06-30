#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/lib.sh"
load_proxy_profile "$ROOT"

export MTPLX_OPENAI_BASE_URL="${MTPLX_OPENAI_BASE_URL:-http://127.0.0.1:8030/v1}"
export MTPLX_OPENAI_MODEL="${MTPLX_OPENAI_MODEL:-mtplx-qwen36-27b-optimized-quality}"
export PROXY_HOST="${PROXY_HOST:-127.0.0.1}"
export PROXY_PORT="${PROXY_PORT:-18080}"
export PROXY_REQUEST_TIMEOUT="${PROXY_REQUEST_TIMEOUT:-240}"
export PROXY_MAX_TOKENS_CAP="${PROXY_MAX_TOKENS_CAP:-4096}"
export PROXY_UPSTREAM_RETRIES="${PROXY_UPSTREAM_RETRIES:-2}"
export PROXY_UPSTREAM_RETRY_DELAY="${PROXY_UPSTREAM_RETRY_DELAY:-2}"
export PROXY_ADVERTISED_MODELS="${PROXY_ADVERTISED_MODELS:-claude-opus-4-8,$MTPLX_OPENAI_MODEL}"

exec python3 "$ROOT/proxy/anthropic_mtplx_proxy.py" \
  --host "$PROXY_HOST" \
  --port "$PROXY_PORT" \
  --upstream-base "$MTPLX_OPENAI_BASE_URL" \
  --upstream-model "$MTPLX_OPENAI_MODEL" \
  --timeout "$PROXY_REQUEST_TIMEOUT" \
  --max-tokens-cap "$PROXY_MAX_TOKENS_CAP" \
  --upstream-retries "$PROXY_UPSTREAM_RETRIES" \
  --upstream-retry-delay "$PROXY_UPSTREAM_RETRY_DELAY" \
  --advertised-models "$PROXY_ADVERTISED_MODELS"

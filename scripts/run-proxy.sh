#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/lib.sh"

capture_proxy_profile_overrides
load_proxy_profile "$ROOT"
restore_proxy_profile_overrides

export UPSTREAM_OPENAI_BASE_URL="${UPSTREAM_OPENAI_BASE_URL:-${MTPLX_OPENAI_BASE_URL:-http://127.0.0.1:8030/v1}}"
export UPSTREAM_OPENAI_MODEL="${UPSTREAM_OPENAI_MODEL:-${MTPLX_OPENAI_MODEL:-mtplx-qwen36-27b-optimized-quality}}"
export UPSTREAM_API_KEY="${UPSTREAM_API_KEY:-${MTPLX_API_KEY:-local-mtplx}}"
export PROXY_PROVIDER_NAME="${PROXY_PROVIDER_NAME:-}"
export MTPLX_OPENAI_BASE_URL="${MTPLX_OPENAI_BASE_URL:-$UPSTREAM_OPENAI_BASE_URL}"
export MTPLX_OPENAI_MODEL="${MTPLX_OPENAI_MODEL:-$UPSTREAM_OPENAI_MODEL}"
export MTPLX_API_KEY="${MTPLX_API_KEY:-$UPSTREAM_API_KEY}"
export PROXY_HOST="${PROXY_HOST:-127.0.0.1}"
export PROXY_PORT="${PROXY_PORT:-18080}"
export PROXY_REQUEST_TIMEOUT="${PROXY_REQUEST_TIMEOUT:-240}"
export PROXY_MAX_TOKENS_CAP="${PROXY_MAX_TOKENS_CAP:-4096}"
export PROXY_UPSTREAM_RETRIES="${PROXY_UPSTREAM_RETRIES:-2}"
export PROXY_UPSTREAM_RETRY_DELAY="${PROXY_UPSTREAM_RETRY_DELAY:-2}"
export PROXY_STREAM_MODE="${PROXY_STREAM_MODE:-direct}"
export PROXY_STREAM_HEARTBEAT_SECONDS="${PROXY_STREAM_HEARTBEAT_SECONDS:-0}"
export PROXY_TOOL_MODE="${PROXY_TOOL_MODE:-pass}"
export PROXY_TOOL_ALLOWLIST="${PROXY_TOOL_ALLOWLIST:-}"
export PROXY_TOOL_VALIDATION="${PROXY_TOOL_VALIDATION:-schema}"
export PROXY_SCHEMA_LOG_PATH="${PROXY_SCHEMA_LOG_PATH:-}"
export PROXY_HARNESS_TOOLS="${PROXY_HARNESS_TOOLS:-}"
export PROXY_CLAUDE_SCIENCE_COMPAT="${PROXY_CLAUDE_SCIENCE_COMPAT:-0}"
export PROXY_ADVERTISED_MODELS="${PROXY_ADVERTISED_MODELS:-$UPSTREAM_OPENAI_MODEL}"
export PROXY_MODEL_DISPLAY_NAMES="${PROXY_MODEL_DISPLAY_NAMES:-}"

exec python3 "$ROOT/proxy/anthropic_mtplx_proxy.py" \
  --host "$PROXY_HOST" \
  --port "$PROXY_PORT" \
  --upstream-base "$UPSTREAM_OPENAI_BASE_URL" \
  --upstream-model "$UPSTREAM_OPENAI_MODEL" \
  --provider-name "$PROXY_PROVIDER_NAME" \
  --timeout "$PROXY_REQUEST_TIMEOUT" \
  --max-tokens-cap "$PROXY_MAX_TOKENS_CAP" \
  --upstream-retries "$PROXY_UPSTREAM_RETRIES" \
  --upstream-retry-delay "$PROXY_UPSTREAM_RETRY_DELAY" \
  --stream-mode "$PROXY_STREAM_MODE" \
  --stream-heartbeat-seconds "$PROXY_STREAM_HEARTBEAT_SECONDS" \
  --tool-mode "$PROXY_TOOL_MODE" \
  --tool-allowlist "$PROXY_TOOL_ALLOWLIST" \
  --tool-validation "$PROXY_TOOL_VALIDATION" \
  --schema-log-path "$PROXY_SCHEMA_LOG_PATH" \
  --harness-tools "$PROXY_HARNESS_TOOLS" \
  --claude-science-compat "$PROXY_CLAUDE_SCIENCE_COMPAT" \
  --advertised-models "$PROXY_ADVERTISED_MODELS" \
  --model-display-names "$PROXY_MODEL_DISPLAY_NAMES"

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
export PROXY_STREAM_MODE="${PROXY_STREAM_MODE:-direct}"
export PROXY_TOOL_MODE="${PROXY_TOOL_MODE:-pass}"
export PROXY_TOOL_ALLOWLIST="${PROXY_TOOL_ALLOWLIST:-}"
export PROXY_TOOL_VALIDATION="${PROXY_TOOL_VALIDATION:-schema}"
export PROXY_TOOL_REPAIR="${PROXY_TOOL_REPAIR:-metadata}"
export PROXY_FORCE_MENTIONED_TOOL="${PROXY_FORCE_MENTIONED_TOOL:-0}"
export PROXY_PARSE_TEXT_TOOL_CALLS="${PROXY_PARSE_TEXT_TOOL_CALLS:-0}"
export PROXY_SCHEMA_LOG_PATH="${PROXY_SCHEMA_LOG_PATH:-}"
export PROXY_HARNESS_TOOLS="${PROXY_HARNESS_TOOLS:-submit_output}"
export PROXY_CLAUDE_SCIENCE_COMPAT="${PROXY_CLAUDE_SCIENCE_COMPAT:-0}"
export PROXY_ADVERTISED_MODELS="${PROXY_ADVERTISED_MODELS:-claude-opus-4-8,$MTPLX_OPENAI_MODEL}"
export PROXY_MODEL_DISPLAY_NAMES="${PROXY_MODEL_DISPLAY_NAMES:-}"

exec python3 "$ROOT/proxy/anthropic_mtplx_proxy.py" \
  --host "$PROXY_HOST" \
  --port "$PROXY_PORT" \
  --upstream-base "$MTPLX_OPENAI_BASE_URL" \
  --upstream-model "$MTPLX_OPENAI_MODEL" \
  --timeout "$PROXY_REQUEST_TIMEOUT" \
  --max-tokens-cap "$PROXY_MAX_TOKENS_CAP" \
  --upstream-retries "$PROXY_UPSTREAM_RETRIES" \
  --upstream-retry-delay "$PROXY_UPSTREAM_RETRY_DELAY" \
  --stream-mode "$PROXY_STREAM_MODE" \
  --tool-mode "$PROXY_TOOL_MODE" \
  --tool-allowlist "$PROXY_TOOL_ALLOWLIST" \
  --tool-validation "$PROXY_TOOL_VALIDATION" \
  --tool-repair "$PROXY_TOOL_REPAIR" \
  --force-mentioned-tool "$PROXY_FORCE_MENTIONED_TOOL" \
  --parse-text-tool-calls "$PROXY_PARSE_TEXT_TOOL_CALLS" \
  --schema-log-path "$PROXY_SCHEMA_LOG_PATH" \
  --harness-tools "$PROXY_HARNESS_TOOLS" \
  --claude-science-compat "$PROXY_CLAUDE_SCIENCE_COMPAT" \
  --advertised-models "$PROXY_ADVERTISED_MODELS" \
  --model-display-names "$PROXY_MODEL_DISPLAY_NAMES"

#!/usr/bin/env bash
set -euo pipefail

PROXY_BASE="${PROXY_BASE:-http://127.0.0.1:18080}"
MODEL="${ANTHROPIC_MODEL:-claude-opus-4-8}"

curl --fail --show-error --silent "$PROXY_BASE/healthz"
printf '\n'

curl --fail --show-error --silent \
  "$PROXY_BASE/v1/messages/count_tokens" \
  -H 'content-type: application/json' \
  -d '{"model":"'"$MODEL"'","messages":[{"role":"user","content":"Count this tiny test."}]}' \
  | python3 -m json.tool

curl --fail --show-error --silent --max-time "${SMOKE_TIMEOUT_SECONDS:-240}" \
  "$PROXY_BASE/v1/messages" \
  -H 'content-type: application/json' \
  -H 'anthropic-version: 2023-06-01' \
  -H 'authorization: Bearer local-mtplx' \
  -d '{"model":"'"$MODEL"'","max_tokens":24,"temperature":0,"messages":[{"role":"user","content":"Reply with exactly: mtplx proxy ok"}]}' \
  | python3 -m json.tool


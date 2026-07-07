#!/usr/bin/env bash
set -euo pipefail

lab_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd
}

load_proxy_profile() {
  local root="$1"
  if [[ -n "${PROXY_PROFILE:-}" ]]; then
    local profile="$PROXY_PROFILE"
    if [[ "$profile" != /* ]]; then
      profile="$root/$profile"
    fi
    if [[ ! -f "$profile" ]]; then
      echo "Proxy profile not found: $profile" >&2
      exit 1
    fi
    set -a
    # shellcheck disable=SC1090
    source "$profile"
    set +a
  fi
}

proxy_profile_override_vars() {
  cat <<'VARS'
UPSTREAM_OPENAI_BASE_URL
UPSTREAM_OPENAI_MODEL
UPSTREAM_API_KEY
PROXY_PROVIDER_NAME
PROXY_HOST
PROXY_PORT
PROXY_REQUEST_TIMEOUT
PROXY_MAX_TOKENS_CAP
PROXY_UPSTREAM_RETRIES
PROXY_UPSTREAM_RETRY_DELAY
PROXY_STREAM_MODE
PROXY_STREAM_HEARTBEAT_SECONDS
PROXY_TOOL_MODE
PROXY_TOOL_ALLOWLIST
PROXY_TOOL_VALIDATION
PROXY_SCHEMA_LOG_PATH
PROXY_HARNESS_TOOLS
PROXY_CLAUDE_SCIENCE_COMPAT
PROXY_ADVERTISED_MODELS
PROXY_MODEL_DISPLAY_NAMES
VARS
}

capture_proxy_profile_overrides() {
  local name
  for name in $(proxy_profile_override_vars); do
    eval "CALLER_${name}_SET=\"\${${name}+x}\""
    eval "CALLER_${name}_VALUE=\"\${${name}-}\""
  done
}

restore_proxy_profile_overrides() {
  local name set_var value_var
  for name in $(proxy_profile_override_vars); do
    set_var="CALLER_${name}_SET"
    value_var="CALLER_${name}_VALUE"
    if [[ -n "${!set_var:-}" ]]; then
      export "$name=${!value_var}"
    fi
  done
}

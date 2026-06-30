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


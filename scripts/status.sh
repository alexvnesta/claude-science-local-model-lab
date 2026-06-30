#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "== Official Claude Science :8765 =="
lsof -nP -iTCP:8765 -sTCP:LISTEN || true

echo
echo "== Local Claude Science :18765 =="
lsof -nP -iTCP:18765 -sTCP:LISTEN || true

echo
echo "== Proxy :18080 =="
if curl --fail --show-error --silent http://127.0.0.1:18080/healthz 2>/dev/null; then
  printf '\n'
else
  echo "Proxy not reachable."
fi

echo
echo "== MTPLX :8030 =="
if curl --fail --show-error --silent http://127.0.0.1:8030/v1/models 2>/dev/null; then
  printf '\n'
else
  echo "MTPLX not reachable."
fi


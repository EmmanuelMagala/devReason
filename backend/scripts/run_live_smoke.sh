#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-full}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${LIVE_SMOKE_ENV_FILE:-$ROOT_DIR/.env.live_smoke}"

if [[ ! -d "$ROOT_DIR/.venv" ]]; then
  echo "Missing virtualenv at $ROOT_DIR/.venv" >&2
  exit 1
fi

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

source "$ROOT_DIR/.venv/bin/activate"

export LIVE_SMOKE_BASE_URL="${LIVE_SMOKE_BASE_URL:-http://127.0.0.1:8000}"

case "$MODE" in
  public)
    exec pytest "$ROOT_DIR/tests/integration/test_live_smoke_routes.py" -k public -q
    ;;
  full)
    "$ROOT_DIR/scripts/validate_live_smoke_env.sh"

    exec pytest "$ROOT_DIR/tests/integration/test_live_smoke_routes.py" -q
    ;;
  *)
    echo "Usage: $0 [public|full]" >&2
    exit 1
    ;;
 esac

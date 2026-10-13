#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-full}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${LIVE_SMOKE_HOST:-127.0.0.1}"
PORT="${LIVE_SMOKE_PORT:-8000}"
STARTUP_TIMEOUT="${LIVE_SMOKE_STARTUP_TIMEOUT:-90}"
ENV_FILE="${LIVE_SMOKE_ENV_FILE:-$ROOT_DIR/.env.live_smoke}"
LOG_FILE="${LIVE_SMOKE_SERVER_LOG:-$ROOT_DIR/.live_smoke_server.log}"

if [[ ! -d "$ROOT_DIR/.venv" ]]; then
  echo "Missing virtualenv at $ROOT_DIR/.venv" >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required for readiness checks" >&2
  exit 1
fi

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

source "$ROOT_DIR/.venv/bin/activate"

export LIVE_SMOKE_BASE_URL="${LIVE_SMOKE_BASE_URL:-http://$HOST:$PORT}"

if [[ "$MODE" == "full" ]]; then
  "$ROOT_DIR/scripts/validate_live_smoke_env.sh"
fi

cleanup() {
  if [[ -n "${SERVER_PID:-}" ]] && kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

cd "$ROOT_DIR"
uvicorn src.main:app --host "$HOST" --port "$PORT" >"$LOG_FILE" 2>&1 &
SERVER_PID=$!

ready_url="$LIVE_SMOKE_BASE_URL/api/health"
for ((i=0; i<STARTUP_TIMEOUT; i++)); do
  if curl -fsS "$ready_url" >/dev/null 2>&1; then
    "$ROOT_DIR/scripts/run_live_smoke.sh" "$MODE"
    exit 0
  fi
  sleep 1
 done

echo "Backend did not become healthy within ${STARTUP_TIMEOUT}s" >&2
if [[ -f "$LOG_FILE" ]]; then
  echo >&2
  echo "Last server log output:" >&2
  tail -n 40 "$LOG_FILE" >&2 || true
fi
exit 1

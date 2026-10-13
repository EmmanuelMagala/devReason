#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${LIVE_SMOKE_ENV_FILE:-$ROOT_DIR/.env.live_smoke}"
BASE_URL="${LIVE_SMOKE_BASE_URL:-http://127.0.0.1:8000}"
VALIDATOR="$ROOT_DIR/scripts/validate_live_smoke_env.sh"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

BASE_URL="${LIVE_SMOKE_BASE_URL:-$BASE_URL}"

print_status() {
  local label="$1"
  local value="$2"
  printf '%-28s %s\n' "$label" "$value"
}

print_status "Project root" "$ROOT_DIR"
print_status "Live smoke env file" "$ENV_FILE"
print_status "Base URL" "$BASE_URL"

if [[ -f "$ENV_FILE" ]]; then
  print_status "Env file present" "yes"
else
  print_status "Env file present" "no"
fi

if command -v curl >/dev/null 2>&1; then
  if curl -fsS "$BASE_URL/api/health" >/dev/null 2>&1; then
    print_status "Backend reachable" "yes"
    if ready_body="$(curl -fsS "$BASE_URL/api/ready" 2>/dev/null)"; then
      print_status "Ready payload" "$ready_body"
    else
      print_status "Ready payload" "request failed"
    fi
  else
    print_status "Backend reachable" "no"
  fi
else
  print_status "Backend reachable" "curl unavailable"
fi

if [[ -x "$VALIDATOR" ]]; then
  if validation_output="$($VALIDATOR 2>&1)"; then
    print_status "Full smoke env" "valid"
    print_status "Validator output" "$validation_output"
  else
    print_status "Full smoke env" "invalid"
    printf '%s\n' "$validation_output"
  fi
else
  print_status "Full smoke env" "validator missing"
fi

cat <<'EOF'

Commands:
  ./scripts/run_live_smoke.sh public
  ./scripts/run_live_smoke.sh full
  ./scripts/run_backend_and_live_smoke.sh public
  ./scripts/run_backend_and_live_smoke.sh full
EOF

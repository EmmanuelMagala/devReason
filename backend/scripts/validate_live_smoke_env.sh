#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${LIVE_SMOKE_ENV_FILE:-$ROOT_DIR/.env.live_smoke}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

required_vars=(
  LIVE_SMOKE_CLERK_BEARER_TOKEN
  LIVE_SMOKE_CLERK_USER_ID
  LIVE_SMOKE_CLERK_EMAIL
  LIVE_SMOKE_CLERK_WEBHOOK_SECRET
  LIVE_SMOKE_GITHUB_OWNER
  LIVE_SMOKE_GITHUB_REPO
  LIVE_SMOKE_GITHUB_PAT
  LIVE_SMOKE_GITHUB_PR_URL
)

missing=()
for var_name in "${required_vars[@]}"; do
  if [[ -z "${!var_name:-}" ]]; then
    missing+=("$var_name")
  fi
done

if (( ${#missing[@]} > 0 )); then
  echo "Missing required live smoke variables:" >&2
  printf '  %s\n' "${missing[@]}" >&2
  exit 1
fi

errors=()

base_url="${LIVE_SMOKE_BASE_URL:-http://127.0.0.1:8000}"
if [[ ! "$base_url" =~ ^https?:// ]]; then
  errors+=("LIVE_SMOKE_BASE_URL must start with http:// or https://")
fi

if [[ ! "$LIVE_SMOKE_CLERK_BEARER_TOKEN" =~ ^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$ ]]; then
  errors+=("LIVE_SMOKE_CLERK_BEARER_TOKEN must look like a JWT")
fi

if [[ ! "$LIVE_SMOKE_CLERK_USER_ID" =~ ^user_ ]]; then
  errors+=("LIVE_SMOKE_CLERK_USER_ID should start with user_")
fi

if [[ ! "$LIVE_SMOKE_CLERK_EMAIL" =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]]; then
  errors+=("LIVE_SMOKE_CLERK_EMAIL must be a valid email address")
fi

if [[ ! "$LIVE_SMOKE_CLERK_WEBHOOK_SECRET" =~ ^whsec_ ]]; then
  errors+=("LIVE_SMOKE_CLERK_WEBHOOK_SECRET should start with whsec_")
fi

if [[ "$LIVE_SMOKE_GITHUB_OWNER" =~ [[:space:]] ]]; then
  errors+=("LIVE_SMOKE_GITHUB_OWNER must not contain spaces")
fi

if [[ "$LIVE_SMOKE_GITHUB_REPO" =~ [[:space:]] ]]; then
  errors+=("LIVE_SMOKE_GITHUB_REPO must not contain spaces")
fi

if [[ ! "$LIVE_SMOKE_GITHUB_PAT" =~ ^(ghp_|github_pat_) ]]; then
  errors+=("LIVE_SMOKE_GITHUB_PAT should start with ghp_ or github_pat_")
fi

expected_pr_prefix="https://github.com/${LIVE_SMOKE_GITHUB_OWNER}/${LIVE_SMOKE_GITHUB_REPO}/pull/"
if [[ "$LIVE_SMOKE_GITHUB_PR_URL" != ${expected_pr_prefix}* ]]; then
  errors+=("LIVE_SMOKE_GITHUB_PR_URL must match ${expected_pr_prefix}<number>")
fi

if (( ${#errors[@]} > 0 )); then
  echo "Invalid live smoke variable values:" >&2
  printf '  %s\n' "${errors[@]}" >&2
  exit 1
fi

echo "Live smoke environment looks valid."

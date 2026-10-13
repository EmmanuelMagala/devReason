# Live Smoke Testing

This backend includes a live smoke suite that exercises the public routes and, when you provide real credentials, the protected repo, webhook, chat, review, and SSE routes.

## Files

- `tests/integration/test_live_smoke_routes.py`: the live smoke test suite
- `.env.live_smoke.example`: template for live test inputs
- `scripts/live_smoke_status.sh`: reports whether the env file is present, whether the backend is reachable, and whether the full smoke env validates
- `scripts/validate_live_smoke_env.sh`: validates required live smoke variables before full-mode test runs
- `scripts/run_live_smoke.sh`: run smoke tests against an already-running backend
- `scripts/run_backend_and_live_smoke.sh`: start the backend, wait for readiness, run the smoke suite, then stop the server

## Prerequisites

- The backend virtualenv exists at `.venv`
- The backend app can start successfully with your `.env`
- For full mode, you have real live-service values for:
  - Clerk bearer token
  - Clerk user ID
  - Clerk email
  - Clerk webhook secret
  - GitHub owner
  - GitHub repo
  - GitHub PAT
  - GitHub PR URL

## Setup

1. Copy `.env.live_smoke.example` to `.env.live_smoke`
2. Fill in the values
3. Make sure your main backend `.env` is also configured for the app itself
4. Run `./scripts/live_smoke_status.sh` to confirm the backend is reachable and the full-mode env is valid

## How To Get Each Live Value

- `LIVE_SMOKE_CLERK_BEARER_TOKEN`: sign into your Clerk-backed app with the target test user, then extract the session JWT from the browser app. If Clerk is available on `window`, run `await Clerk.session.getToken()` in the devtools console.
- `LIVE_SMOKE_CLERK_USER_ID`: the Clerk user ID for that same account, usually visible in the Clerk dashboard or frontend session payload. It should look like `user_...`.
- `LIVE_SMOKE_CLERK_EMAIL`: the email address for that same Clerk user.
- `LIVE_SMOKE_CLERK_WEBHOOK_SECRET`: from the Clerk webhook configuration that points to your backend `POST /webhooks/clerk` endpoint.
- `LIVE_SMOKE_GITHUB_OWNER`: the owner segment of the GitHub repository URL you want to test.
- `LIVE_SMOKE_GITHUB_REPO`: the repository name segment of that GitHub URL.
- `LIVE_SMOKE_GITHUB_PAT`: a GitHub personal access token with enough scope to read the repo and PR. If you later want to test `post_to_github=true`, it also needs comment/review write permissions.
- `LIVE_SMOKE_GITHUB_PR_URL`: a real pull request URL in that same repository, for example `https://github.com/<owner>/<repo>/pull/123`.

## Commands

Run only the public smoke tests against an already-running backend:

```bash
./scripts/run_live_smoke.sh public
```

Run the full live smoke suite against an already-running backend:

```bash
./scripts/run_live_smoke.sh full
```

Start the backend, wait for readiness, run public smoke tests, and shut it down:

```bash
./scripts/run_backend_and_live_smoke.sh public
```

Start the backend, wait for readiness, run the full live smoke suite, and shut it down:

```bash
./scripts/run_backend_and_live_smoke.sh full
```

## Environment Variables

The runner reads `.env.live_smoke` by default. You can override it with:

```bash
LIVE_SMOKE_ENV_FILE=/path/to/custom.env ./scripts/run_live_smoke.sh full
```

You can validate the env file without running tests:

```bash
./scripts/validate_live_smoke_env.sh
```

You can also get a combined readiness report:

```bash
./scripts/live_smoke_status.sh
```

The combined runner also supports:

- `LIVE_SMOKE_HOST` default `127.0.0.1`
- `LIVE_SMOKE_PORT` default `8000`
- `LIVE_SMOKE_BASE_URL` default `http://127.0.0.1:8000`
- `LIVE_SMOKE_STARTUP_TIMEOUT` default `90`

## What gets tested

Public mode:

- `GET /`
- `GET /api/health`
- `GET /api/ready`

Full mode adds:

- `POST /webhooks/clerk`
- `GET /api/repos`
- `POST /api/repos`
- `POST /api/repos/{repo_id}/rules`
- `GET /api/repos/{repo_id}/rules`
- `POST /api/repos/{repo_id}/chat`
- `POST /api/reviews`
- `GET /api/reviews/{review_id}`
- `GET /api/reviews/{review_id}/stream`
- negative-path checks for auth, invalid webhook signature, invalid PR URL, and missing IDs

## Notes

- Full mode uses real external services. It is a smoke suite, not an isolated unit test run.
- Full mode fails fast if the env file is missing required values or the values do not match basic expected formats.
- The review stream route is tested with an SSE-capable client, not Swagger.
- The chat route is validated as a streaming text response.
- If the review graph completes with `failed`, the smoke suite still treats that as a valid terminal state for route-contract testing; you should inspect the review payload and logs to diagnose the underlying workflow failure.

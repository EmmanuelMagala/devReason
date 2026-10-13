# DevReason

FastAPI and React application for reviewing authorized GitHub repositories.

See the [user and technical manual](DEVREASON_MANUAL.md) for numbered user
procedures, architecture diagrams, the LangGraph workflow, and source traces.
The Markdown manual is the versioned source. Generated HTML and PDF copies
remain local.

## Windows development

Use Python 3.12 or newer, Node 22 or newer, and a running Docker Desktop.
After installing dependencies below, start all three processes from the root:

```powershell
.\start-dev.ps1
```

This runs the frontend on 5173, API on 8000, and a separate review worker in
hidden background processes. Use `.\stop-dev.ps1` to stop these processes.
Logs and process IDs are saved under `.audit/implementation/runtime`.
For a local demo, use `.\start-dev.ps1 -Preview`. This builds and serves the
compiled frontend. It avoids development module transforms and file watching.
Run `.\stop-dev.ps1` before changing modes. Preview is a local demo server;
use a proper static web server for a public deployment.
Use `-ApiPort 8002 -FrontendPort 5174` when the default ports are occupied;
the script aligns frontend/API URLs and CORS for those ports. Update the GitHub
App's registered callback and setup URLs to the same API port.

From the project root, start local Redis:

```powershell
docker compose -f compose.dev.yml -p devreason-dev up -d redis
```

Backend, in one terminal:

```powershell
cd backend
py -m venv .venv-win
.\.venv-win\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m alembic upgrade head
python -m src.run
```

Worker, in a separate backend terminal with the same environment activated:

```powershell
python -m src.worker
```

The worker must be running for `/api/ready` to pass and reviews to execute.

The existing `.venv` is a Linux environment; use `.venv-win` on Windows. If
activation is blocked, use `Set-ExecutionPolicy -Scope Process Bypass` or call
`.venv-win/Scripts/python.exe` directly. The API launcher selects a Windows
event loop compatible with Psycopg. Do not run multiple APIs on the same port.

Frontend, in another terminal:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Set `REDIS_URL=redis://127.0.0.1:6381/0` for dedicated local Redis. Use a valid
`postgresql+asyncpg://` database URL. Keep credentials in `backend/.env` and the
Clerk publishable key in `frontend/.env.local`; never commit either file.

## GitHub setup

Configure `GITHUB_APP_CLIENT_ID`, `GITHUB_APP_CLIENT_SECRET`,
`GITHUB_APP_ID`, `GITHUB_APP_SLUG`, `GITHUB_APP_PRIVATE_KEY_PATH`, and
`GITHUB_APP_WEBHOOK_SECRET` on the backend. In the GitHub App registration:

- OAuth callback: `http://localhost:8000/api/auth/github/callback` (also set
  `GITHUB_OAUTH_CALLBACK_URL` to this exact URL).
- Installation setup URL: `http://localhost:8000/api/auth/github/setup`.
- Enable redirect on update; request contents read, metadata read and PR write.
- Leave **Request user authorization (OAuth) during installation** unchecked.
  DevReason authorizes the account first, then verifies installation access.
  GitHub hides the Setup URL when that option is checked.
- Webhook: the externally reachable `/webhooks/github` URL. Use an HTTPS tunnel
  when developing locally, with the same configured webhook signing secret.

Set `FRONTEND_BASE_URL` to the actual frontend origin, including the port.
Development consent and repository access are distinct from Clerk sign-in.
Previously imported repositories must be verified through the new connection
flow. Personal access tokens are not accepted for new repository connections.

If granting repository access leaves the browser on GitHub, check the App's
**Post installation → Setup URL** and **Redirect on update** settings. These
settings are on GitHub; changing backend environment variables alone does not
update them. **Connect**, **Grant repository access**, and **Manage access** open
GitHub in a new tab. DevReason keeps its current page, filters, and form state.
Buttons immediately show **Opening GitHub…** and prevent repeat clicks. A blocked
tab or failed launch shows an error and allows another attempt.

Verified callbacks return to `/github/return` in the new tab. That page completes
the user-bound OAuth handoff, if needed, and sends a flow-specific notification
to the original tab. It sends no OAuth code, ticket, or access token between tabs.
The original tab fetches signed-in connection status, synchronizes verified
repository access, and refreshes metadata. It then acknowledges the callback so
the callback tab can close. Navigation intent persists through an original-tab
reload. BroadcastChannel messages and optional localStorage fallback results
are bound to a random flow ID and can only request an access recheck.

If GitHub stays open after saving the existing selection, close that tab or
switch back to DevReason. Tab closure, focus, and visibility events also trigger
an access refresh. DevReason cannot observe a Save click inside GitHub; an update
appears after its callback or when you return. Returning alone never proves that
GitHub granted access. Installation updates can still recover one-use server
state from an HttpOnly cookie when GitHub omits URL state. Only allowlisted
frontend origins receive callback redirects. Legacy same-tab return URLs remain
supported for links already in progress.
[GitHub setup URL documentation](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/about-the-setup-url).

## Checks

```powershell
cd backend
python -m pytest tests/unit -q
```

Use `docker compose -f compose.dev.yml -p devreason-dev --profile test up -d`
for an isolated pgvector test database on port 55439. Its local-only test URL is
`postgresql+asyncpg://devreason:local-test-only@127.0.0.1:55439/devreason_test`.
Never point destructive test fixtures at a live database.

From `backend`, run the full local regression gate against that database:

```powershell
$env:DATABASE_URL="postgresql+asyncpg://devreason:local-test-only@127.0.0.1:55439/devreason_test"
python -m alembic upgrade head
python -m pytest tests/unit tests/regression -q
Remove-Item Env:DATABASE_URL
```

Frontend validation:

```powershell
cd frontend
npm.cmd run build
npm.cmd run lint -- --max-warnings 0
npm.cmd run test:browser
```

Browser tests use an isolated compiled fixture build on 5190, saved in
`.audit/implementation/e2e-dist`. The Clerk substitution is
limited to `vite.e2e.config.ts`; production builds always use real Clerk. Tests
never publish to GitHub or call a paid model. Real tabs exercise callbacks and
closure. Focus events are simulated because headless Chrome does not emit native
tab-focus events in this environment. Chrome must be installed, or adjust
the Playwright browser channel and install Playwright's Chromium.

Live smoke checks use `LIVE_SMOKE_BASE_URL` and a valid
`LIVE_SMOKE_CLERK_BEARER_TOKEN` supplied privately through your environment.
Set `LIVE_SMOKE_GITHUB_PR_URL` to an authorized test PR and explicitly enable
`LIVE_SMOKE_RUN_ANALYSIS=true` to run a paid analysis. Posting remains disabled.

## Review scope and rollout

`DURABLE_REVIEWS_ENABLED` controls review submission. `BRANCH_REVIEWS_ENABLED`
defaults to false; `start-dev.ps1` enables it for local acceptance. New reviews
are tied to an immutable commit. Defaults are 50 eligible files and 100,000
source characters; change `REVIEW_MAX_FILES` and `REVIEW_MAX_CHARACTERS` to adjust
them. Coverage records omitted files and exact character ranges. Continue
remaining content or choose another file batch at the same commit. Each batch
has its own saved report; incomplete coverage always remains visible.

Supported resolved-version formats: npm package-lock/shrinkwrap, pinned Python
requirements, Poetry lock, Cargo lock, and Go modules. Companion declarations
use their selected lockfile. Yarn/pnpm and declarations without a supported
lockfile are explicitly reported as incomplete dependency coverage.

Snapshot results can be reused for one hour when commit, model, rules, and scope
match. Revoke repository access through GitHub to invalidate future operations.
Existing results remain in review history; historical coverage is unknown.
GitHub posting requires a separate explicit action, with preview and safe retry.
Legacy PR requests with `post_to_github=true` still explicitly opt into posting.

Before release, configure the GitHub OAuth/webhook secrets, complete a signed-in
live connection, and run the designated live PR/snapshot checks. Local fixtures
do not prove real organization policy or GitHub OAuth registration.

Internal audit reports, implementation records, and generated manual exports
are excluded from Git. Keep the README, Markdown manual, diagrams, and test
instructions in the repository.

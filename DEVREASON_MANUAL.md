# DevReason user and technical manual

**Code and evidence date:** 13 October 2026. **Audience:** users, developers, and operators.

**Other formats:** Local generated HTML and PDF copies. The Markdown manual and diagram sources are included in the repository.

DevReason reviews code from GitHub repositories that you can access. It saves findings, reports, conversations, and architecture rules.

The **frontend** is the React application in your browser. React builds the user interface. The **backend** is the FastAPI server. FastAPI is the Python framework for API routes.

A separate **worker** performs saved review jobs. A **job** is a saved instruction to perform work. A **database** stores application records. PostgreSQL is the main database. Redis stores short-lived connection state, progress events, and cached service data.

A **repository** is a GitHub project that contains files and their change history. A **pull request**, or **PR**, proposes changes for a merge. A **branch** names a line of development. A **commit** identifies one saved version of the files.

A **finding** is a possible code issue. A **scope** specifies the files or file parts for a review. **Coverage** records the content that the application actually read. A finding is not proof of a defect. Check it against the code.

## How to use this manual

1. Read Section 1 for the main user journey.
2. Read Section 2 for each feature and its internal operation.
3. Read Sections 3 and 4 for the system and agent workflow.
4. Read Section 5 for an example with recorded live results.
5. Use Sections 6 and 7 for fault diagnosis and limits.

The manual uses short sentences, active voice, consistent terms, and numbered procedures. These choices follow [ASD-STE100 principles](https://www.asd-ste100.org/STE_faq.html). This document does not claim a formal dictionary compliance check.

**Evidence terms:**

| Term | Meaning in this manual |
| --- | --- |
| Implemented | The current source contains the behavior. |
| Fixture tested | A test used controlled service data or a test account substitute. |
| Live verified | The implementation record reports a check with real services or the user confirmed the result. |
| Unverified | The code exists, but the stated real-service behavior lacks recorded acceptance evidence. |
| Illustrative | An example explains the flow. It does not describe an extra test run. |

Local implementation and audit records contain run-specific validation evidence. These records are excluded from Git. Use the source links and test suites in this manual to inspect the implementation. Historical live-test results below describe the recorded runs on the evidence date.

## Contents

- [1. User journey](#1-user-journey)
- [2. Feature walkthroughs](#2-feature-walkthroughs)
- [3. System architecture](#3-system-architecture)
- [4. LangGraph execution](#4-langgraph-execution)
- [5. Worked example](#5-worked-example)
- [6. Troubleshooting and local operation](#6-troubleshooting-and-local-operation)
- [7. Known limitations and verification](#7-known-limitations-and-verification)
- [Appendix A. API reference](#appendix-a-api-reference)
- [Appendix B. Source map](#appendix-b-source-map)

## 1. User journey

### 1.1 Start the application and create an account

For the recorded local setup, open **http://localhost:5173**. The API documentation is at **http://localhost:8000/docs**. Section 6 gives the local start commands.

1. Open DevReason.
2. Select the sign-up link if you do not have an account.
3. Complete the steps on the Clerk sign-up screen.
4. Sign in if you already have an account.
5. Wait for the Overview page.

**Clerk** manages the sign-up and sign-in screens. The enabled sign-in methods depend on the Clerk configuration. DevReason does not implement its own password form.

Signing in identifies your DevReason account. The GitHub connection in the next procedure gives the application access to repositories.

Behind the scenes, `ProtectedRoute` waits for Clerk to load. It sends an unsigned user to `/sign-in`. It includes the requested path and query in `redirect_url`. Clerk controls the final sign-in behavior. The sign-in and sign-up components also set `/` as their default destination.

The frontend obtains a **token**, which is a credential that proves the current session. It adds the token to protected API requests. The backend verifies the token before it accesses your records.

**Source trace:** [App.tsx](frontend/src/App.tsx) → [ProtectedRoute.tsx](frontend/src/components/layout/ProtectedRoute.tsx) → [SignInPage.tsx](frontend/src/pages/SignInPage.tsx) / [SignUpPage.tsx](frontend/src/pages/SignUpPage.tsx) → [API client](frontend/src/api/client.ts) → [Clerk verification](backend/src/core/clerk.py).

### 1.2 Use the navigation

The main navigation has four destinations.

| Destination | Use |
| --- | --- |
| Overview | Start from a repository, paste a PR URL, or open a recent review. |
| Repositories | Find a repository and open its workspace. |
| Reviews | Find and open saved review results. |
| Settings | Connect GitHub accounts and manage repository access. |

On a small screen, select **Open navigation**. On a repository page, use the **Pull requests**, **Branches**, **Reviews**, **Chat**, and **Rules** tabs.

A breadcrumb shows the path to the current page. The address contains the repository or review identifier. The current workflow does not require a global repository selection.

**Source trace:** [router.tsx](frontend/src/router.tsx), [AppShell.tsx](frontend/src/components/layout/AppShell.tsx), [Sidebar.tsx](frontend/src/components/layout/Sidebar.tsx), [RepositoryPage.tsx](frontend/src/pages/RepositoryPage.tsx).

### 1.3 Connect GitHub

1. Open **Settings**.
2. Select **Connect GitHub account**.
3. Select the correct account on GitHub.
4. Authorize the DevReason GitHub App.
5. Wait for GitHub to return you to DevReason.
6. Check the account status.
7. Select **Grant repository access** if the App cannot access the required repositories.
8. Select the account or organization on GitHub.
9. Select the repositories and save the installation settings.
10. Wait for the return to your original DevReason page.

An **installation** is the GitHub App permission set for an account or organization. DevReason checks both your account access and the installation access. You do not enter an installation identifier in the normal workflow.

If the App already has an accessible installation, DevReason imports its repositories after authorization. You do not need another installation for each review.

If your organization requires approval, request access on GitHub. An administrator must approve the request. DevReason shows an approval notice. It cannot override the organization policy.

The connection can return to a repository page with its filters. The App registration must contain the correct callback and setup URLs. See Procedure 6.3 if GitHub does not return.

**Source trace:** [IntegrationsPage.tsx](frontend/src/pages/IntegrationsPage.tsx) → [workspace API](frontend/src/api/workspace.ts) → [GitHub routes](backend/src/api/routes/github_app.py) → [GitHub connection service](backend/src/services/github_connection_service.py). Return handling uses [githubReturn.ts](frontend/src/lib/githubReturn.ts) and [useGitHubConnection.ts](frontend/src/hooks/useGitHubConnection.ts).

### 1.4 Find a repository

1. Open **Repositories**.
2. Enter a repository or owner name in **Search repositories**.
3. Select an account or organization if you need to narrow the list.
4. Use **Next** or **Previous** to change the page.
5. Select the repository card.

The normal page contains up to 20 repositories. A card shows the owner, name, and available metadata. Metadata can include a description, language, and private status.

Search covers the repository name, owner, and full `owner/name` value. DevReason delays a search request by 250 milliseconds. This delay reduces requests while you type.

If a repository is missing, select **Missing a repository? Grant access**. Check the GitHub account and the App installation. Clear the search and account filters before you diagnose access.

The browser shows a load error if the request fails. A load error does not mean that your account has no repositories.

**Source trace:** [RepositoriesPage.tsx](frontend/src/pages/RepositoriesPage.tsx) → [useDebounce.ts](frontend/src/hooks/useDebounce.ts) → `GET /api/repos/browse` in [discovery.py](backend/src/api/routes/discovery.py).

### 1.5 Review a pull request

1. Open the repository workspace.
2. Select **Pull requests**.
3. Select **Open**, **Closed**, or **All** in the PR state control.
4. Use the page controls if necessary.
5. Select **Review** on the required PR row.
6. Wait for the saved review page to open.
7. Check the status and coverage when the review finishes.

The PR text filter checks only the loaded page. It is not a search across all GitHub PRs. The list shows 20 PRs per page. A draft label does not prevent submission.

The API resolves the PR to a commit before it creates the job. The worker checks that the PR head still matches that commit. A changed PR can require a new review.

The normal submission sets GitHub posting to false. Starting a review does not publish the result.

**URL shortcut:**

1. Open **Overview**.
2. Paste an HTTPS GitHub PR URL into **Already have a PR link?**
3. Select **Review pull request**.

DevReason finds the matching authorized repository. It accepts supported PR subpages, such as `/files`, and the backend stores a canonical PR URL. A URL does not bypass repository authorization.

**Source trace:** [RepositoryPage.tsx](frontend/src/pages/RepositoryPage.tsx) / [OverviewPage.tsx](frontend/src/pages/OverviewPage.tsx) → [reviews API](frontend/src/api/reviews.ts) → `submit_review` in [reviews.py](backend/src/api/routes/reviews.py) → [URL parser](backend/src/core/urls.py).

### 1.6 Review a branch

A **snapshot review** checks selected files from one commit. It does not need a PR. Branch reviews must be enabled by the operator.

1. Open the repository workspace.
2. Select **Branches**.
3. Select the required branch.
4. Check the commit identifier and the eligible file count.
5. Check the file and character limits.
6. Clear file checkboxes that you do not want to include.
7. Use **Next batch** or **Previous batch** if necessary.
8. Select **Review selected scope**.
9. Check the saved coverage after the review finishes.

Use **Load more branches** if the required branch is not in the current list. The API returns up to 100 branches per page.

The default scope selects up to 50 files. The default file-content limit is 100,000 characters. File content can reach the character limit before the application reads all selected files.

The preview lists eligible paths. It does not promise that every selected file will fit. The saved coverage gives the actual result.

DevReason excludes known generated and vendor paths. It reads source files and known dependency manifests. A **manifest** describes dependencies. A **lockfile** records resolved dependency versions.

A selected commit stays fixed for the run. **Review latest commit** and **Review remaining content** have different purposes. The first starts a new review of the current target. The second continues the saved snapshot scope at its original commit.

**Source trace:** [RepositoryPage.tsx](frontend/src/pages/RepositoryPage.tsx) → `scope` in [discovery.py](backend/src/api/routes/discovery.py) → [source_service.py](backend/src/services/source_service.py) → [ReviewCreate](backend/src/schemas/review.py).

### 1.7 Wait, leave, reconnect, or cancel

1. Read the review status.
2. Expand **Review progress** if you need the phase details.
3. Leave the page if you need to do other work.
4. Open **Reviews** later and select the saved review.
5. Select **Cancel review** if you want to stop a pending or active job.

A browser refresh does not delete a review. The worker owns the job. The browser receives progress and checks the saved status every five seconds while the review is pending or running.

If the event connection fails, the page shows a reconnect state. It continues to check saved status. Cancellation requests reach the worker through the database. A pending job can stop immediately. An active job stops when the worker observes the request.

**Source trace:** [ReviewPage.tsx](frontend/src/pages/ReviewPage.tsx), [useReviews.ts](frontend/src/hooks/useReviews.ts), [useLiveReview.ts](frontend/src/hooks/useLiveReview.ts), [review routes](backend/src/api/routes/reviews.py), [jobs.py](backend/src/services/jobs.py).

### 1.8 Read the result and choose the next action

1. Check the terminal status.
2. Read the recommendation.
3. Read **Coverage**.
4. Expand **Check outcomes**.
5. Select a severity total or use the finding filters.
6. Expand a finding.
7. Check its location and suggested action.
8. Select **Open code at reviewed commit** if the link is available.
9. Read the report.
10. Download or copy the report if necessary.

A **terminal status** means that this execution has stopped. It can be `completed`, `partial`, `failed`, or `cancelled`.

For a partial snapshot, use **Review remaining content** or **Choose the next batch**. Each action creates another saved review. It does not extend the first report in place.

You can then use **Chat**, add **Rules**, or start another review. GitHub posting is a separate action. Procedure 2.6 explains it.

**Source trace:** [ReviewPage.tsx](frontend/src/pages/ReviewPage.tsx), [FindingCard.tsx](frontend/src/components/review/FindingCard.tsx), [ReportViewer.tsx](frontend/src/components/review/ReportViewer.tsx).

## 2. Feature walkthroughs

### 2.1 Understand review status and recommendation

Status describes execution. Recommendation describes the result. Posting status describes a separate GitHub action.

| Review status | Meaning | Next action |
| --- | --- | --- |
| `pending` | The API saved a job. A worker has not started the review. | Wait. Check worker readiness if the wait is long. |
| `running` | The worker processes the review. | Check progress, leave the page, or cancel. |
| `completed` | The outcome function found no failed or partial check, and no incomplete coverage condition. | Assess findings and the recorded checks. |
| `partial` | A check or scope is incomplete. Some results can still be available. | Read warnings. Review the missing scope or rerun. |
| `failed` | The fetch failed, the execution failed, or the outcome function found all recorded analysis checks failed. | Read the error. Correct the cause before a rerun. |
| `cancelled` | Cancellation stopped the job or prevented its start. | Start a new review if you still need the result. |

The outcome function also considers check states such as `timeout` and `rule_lookup_failed`. A `no_rules` or `skipped` check is not the same as a failed check.

The worker sets the saved recommendation as follows.

| Saved value | Page heading | Rule |
| --- | --- | --- |
| `approve` | Ready for your review | Execution completed and no critical or high finding remains. |
| `request_changes` | Changes recommended | Execution completed and at least one critical or high finding remains. |
| `incomplete` | Limited or incomplete review | Execution did not complete with full coverage and successful required checks. |

The page gives specific headings for pending, running, failed, and cancelled states. A complete review can still have medium or low findings. A complete review also does not prove that all defects were found.

The report is model-generated text. Its wording can differ from the saved recommendation. The worker computes the saved recommendation from status and finding severity. GitHub posting does not turn that recommendation into a GitHub approval.

**Sources:** [outcomes.py](backend/src/services/outcomes.py), [execution.py](backend/src/services/execution.py), [ReviewPage.tsx](frontend/src/pages/ReviewPage.tsx), [report_writer.py](backend/src/agents/nodes/report_writer.py).

### 2.2 Understand findings and coverage

Each finding contains an agent, severity, type, message, and optional location or suggestion. A **severity** ranks the possible impact. The four values are critical, high, medium, and low.

The **Code analyst** uses a language model to examine code quality. The **App security agent** uses a language model to examine application security. The **Architecture agent** checks approved rules. The **Security agent** scans secret patterns and known dependency vulnerabilities without a language-model analysis call.

A **large language model**, or **LLM**, produces text from supplied instructions and context. LLM findings can be wrong or incomplete. Check the location and reasoning before you change code.

The finding card can show **CWE**, a weakness category, and **CVSS**, a numerical vulnerability severity score. OSV data supplies these values when available. Missing scores stay unknown. The security agent currently assigns medium severity when CVSS is absent. That is an application rule, not a published score.

Coverage distinguishes these conditions.

| Coverage field | Meaning |
| --- | --- |
| Eligible files | Paths that pass the source and manifest selection rules. |
| Selected files | Eligible paths selected by the requested batch or file list. |
| Reviewed files | Files from which the application read some selected content. This count can include partial files. |
| Characters | Retained file-content characters across the selected files. |
| Skipped files | Paths with no retained content. This includes excluded paths and eligible paths outside the scope. |
| Truncated files | Files with only part of their content in this run. |
| Unavailable files | Selected files that the content fetch could not read. |
| Reviewed ranges | Start and end character offsets for each retained file part. |
| Budget-skipped files | Selected paths that did not fit after the character limit. |
| Next file offsets | The next character position for unfinished files. |

Character ranges use zero-based offsets. The start is included. The end is excluded. Source line hints use one-based line numbers.

For PR reviews, the retained file-content limit does not cap the whole model request. Selected PR patches, headers, prior findings, and instructions add context. The application sends selected source context to more than one analysis agent.

For PRs, secret scanning examines all available PR patches. Its scope can exceed the files sent to the LLM agents. This distinction matters when a skipped file contains a secret pattern.

The application records removed files and missing PR patches. It does not read removed files as current source. GitHub can omit a patch. A missing patch appears in metadata; that field alone does not force partial status in the current outcome function.

Old reviews can have unknown coverage or commit data. The read schema converts a historical line `0` to an unknown line. It does not invent a location.

**Sources:** [source_service.py](backend/src/services/source_service.py), [security_agent.py](backend/src/agents/nodes/security_agent.py), [schemas/review.py](backend/src/schemas/review.py), [FindingCard.tsx](frontend/src/components/review/FindingCard.tsx).

### 2.3 View history, rerun, compare, and export

**Open a saved review:**

1. Select **Reviews** in the main navigation.
2. Enter part of a review title if necessary.
3. Select a status filter if necessary.
4. Use the page controls.
5. Select a review row.

For one repository, use its **Reviews** tab. The API limits history to the signed-in user's records. It returns the saved findings with each review page. It does not depend on a live stream.

**Start a new review of the current target:**

1. Open a saved review that is no longer running.
2. Select **Review latest commit**.
3. Open the new review result when the request succeeds.

The backend resolves the current PR head or branch again. It retains the prior scope except for commit and file-continuation constraints. It sets posting to false. For a custom file list, the rerun still uses that list. It does not automatically expand to the whole repository.

**Read the comparison:**

1. Open the newer review.
2. Read **Changes since the previous review**, if present.
3. Select **Open previous review** if you need the earlier result.

The API finds the earlier completed or partial review for the same target. It matches agent, type, file, and normalized message text. It does not perform a semantic code comparison.

The API reports resolved findings only when both reviews are complete and their scopes and reviewed path sets match. Otherwise, resolved findings remain unknown. Model wording changes can make an issue appear new.

**Export a report:**

1. Select the copy control in **Review report** to copy its text.
2. Select **Download report** to save a Markdown file.

**Markdown** is a plain-text format for headings, lists, links, and code blocks. The download contains the report text. It is not a full export of all structured findings or coverage records.

**Sources:** [ReviewsPage.tsx](frontend/src/pages/ReviewsPage.tsx), [ReviewPage.tsx](frontend/src/pages/ReviewPage.tsx), [review routes](backend/src/api/routes/reviews.py), [report_actions.py](backend/src/api/routes/report_actions.py), [CopyButton.tsx](frontend/src/components/shared/CopyButton.tsx).

### 2.4 Use chat

1. Open the repository workspace.
2. Select **Chat**.
3. Read the saved conversation.
4. Select **Load older messages** if necessary.
5. Enter a question, or select a prompt starter.
6. Select **Send message**.
7. Select **Stop response** if you need to stop the response stream.
8. Select **Retry response** after an error or stop if you want another response.

Useful questions include “What should I fix first?” and “Which security issues recur?” The question can contain up to 8,000 characters.

Chat uses saved findings and conversation context. It does not fetch full repository source. It does not execute the review graph. It does not start a review, change code, or post to GitHub.

Behind the scenes, the API gets or creates one conversation for the user and repository. It loads the last 20 messages. It reads up to 30 recent finding records and available repository statistics.

The model context includes finding severity, agent, and message text. The current formatter does not add the selected `file` column as a separate location field. It also does not supply the complete review report.

The API saves the question before it calls the model stream. It sends response text directly to the browser. It saves the assistant response in a final step. On interruption, it adds a stopped-response note to the partial text. A retry sends the question again. It does not resume the old model generation.

The conversation endpoint returns up to 100 messages per page. This display history is larger than the 20-message context for one model call.

**Source trace:** [RepoChatPage.tsx](frontend/src/pages/RepoChatPage.tsx) → [repos API](frontend/src/api/repos.ts) → `repo_chat` / `conversation` in [repos.py](backend/src/api/routes/repos.py) → [chat_service.py](backend/src/services/chat_service.py) → [llm.py](backend/src/core/llm.py).

### 2.5 Use architecture rules

An **architecture rule** is a natural-language policy for the repository. For example: “Every protected endpoint verifies resource ownership.” The architecture agent checks approved rules during later reviews.

**Add a manual rule:**

1. Open the repository workspace.
2. Select **Rules**.
3. Select a template if it fits the repository.
4. Edit the rule text.
5. Select **Save approved rule**.

A manual rule starts as approved. Rule text can contain up to 4,000 characters. Use one clear requirement per rule.

**Use an AI suggestion:**

1. Select **Suggest rules with AI**.
2. Wait for the suggestion request.
3. Read each suggested rule.
4. Select **Approve rule** for a useful rule.
5. Select **Reject suggestion** for an unsuitable rule.

The suggestion service scans the default branch. It ranks representative files, such as controllers and services. It samples up to 12 files with up to 5,000 characters each. Its prompt asks for four to eight rules. The response parser requires a JSON array of strings; it does not enforce that count.

The scan is separate from a commit-pinned review. It uses a branch name during retrieval. It does not give a full review coverage report. Treat suggestions as candidate policies.

**Edit or remove a rule:**

1. Select **Edit** to change its text.
2. Select **Save changes**.
3. Select **Disable rule** if an approved rule must stop affecting future reviews.
4. Select **Delete**, then **Confirm deletion**, if you want to remove the rule.

Disabled rules have status `rejected`. The UI can approve them again. Suggested and rejected rules do not affect analysis.

An **embedding** is a numerical representation of text. The API sends rule text to the configured OpenAI embedding model. It stores the rule and its embedding together in PostgreSQL. Edits regenerate the embedding. Deletion removes the row and its embedding.

The durable worker loads all approved rule text when a review starts. It freezes that set for the run and checkpoint recovery. A rule change does not rewrite a saved report. Start a new review to apply the change.

The architecture agent can use vector search if a caller supplies no frozen rule set. That helper ranks stored vectors and includes old approved rules without vectors. The normal durable path uses the approved rule set directly.

**Source trace:** [RepoSettingsPage.tsx](frontend/src/pages/RepoSettingsPage.tsx) → [rule routes](backend/src/api/routes/repos.py) → [architecture_rule_service.py](backend/src/services/architecture_rule_service.py) / [memory_service.py](backend/src/services/memory_service.py). Enforcement uses [execution.py](backend/src/services/execution.py), [architecture_agent.py](backend/src/agents/nodes/architecture_agent.py), and the fallback [vector_search.py](backend/src/tools/vector_search.py).

### 2.6 Post a report to GitHub

Posting is optional. The normal UI never posts when it submits a review. A snapshot cannot post to a PR.

1. Open a completed or partial PR review.
2. Select **Preview GitHub posting**.
3. Check the target PR, commit, status, and report text.
4. Select **Post this review to GitHub** if you want to publish it.
5. Use **Open posted review** after a successful post.
6. Use **Retry GitHub posting** if the post fails.

The backend creates a GitHub PR review with event `COMMENT`. It does not use GitHub events `APPROVE` or `REQUEST_CHANGES`. It does not merge the PR. The text can recommend changes without changing GitHub's approval state.

The backend checks current repository access before posting. It attaches the saved commit. A historical report without a commit must be rerun before posting.

An invisible marker contains the DevReason review identifier. Before it creates a GitHub review, the backend searches existing PR reviews for this marker. It can recover a post that succeeded before a response or database write failed.

Posting failure changes `posting_status` to `failed`. It preserves the analysis report and findings. A retry does not rerun the LLM analysis.

The API also supports an explicit `post_to_github=true` on an older PR request format. The durable worker handles that opt-in after analysis. Current UI submissions set it to false.

**Source trace:** [ReviewPage.tsx](frontend/src/pages/ReviewPage.tsx) → [report_actions.py](backend/src/api/routes/report_actions.py) → [posting.py](backend/src/services/posting.py). Worker opt-in handling is in [execution.py](backend/src/services/execution.py).

### 2.7 Manage connection access

1. Open **Settings**.
2. Check each connected GitHub account.
3. Select **Grant repository access** to change an installation.
4. Select **Connect GitHub account** to connect another account or renew access.
5. Select **Disconnect** to remove a local connection.

Local disconnection removes the stored connection and its installation bindings. It does not uninstall the App on GitHub. Manage the installation on GitHub if you want to remove the App there.

The backend refreshes an expiring user token when a valid refresh token exists. It shows a reconnect state when refresh cannot continue. GitHub installation suspension, deletion, or removed repository access can block later source operations.

Saved results remain user-owned history. Loss of GitHub access does not automatically delete those results.

**Sources:** [IntegrationsPage.tsx](frontend/src/pages/IntegrationsPage.tsx), [github_app.py](backend/src/api/routes/github_app.py), [github_connection_service.py](backend/src/services/github_connection_service.py), [webhooks.py](backend/src/api/routes/webhooks.py).

## 3. System architecture

### 3.1 Components and connections

The **application programming interface**, or **API**, accepts HTTP requests from the frontend. HTTP is the request protocol between the browser and server. Most API messages use **JSON**, a structured text format.

The review worker uses the same database as the API. The API saves work before it returns a review identifier. The worker then claims that work.

**Figure 1. Active system architecture**

```mermaid
flowchart TB
    UI[React frontend] -->|Session| Clerk[Clerk]
    UI <-->|Requests and results| API[FastAPI API]
    subgraph Backend[Backend processes]
        API
        Worker[Review worker and LangGraph]
    end
    API -->|Token check| Clerk
    API <-->|Records| DB[(PostgreSQL)]
    Worker <-->|Jobs and saved state| DB
    API <-->|GitHub operations| GH[GitHub API]
    Worker <-->|Read source| GH
    API <-->|Chat and rules| LLM[OpenAI models]
    Worker <-->|Review and report| LLM
    Worker <-->|Package versions| OSV[OSV API]
    API <-->|State and event reads| Redis[(Redis)]
    Worker <-->|Events and OSV cache| Redis
    %% Invisible links control layout. They do not add service calls.
    GH ~~~ LLM
    LLM ~~~ OSV
    DB ~~~ Redis
```

The worker node includes LangGraph. Figure 5 shows that workflow in detail. Arrow labels summarize requests and returned data.

The security agent's OSV lookup code writes the response cache to Redis. OSV itself does not connect to your Redis server.

| Component | Actual responsibility |
| --- | --- |
| React and TypeScript | Page rendering, forms, navigation, review views, and local interaction state. |
| React Router | Routes and lazy page loading. |
| TanStack Query | API query cache, request states, saved-status polling, and cache refresh. |
| Clerk | User sessions and backend token verification. |
| FastAPI | Protected endpoints, validation, authorization, discovery, chat, rules, and report actions. |
| SQLAlchemy with asyncpg | Access to application records in PostgreSQL. |
| PostgreSQL | Durable jobs, reviews, findings, connections, rules, conversations, and snapshot cache. |
| pgvector | PostgreSQL extension for stored rule embeddings. |
| Psycopg pools | LangGraph checkpoint and memory access to PostgreSQL. |
| Redis | Short-lived OAuth state, replayable review events, worker heartbeat, and OSV response cache. |
| Worker | Job claims, lease renewal, execution deadlines, cancellation, and review execution. |
| LangGraph | Fixed review nodes, conditional routes, parallel checks, state updates, and checkpoints. |
| OpenAI models | Code analysis, application security analysis, architecture analysis, reports, chat, and rule suggestions. |
| OpenAI embedding model | Numerical rule embeddings. |
| GitHub | Account authorization, installations, repository metadata, source, and optional PR review publication. |
| OSV | Known vulnerability records for selected exact package versions. |

Vite serves and builds the frontend. Tailwind CSS supplies the style utilities. Lucide supplies icons. Zustand stores remain in the source, but the new route-based workflow uses API data and local page state.

TypeScript adds type checks to frontend JavaScript. SQLAlchemy maps Python records to database tables. The asyncpg driver performs asynchronous PostgreSQL requests. Psycopg supplies separate database connections for LangGraph storage.

A **cache** is a stored copy that an application can reuse. A **connection pool** reuses open database connections. The API and worker maintain their own pools.

The active discovery, review-source, and posting helpers use the GitHubKit SDK. An **SDK** is a library for service requests. These helpers set a 15-second request timeout and disable SDK automatic retries. OAuth exchange and rule-sample retrieval use HTTP clients in their own services.

The configured project database is PostgreSQL hosted through Supabase. Supabase is not the user sign-in provider. Clerk handles that role. The `supabase` readiness label refers to the configured PostgreSQL connection.

**Sources:** [App.tsx](frontend/src/App.tsx), [router.tsx](frontend/src/router.tsx), [package.json](frontend/package.json), [main.py](backend/src/main.py), [db/base.py](backend/src/db/base.py), [worker.py](backend/src/worker.py), [core/store.py](backend/src/core/store.py), [core/checkpointer.py](backend/src/core/checkpointer.py).

### 3.2 Authentication and record ownership

**Authentication** checks who the user is. **Authorization** checks what the user can access.

The frontend gets a Clerk session token. It sends the token in an `Authorization: Bearer ...` header. The backend verifies the signed token and its permitted frontend origin. A **JWT** is the signed token format that Clerk uses.

The backend uses the JWT subject as `clerk_user_id`. It gets an email from the token, a saved user record, or Clerk. It creates or updates the local user record when necessary. A Clerk webhook can also update the user record.

Routes compare the requested repository, review, or conversation with that user identifier. Requests for another user's record usually receive `404`. Client-side identifiers are not access proof.

The frontend creates a new query client when the Clerk account changes. It also resets older stores. This prevents the previous account's cached page state from becoming the new account's workspace.

**CORS** is the server rule for permitted browser origins. The allowed origins also supply Clerk's permitted token parties. Operators must align these values with the actual frontend URL.

**Sources:** [API client](frontend/src/api/client.ts), [clerk.ts](frontend/src/lib/clerk.ts), [App.tsx](frontend/src/App.tsx), [AppShell.tsx](frontend/src/components/layout/AppShell.tsx), [core/clerk.py](backend/src/core/clerk.py), [main.py](backend/src/main.py), [api/deps.py](backend/src/api/deps.py).

### 3.3 GitHub authorization and installation data flow

**OAuth** is the protocol for user authorization. DevReason starts OAuth only after it identifies the signed-in Clerk user.

The backend creates random **state** and a **PKCE** verifier. State links the return request to the initiating user and page. PKCE links code exchange to the original verifier. The backend stores state in Redis for ten minutes.

**Figure 2. Account connection and verified repository import**

```mermaid
sequenceDiagram
    participant U as React browser
    participant A as FastAPI
    participant R as Redis
    participant G as GitHub
    participant D as PostgreSQL
    U->>A: POST /api/auth/github/start + Clerk token + return_to
    A->>R: Save one-use state, user ID, verifier, return path
    A-->>U: authorize_url
    U->>G: Open authorization URL
    G->>A: GET /github/callback + code + state
    A->>R: GETDEL OAuth state
    A->>G: Exchange code with PKCE verifier
    A->>R: Save user-bound ticket and encrypted tokens
    A-->>U: Redirect to original page + github_ticket
    U->>A: POST /github/complete + Clerk token + ticket
    A->>R: Check ticket owner, then consume ticket
    A->>G: GET /user with GitHub user token
    A->>D: Save account and encrypted credentials
    U->>A: POST /github/refresh
    A->>G: List user installations and allowed repositories
    A->>D: Save verified bindings and repository metadata
    A-->>U: Account status and repository discovery data
```

The callback consumes state with Redis `GETDEL`. That command reads and deletes a value in one operation. A second callback cannot reuse it.

The callback does not immediately bind the GitHub identity to a Clerk account. It creates a short-lived ticket. The authenticated completion request must come from the original Clerk user. This check protects shared authorization links.

The connection service verifies the GitHub profile with `/user`. It encrypts access and refresh tokens before it saves them. It uses **Fernet**, a credential encryption format, and the server's `ENCRYPTION_KEY`.

An installation grant has a separate ten-minute state record. The setup callback checks live user installation access before it imports repositories. An `installation_id` query parameter alone is not proof.

For an installation update without state, the backend returns a verification notice. The frontend can restore the initiating page from short-lived session storage. That stored path controls navigation only. It cannot authorize an installation.

The access check uses GitHub's user-scoped installation and repository listings. The effective set is the intersection of user access and App access. Multiple connected accounts can expose different subsets. Import combines the verified subsets for the same installation.

The frontend refreshes status and import after connection. It also refreshes those queries when the browser regains focus. Repository browsing reads imported database metadata. PR, branch, scope, submission, worker, and publication operations check live repository authorization.

**Sources:** [GitHub routes](backend/src/api/routes/github_app.py), [github_connection_service.py](backend/src/services/github_connection_service.py), [github_api.py](backend/src/core/github_api.py), [crypto.py](backend/src/core/crypto.py), [githubReturn.ts](frontend/src/lib/githubReturn.ts), [useGitHubConnection.ts](frontend/src/hooks/useGitHubConnection.ts).

### 3.4 Database records

A **UUID** is a unique record identifier. The API uses UUIDs for repositories, reviews, jobs, rules, and conversations. These identifiers differ from GitHub's numeric repository and installation identifiers.

| Record | Important data |
| --- | --- |
| `users` | Clerk user identifier, email, and creation time. |
| `github_connections` | Clerk owner, verified GitHub user, encrypted tokens, expiry times, and connection status. |
| `github_installations` | Connection, installation identifier, account name, and binding status. |
| `repos` | Clerk owner, GitHub owner/name, verified GitHub identifiers, and metadata. |
| `reviews` | Target mode, PR or branch, commit, scope, coverage, check outcomes, recommendation, report, status, and posting result. |
| `review_jobs` | Review identifier, request key, attempts, lease token, lease deadline, status, and cancellation request. |
| `findings` | Review/repository links and structured issue fields. |
| `arch_rules` | Repository, rule text, status, source, and a 1,536-value embedding. |
| `conversations` | Unique user/repository conversation. |
| `conversation_messages` | User or assistant text, conversation link, and time. |
| `review_cache` | Snapshot compatibility key, saved result payload, and cache creation time. |

**Figure 3. Main record relationships**

```mermaid
flowchart TB
    User[User] --> Connection[GitHub connection]
    Connection --> Installation[Verified installation binding]
    User --> Repo[Repository]
    Repo --> Review[Review]
    Review --> Job[Review job]
    Review --> Findings[Findings]
    Repo --> Rules[Architecture rules and vectors]
    User --> Conv[Conversation]
    Repo --> Conv
    Conv --> Messages[Conversation messages]
    Repo --> Cache[Snapshot result cache]
    Installation -.->|Verified installation ID link| Repo
```

The dotted edge represents the authorization linkage. It is not a declared repository-to-installation foreign key in the model.

**Alembic** applies database schema migrations. The additive migrations add vector storage, verified connection records, and durable review data. Legacy reviews keep PR mode. Missing historical coverage remains unknown.

LangGraph maintains separate checkpoint and memory tables in the same PostgreSQL system. The worker initializes those tables. The API opens the memory store without running its setup.

**Sources:** [db/models.py](backend/src/db/models.py), [db/base.py](backend/src/db/base.py), [vector/connection migration](backend/alembic/versions/2b1c4d5e6f70_vector_and_github_connections.py), [durable review migration](backend/alembic/versions/3c2d5e6f7081_durable_reviews.py), [core/store.py](backend/src/core/store.py).

### 3.5 Saved jobs, leases, and recovery

A **job** is a saved instruction to perform a review. A **lease** gives one worker temporary ownership. A **fence** checks that ownership before a sensitive database write.

The API saves a pending review and job in one transaction. A **transaction** commits a group of database changes together. A failed commit does not leave only half of that submission.

The worker claims one pending job, or an expired active job. It uses PostgreSQL row locks with `SKIP LOCKED`. Other workers can claim other jobs without taking that row.

Each worker process runs one review job at a time. The graph can run its analysis agents in parallel. More worker processes can process different jobs, subject to database and service limits.

The default lease lasts 90 seconds. The job loop waits up to two seconds between ownership checks. Database and network time can add delay. The worker renews the lease when it still owns the job.

The fence rejects a stale lease, expired lease, cancelled job, or non-running job. A replacement worker gets a new lease token. The old worker cannot safely commit through that fence.

After a worker stop, an expired job can resume from its checkpoint. Recovery has a limit of three claims. A job that reaches that limit becomes failed. The execution deadline defaults to 900 seconds per claimed run. It is not a guaranteed total wait limit for a queued or recovered job.

Completed business failures are not all automatically retried. For example, an analysis can finish as partial, or a fetch can finish as failed. Use a new review after you correct the cause.

**Idempotency** means that a repeated request can reuse the same result instead of creating duplicate work. Review submission supports an `Idempotency-Key`. The frontend retains a request key until it receives a successful response. The backend rejects reuse for a different target or scope.

**Sources:** [review routes](backend/src/api/routes/reviews.py), [reviews API](frontend/src/api/reviews.ts), [jobs.py](backend/src/services/jobs.py), [worker.py](backend/src/worker.py), [execution.py](backend/src/services/execution.py).

### 3.6 Review streaming and saved result recovery

**Server-sent events**, or **SSE**, carry a one-way HTTP event stream from the server to the browser. A **Redis Stream** stores ordered events with identifiers. Reading an event does not remove it.

**Figure 4. Submission, execution, stream, and saved result**

```mermaid
sequenceDiagram
    participant U as React browser
    participant A as FastAPI
    participant D as PostgreSQL
    participant W as Worker and LangGraph
    participant R as Redis
    U->>A: POST /api/reviews + target + request key
    A->>D: Commit pending review and job
    A-->>U: HTTP 202 + review ID
    W->>D: Claim job and renew lease
    U->>A: GET /reviews/ID/stream + cursor + Clerk token
    loop During execution
        W->>D: Save checkpoints, phase outcomes, and coverage
        W->>R: XADD progress and report events
        A->>R: XREAD after this client's cursor
        A-->>U: SSE event ID and JSON payload
        U->>A: GET /reviews/ID every five seconds
        A->>D: Read authoritative saved status
        A-->>U: Review record and saved findings
    end
    W->>D: Save report, findings, final metadata, and terminal state
    W->>R: Complete event
    A-->>U: Final saved result
    Note over U,D: After reload, GET history/detail restores the result without old events
```

The graph first commits report and findings together. Final metadata and terminal review status follow in a separate worker transaction. The job loop then finalizes the job record. Figure 4 groups these writes for readability.

Events include `agent_start`, `agent_complete`, `findings_ready`, `report_token`, `report_ready`, `complete`, and `error`.

The frontend reconnects with its last event cursor during the active page session. After a full page reload, it starts replay at `0-0`. Saved polling and detail retrieval still work without a retained cursor.

Each tab reads independently. The stream endpoint drains retained events before it checks terminal database state. It can then emit a final result from the database for a late subscriber.

Redis event storage expires 24 hours after the latest event write. The approximate stream length limit is 20,000 events. The database has no equivalent automatic review expiry in this implementation.

Redis outages can remove live progress and block connection-state operations. They do not replace the saved review database. Completed results remain available through authenticated detail and history routes when PostgreSQL and authentication work.

**Sources:** [stream_service.py](backend/src/services/stream_service.py), `stream_review` in [reviews.py](backend/src/api/routes/reviews.py), [useLiveReview.ts](frontend/src/hooks/useLiveReview.ts), [useReviews.ts](frontend/src/hooks/useReviews.ts), [execution.py](backend/src/services/execution.py).

### 3.7 External data and credentials

| Destination | Data from DevReason |
| --- | --- |
| Clerk | Session verification and user-profile requests. |
| GitHub | OAuth exchange, account/install/repository requests, source requests, and an optional published report. |
| OpenAI analysis model | Selected source context, relevant PR patches, analysis instructions, and approved rules or prior findings as applicable. |
| OpenAI report model | Selected finding summaries, limited prior findings, check outcomes, and coverage metadata. |
| OpenAI chat model | The question, recent messages, recent finding text, and available repository statistics. |
| OpenAI rule suggestion model | Repository structure facts and bounded representative code snippets. |
| OpenAI embedding model | Rule text, or fallback vector-search query text. |
| OSV | Package ecosystem, name, and exact version. The query does not send repository source. |

The normal analysis and publication paths use a verified GitHub App user token. Rule suggestion routes first authorize the repository. Their scan service then uses an App installation token for that repository.

GitHub connection credentials use explicit application encryption in `github_connections`. The graph wraps its token in `SecretStr`, which masks normal text display. Masking is not a general encryption guarantee for serialized checkpoints. Protect the database and backups as sensitive data.

The API launcher disables raw HTTP access logs because callback query strings can contain one-use authorization codes. Metrics accept only defined event names and an optional duration. They reject arbitrary fields. The actor value is a derived hash.

Worker logs record review completion, time, recovery, and status. Existing application logs can also contain record identifiers and errors. The restricted metrics endpoint does not guarantee that every log or external tracing configuration excludes sensitive data.

Settings contain LangSmith tracing fields. The active startup code does not construct a LangSmith dashboard or explicitly enable tracing from those fields. Environment-driven library tracing requires separate operator review.

**Sources:** [settings.py](backend/src/core/settings.py), [crypto.py](backend/src/core/crypto.py), [state.py](backend/src/agents/state.py), [run.py](backend/src/run.py), [metrics.py](backend/src/api/routes/metrics.py), [architecture_rule_service.py](backend/src/services/architecture_rule_service.py), [chat_service.py](backend/src/services/chat_service.py).

## 4. LangGraph execution

### 4.1 What the graph does

An **agent** here is a named review step. Some agents call an LLM. Other nodes perform fixed code operations. The **graph** defines which node runs next and which nodes can run together.

The supervisor uses code conditions. It does not ask an LLM to invent a plan or select arbitrary tools. The review does not build or execute repository code.

The graph registers 15 named nodes. Older comments still say 12 nodes and three agents. The actual registration and routing include four possible analysis agents.

**Figure 5. Actual graph routes**

```mermaid
flowchart TB
    Start([Start]) --> Fetch[fetch_pr]
    Fetch --> Prior[load_pr_history]
    Prior --> Insights[load_project_insights]
    Insights --> Supervisor[supervisor]
    Supervisor --> Code[code_analyst]
    Supervisor --> Security[security_agent]
    Supervisor --> Arch[architecture_agent]
    Supervisor -->|Sensitive scope or snapshot| Semantic[semantic_security_agent]
    Supervisor -->|Error: no raw patch| Merge[merge_findings]
    Supervisor -.->|Error: raw patch exists| Security
    Code --> Merge
    Security --> Merge
    Arch --> Merge
    Semantic --> Merge
    Merge --> Report[report_writer]
    Report --> Persist[persist_review]
    Persist --> Save[save_pr_memory]
    Save --> Update[update_project_insights]
    Update -->|Durable worker| Complete[complete_review]
    Update -.->|Legacy graph flag| Post[post_to_github]
    Post -.-> Complete
    Complete --> End([End])
```

The dotted posting route exists in the graph. The durable executor always supplies `post_to_github=False` to `RepoConfig`. Current publication uses the separate posting service after analysis or through the explicit API action.

**Sources:** [graph.py](backend/src/agents/graph.py), [supervisor.py](backend/src/agents/nodes/supervisor.py), [execution.py](backend/src/services/execution.py), [post_to_github.py](backend/src/agents/nodes/post_to_github.py).

### 4.2 Shared state and parallel updates

`ReviewState` is the shared graph data object. A node returns only the fields that it changes.

| State group | Important fields |
| --- | --- |
| Input | `pr_url`, `repo_config`, target mode, branch, commit, scope, and lease token. |
| Retrieved context | PR metadata, raw patches, focused analysis patches, selected file content, and coverage. |
| History | Prior findings and repository insight data. |
| Agent output | Separate code, security, application-security, and architecture finding lists. |
| Progress | Completed agent names and the check-status dictionary. |
| Result | Merged findings, report, optional GitHub URL, and error. |

Parallel agents write separate finding lists. The state combines completed-agent lists and check dictionaries with explicit merge functions. This prevents one agent's result from replacing another agent's result.

The graph loads repository insights. The current code-analysis and report prompts do not directly include the whole `project_insights` object. Chat uses the stored aggregate statistics. Prior findings enter the code analyst and report writer contexts.

**Sources:** [state.py](backend/src/agents/state.py), [code_analyst.py](backend/src/agents/nodes/code_analyst.py), [report_writer.py](backend/src/agents/nodes/report_writer.py), [chat_service.py](backend/src/services/chat_service.py).

### 4.3 Node-by-node operation

| Node | Inputs and operation | Output or side effect |
| --- | --- | --- |
| `fetch_pr` | Resolve the saved target. Retrieve PR metadata/files or the snapshot tree. Read selected files at the commit. | File context, patches, coverage, and fetch status. A source error becomes explicit state error. |
| `load_pr_history` | Read up to three stored review-memory items for the same PR or branch. Parse valid findings and remove duplicate history. | Up to 12 prior findings. Store failure produces empty history. |
| `load_project_insights` | Read the repository aggregate memory item. | Insight data, or empty data if unavailable. |
| `supervisor` | Check source error, target mode, paths, and security-sensitive terms. | Dispatch normal agents, optional application security, or the fetch-error path. |
| `code_analyst` | Supply selected code, PR patches where applicable, and prior findings to the LLM. | Code-quality findings and chunk outcome. |
| `security_agent` | Scan raw patch/source text for secret patterns. Parse selected dependencies. Query OSV for exact versions. | Secret/vulnerability findings and dependency coverage warnings. |
| `semantic_security_agent` | Supply selected code and PR patches to the LLM for access, trust, validation, and data-exposure checks. | Application-security findings and chunk outcome. |
| `architecture_agent` | Use frozen approved rules, or fallback rule retrieval. Analyze context against the rules. | Rule findings, `no_rules`, or an explicit lookup/analysis failure. |
| `merge_findings` | Combine four finding lists. Deduplicate by file and the first 80 message characters. Sort by severity. | Merged findings. This node does not save database finding rows. |
| `report_writer` | Give the LLM selected finding summaries, limited history, checks, and coverage. | Markdown report or an explicit report-generation fallback. |
| `persist_review` | Check the lease. Save the report and replace this review's finding rows in one transaction. | Saved results while review status remains running. |
| `save_pr_memory` | Save merged findings, a short report summary, target URL, and time under the review identifier. | Memory for a later review of the same target. Skip on source error. |
| `update_project_insights` | Count deduplicated issue types and affected files. Track processed review identifiers. | Repository aggregate memory. Skip on source error. |
| `post_to_github` | Legacy graph route: use a hosted GitHub MCP review tool if the graph posting flag is true. | Legacy posting result. The durable path does not dispatch this node. |
| `complete_review` | In durable execution, return completion metadata and leave final status to the worker. | The executor subsequently saves terminal status, recommendation, and final coverage. |

**MCP**, or **Model Context Protocol**, connects applications to external tools. The repository has a GitHub MCP helper and legacy posting node. The active fetch/discovery/posting service paths do not rely on that node.

The source also contains an NVD helper. **NVD** is another vulnerability data service. The active dependency security agent queries OSV; it does not call the NVD helper.

**Source trace:** [graph.py](backend/src/agents/graph.py) → [nodes directory](backend/src/agents/nodes) → [execution.py](backend/src/services/execution.py). Tool implementations are in [github_mcp.py](backend/src/tools/github_mcp.py), [osv_search.py](backend/src/tools/osv_search.py), and [nvd_cve.py](backend/src/tools/nvd_cve.py).

### 4.4 Source selection and model chunks

For a PR, the fetch service gets all available file pages before it selects source context. It allows up to 30 pages of 100 file entries. If GitHub reports more changes than the listing contains, coverage remains partial.

For a snapshot, the service reads a recursive Git tree. A **Git tree** lists paths for a commit. If the recursive response is truncated, the service walks smaller trees.

The selection order puts compact manifests first, source files next, and large lockfiles last. It excludes known vendor/generated directories and selected generated file patterns. It then applies the requested paths or file offset.

The content fetch accepts base64-encoded UTF-8 file content. A binary, unreadable, or unavailable file produces an unavailable coverage entry. Large-file responses that do not contain the required encoding are not analyzed through another content endpoint.

The service retains file content until it reaches the character limit. It records the original size and retained range. It adds a source-line hint for continuation parts.

The LLM analysis helper divides context into 12,000-character chunks by default. It processes chunks in order within each agent. Different graph agents can process their contexts in parallel.

Each analysis chunk has up to three attempts. Each attempt has a 60-second timeout. The helper requires a JSON array of valid findings. It overwrites any model-supplied agent name with the actual agent name.

Malformed JSON or invalid finding data counts as a failed attempt. If some chunks fail after retries, the check becomes partial. If all chunks fail, the check becomes failed. Empty valid arrays can mean no findings for that successfully processed context.

The prompt tells the model to treat source as data. It also explains chunk boundaries and unknown line positions. These instructions reduce errors. They do not prove correct interpretation or complete protection from hostile source text.

**Sources:** [fetch_pr.py](backend/src/agents/nodes/fetch_pr.py), [source_service.py](backend/src/services/source_service.py), [analysis.py](backend/src/agents/analysis.py), [code_analyst.py](backend/src/agents/nodes/code_analyst.py), [semantic_security_agent.py](backend/src/agents/nodes/semantic_security_agent.py).

### 4.5 Dependency tools and severity

**OSV** is a service that returns known vulnerabilities for package versions. DevReason extracts an ecosystem, package name, exact version, and local source path from selected manifests.

| Format | Current parser behavior |
| --- | --- |
| `package-lock.json`, `npm-shrinkwrap.json` | Read resolved npm versions from package entries or nested dependency entries. |
| `requirements.txt` | Read pinned `name==version` entries. Unpinned ranges and other requirement forms do not become resolved versions. |
| `poetry.lock` | Read package name/version records from TOML. |
| `Cargo.lock` | Read Rust package name/version records from TOML. |
| `go.mod` | Read exact module versions from recognized require lines. |
| `package.json` | Read exact-looking versions where possible, but warn if a supported companion lockfile is absent. |
| Other known manifests | Mark unresolved or unsupported dependency coverage. |

The parser does not treat `^1.0.0`, `~1.0.0`, or a version range as an exact version. A selected supported companion lockfile can replace a declaration's dependency coverage.

Despite its function name, `osv_batch_query` calls OSV's individual `/v1/query` endpoint. It allows six concurrent lookups and follows response page tokens. It collects full response records, not only vulnerability identifiers.

The Redis cache key uses the package ecosystem, name, and version. The cache lasts 24 hours. The code restores the current manifest path when it turns a cached response into findings. An empty successful response can also be cached.

The security agent gives the whole dependency lookup a 90-second timeout. Redis cache failure does not become a clean scan. It attempts the network query. A network lookup failure marks the check failed.

The CVSS parser supports version 2, 3, and 4 vectors and numerical scores. It chooses the highest valid score in a vulnerability record. It prefers a CVE alias when available. A **CVE** is a public vulnerability identifier. Otherwise, it retains the provider's identifier.

The severity rule is critical for scores of at least 9, high for at least 7, medium for at least 4, and low below 4. An unknown score receives medium finding severity, with no invented numerical score.

Fix suggestions collect published fixed-version events. They are not an automated upgrade plan. Check whether a listed version applies to the dependency's own release line.

**Sources:** [dependencies.py](backend/src/tools/dependencies.py), [osv_search.py](backend/src/tools/osv_search.py), [security_agent.py](backend/src/agents/nodes/security_agent.py).

### 4.6 Checkpoints, memory, and cache are different

A **checkpoint** saves graph execution state and pending work. **Memory** saves information for later reviews. A **cache** reuses a compatible result to avoid another analysis.

**Checkpoint recovery:**

1. The worker reads the review's graph thread.
2. It checks live GitHub repository access.
3. It refreshes the token in the graph configuration.
4. It preserves the rule set stored with unfinished execution.
5. It resumes pending graph work when a checkpoint has a next step.
6. It uses a finished checkpoint result when the graph already ended with a report.

The thread identifier contains the Clerk user, repository, and review identifiers. A later review has a different thread. It does not overwrite the earlier execution.

The checkpoint serializer permits the application's `RepoConfig`, `ReviewState`, and `Finding` types, plus `SecretStr`. It restricts other custom constructors. PostgreSQL and backups still contain sensitive graph context.

**Memory namespaces:**

| Namespace | Stored information |
| --- | --- |
| `repos / REPO_ID / prs / PR_NUMBER` | PR review findings and short report summaries. |
| `repos / REPO_ID / branches / BRANCH` | Snapshot review findings and short report summaries for that branch. |
| `repos / REPO_ID / insights`, key `aggregated` | Issue counts, affected-file counts, processed review IDs, and total reviews. |

Memory writes use the review identifier as a key. The insight update checks processed review identifiers before it counts again. This supports recovery, but it is not a proof of serial correctness for all simultaneous insight updates.

**Snapshot cache:**

The key includes repository, commit, mode, scope, model name, approved rules, configured limits, and a cache version. Reuse lasts one hour. The current key does not include every provider setting or prompt text. Code changes that alter analysis semantics need a cache-version change.

The worker checks authorization before reuse. It creates a separate saved review with a cache-reused flag. It avoids reuse for unfinished checkpoint recovery. Failed or partial check outcomes prevent cache insertion. Limited coverage can still be cached if all performed checks succeeded.

**Sources:** [execution.py](backend/src/services/execution.py), [checkpointer.py](backend/src/core/checkpointer.py), [store.py](backend/src/core/store.py), [review_cache.py](backend/src/services/review_cache.py), [load_pr_history.py](backend/src/agents/nodes/load_pr_history.py), [save_pr_memory.py](backend/src/agents/nodes/save_pr_memory.py), [update_project_insights.py](backend/src/agents/nodes/update_project_insights.py).

## 5. Worked example

### 5.1 Example scope and evidence

This example uses the recorded Teamflow PR #1 result. The UI steps and message samples explain the implemented path. They are not an assertion that an automated signed-in browser submitted that live job.

The implementation checks submitted the live review through application service entry points. They used the real verified Clerk/GitHub binding. The user also confirmed the real GitHub return to the original DevReason page.

| Item | Recorded value |
| --- | --- |
| Repository | `EmmanuelMagala/Teamflow` |
| PR | `https://github.com/EmmanuelMagala/Teamflow/pull/1` |
| Repository record | `ac5c0b4c-761a-4ffc-83b3-39af5befebda` |
| Commit | `6b6c07d47bd1b65ee79ec371739a4de2dee8c194` |
| Saved review | `feb1a09f-719f-475e-b09f-766840765fae` |
| Final status and recommendation | `partial` and `incomplete` |
| Findings | 68 |
| Coverage | 21 of 22 eligible files; 100,000 retained source characters |
| Worker execution time | About 138.1 seconds for this run |
| GitHub posting | `not_requested` |

**Evidence:** Local implementation records and evidence under `.audit/implementation/`. These files are excluded from Git. The earlier audit's 16-finding review is a different saved run.

### 5.2 Step 1: Sign in and connect

1. The maintainer signs in through Clerk.
2. The frontend sends a Clerk token to the GitHub start endpoint.
3. The backend stores user-bound state and a return path in Redis.
4. GitHub returns an authorization code.
5. The backend exchanges the code and returns a one-use ticket.
6. The signed-in frontend completes the ticket.
7. The backend verifies the GitHub user and saves encrypted credentials.
8. The frontend requests verified installation refresh.

The backend gets user-scoped installations and repositories from GitHub. It saves the matching repository metadata. The live discovery check found 20 authorized repositories.

The maintainer sees a connected account and repository cards. If an installation update lacks state, navigation fallback returns to the remembered local page. The server still verifies account access.

### 5.3 Step 2: Select Teamflow and PR #1

1. The maintainer searches for Teamflow.
2. The backend filters imported repository records for that user.
3. The maintainer opens the Teamflow card.
4. The frontend requests the PR list for the repository UUID.
5. The backend checks live GitHub repository access.
6. GitHub returns PR metadata.
7. The page shows PR number, title, author, branch, and draft state where applicable.
8. The maintainer selects **Review** for PR #1.

The frontend creates an idempotency key. It sends a body with this shape:

```json
{
  "repo_id": "ac5c0b4c-761a-4ffc-83b3-39af5befebda",
  "mode": "pr",
  "pr_number": 1,
  "post_to_github": false,
  "scope": {}
}
```

The API rechecks ownership and GitHub access. It resolves the PR head to the recorded commit. It saves a review and a job in one transaction.

The response has this shape:

```json
{
  "id": "feb1a09f-719f-475e-b09f-766840765fae",
  "status": "pending"
}
```

The browser opens `/reviews/feb1a09f-719f-475e-b09f-766840765fae`. It sees a queued state before worker execution starts.

### 5.4 Step 3: The worker reads and checks the code

1. The worker claims the job and gets a lease token.
2. It verifies GitHub access again.
3. It loads approved architecture rules and checkpoint state.
4. The graph retrieves PR metadata and file pages.
5. The fetch node verifies the queued commit.
6. The source service selects eligible files and reads their content.
7. The graph loads prior review memory and repository insights.
8. The supervisor dispatches the analysis agents.

In this run, the source limit retained 100,000 characters. It included 21 files. It truncated `backend/package-lock.json`. It did not retain `frontend/package-lock.json` after the character limit.

The code analyst completed 13 chunks and returned 39 findings. The application security agent returned 29 findings. One of its 13 chunks failed after retries. The dependency security check was partial. It could not parse a full supported lockfile in this scope.

The architecture agent reported `no_rules`. No approved architecture rules existed for this repository during the live run. That result means no architecture policies were checked.

The worker sends phase and report events to Redis. The API streams those events to the browser. It also serves saved status. The user can leave the page during this work.

### 5.5 Step 4: Save and assess the result

1. `merge_findings` combines and sorts 68 findings.
2. `report_writer` produces a Markdown report.
3. `persist_review` commits the report and finding rows together.
4. Memory nodes save target history and repository counts.
5. The executor computes partial status and an incomplete recommendation.
6. The worker saves final coverage and check outcomes.
7. The browser reads the saved result and stops active polling.

The user sees **Limited or incomplete review**. The page shows severity totals, the reviewed commit, coverage, warnings, finding cards, and the report.

The user must not read the zero dependency findings as a clean dependency scan. The dependency check was incomplete. The saved status exposes that distinction.

For a new PR review, the **Review latest commit** action resolves the target again. The PR page does not have the snapshot's **Review remaining content** action. A branch review can inspect more source. A complete JSON lockfile needs a scope and limit that can hold the whole file.

### 5.6 Step 5: Use chat and rules

The following actions are illustrative follow-up steps. They were not part of the recorded 68-finding live review submission.

1. The user opens **Chat** for Teamflow.
2. The user asks, “Which access-control issues should I inspect first?”
3. The API loads recent messages, recent finding text, and repository statistics.
4. The model streams an answer.
5. The API saves the conversation turn.

The assistant has review context. It does not inspect the current Teamflow files for that question. Its context can omit some of the 68 findings because the current recent-finding limit is 30.

The user then opens **Rules** and saves this policy:

> Every protected endpoint verifies resource ownership.

The API generates an embedding and saves the approved rule. The next review freezes that rule in its configuration. The architecture agent can then report policy violations. The old report does not change.

### 5.7 Step 6: Reopen or optionally publish

1. The user refreshes the browser.
2. The user opens **Reviews**.
3. The API returns the saved Teamflow result from PostgreSQL.
4. The user downloads the report if necessary.
5. The user opens a posting preview only if publication is required.
6. The user selects **Post this review to GitHub** only after checking that preview.

The recorded run did not execute Steps 5 and 6. Live GitHub publication remains unverified in the implementation record.

If the user executes them later, the posting service checks access and searches for the review marker. It creates or recovers a GitHub `COMMENT` review. A publication failure preserves the saved analysis.

### 5.8 Branch example: a repository without PRs

The approved snapshot check used `EmmanuelMagala/agentflow-dashboard`, branch `main`. It had no PRs for the designated check.

| Item | Recorded value |
| --- | --- |
| Commit | `d3680196ac36c87f8925566395994b306550f016` |
| Review | `eb69d6ac-a940-4ffd-872e-33971fed587e` |
| Repository paths | 99 total; 88 eligible |
| Initial selected batch | Up to 50 paths |
| Retained content | 37 files; 100,000 characters |
| Findings | 15 |
| Final result | `partial`; recommendation `incomplete`; no posting |
| Worker execution time | About 133.7 seconds for this run |

The source limit stopped during `src/components/ui/dialog.tsx`. The coverage records its unfinished character position. Thirteen other paths in the selected batch did not fit. Other eligible paths remained outside that batch.

The code and application security checks each completed nine chunks. The dependency check remained partial because the selected declaration lacked a supported resolved lockfile in the scope.

The user can select **Review remaining content** for unfinished files and budget-skipped paths. The user can also select **Choose the next batch** for paths after the first 50. Both actions preserve the recorded commit and create a new saved review.

**Flow sources for the example:** [ReviewPage.tsx](frontend/src/pages/ReviewPage.tsx) → [review routes](backend/src/api/routes/reviews.py) → [jobs.py](backend/src/services/jobs.py) → [execution.py](backend/src/services/execution.py) → [graph.py](backend/src/agents/graph.py) → [source_service.py](backend/src/services/source_service.py).

## 6. Troubleshooting and local operation

### 6.1 Install dependencies and start on Windows

Use the repository's Windows commands. The recorded environment requires Python 3.12 or later, Node 22 or later, and Docker Desktop.

1. Configure the backend values in `backend/.env`. Use [backend/.env.example](backend/.env.example) to identify the required keys.
2. Configure `VITE_CLERK_PUBLISHABLE_KEY` and `VITE_API_URL` in `frontend/.env.local`.
3. Open a PowerShell terminal in the project root.
4. Create the Windows virtual environment and install backend dependencies:

```powershell
cd backend
py -m venv .venv-win
.\.venv-win\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cd ..
```

5. Install frontend dependencies:

```powershell
cd frontend
npm.cmd ci
cd ..
```

6. Start the managed development processes:

```powershell
.\start-dev.ps1
```

7. Open `http://localhost:5173`.
8. Check `http://localhost:8000/api/ready`.

The start script starts dedicated Redis, applies Alembic migrations, and starts the API, worker, and frontend. It enables local branch reviews. It aligns the frontend URL, API URL, and CORS values for the selected ports.

The existing `.venv` can be a Linux environment. Its activation path is not the Windows path. Use `.venv-win` on Windows.

If PowerShell blocks activation, run this command for the current terminal only:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

You can also use the virtual environment's Python directly. Activation only changes the terminal's executable paths.

```powershell
cd backend
.\.venv-win\Scripts\python.exe -m pip install -r requirements.txt
```

**Manual start after setup:**

1. Start Redis from the project root:

```powershell
docker compose -f compose.dev.yml -p devreason-dev up -d redis
```

2. Start the API in an activated backend terminal:

```powershell
python -m alembic upgrade head
python -m src.run
```

3. Start the worker in another activated backend terminal:

```powershell
python -m src.worker
```

4. Start the frontend in a frontend terminal:

```powershell
npm.cmd run dev
```

For manual startup, set `BRANCH_REVIEWS_ENABLED=true` if branch reviews are required. Keep the API and worker on the same database and Redis configuration.

**Stop managed processes:**

```powershell
.\stop-dev.ps1
```

The stop script checks recorded executable paths and process start times. It stops the recorded process trees. It leaves Redis and its volume available. A forced worker stop can leave an active job for lease recovery.

**Sources:** [README.md](README.md), [start-dev.ps1](start-dev.ps1), [stop-dev.ps1](stop-dev.ps1), [compose.dev.yml](compose.dev.yml), [run.py](backend/src/run.py), [worker.py](backend/src/worker.py).

### 6.2 Configuration reference

Do not put backend secrets in a `VITE_` variable. Frontend build variables are available to the browser. Keep existing encryption keys when you use stored connection credentials.

| Setting | Purpose or source default |
| --- | --- |
| `DATABASE_URL` | Required PostgreSQL URL with the `postgresql+asyncpg://` scheme. |
| `REDIS_URL` | Required Redis URL. Dedicated local value: `redis://127.0.0.1:6381/0`. |
| `OPENAI_API_KEY` | Required server model credential. |
| `OPENAI_MODEL` | Source default: `gpt-4o-mini`. The environment can override it. |
| `OPENAI_EMBEDDING_MODEL` | Source default: `text-embedding-3-small`. |
| `OPENAI_EMBEDDING_DIMENSIONS` | Source default: 1,536. The vector schema must match. |
| `CLERK_SECRET_KEY` | Required server Clerk credential. |
| `CLERK_WEBHOOK_SECRET` | Required for Clerk webhook verification when that endpoint is used. |
| `VITE_CLERK_PUBLISHABLE_KEY` | Frontend Clerk configuration. A publishable key is not the backend secret key. |
| `ENCRYPTION_KEY` | Required credential encryption key. Prefer 64 hexadecimal characters for a new setup. |
| `GITHUB_APP_ID`, `GITHUB_APP_SLUG`, `GITHUB_APP_PRIVATE_KEY_PATH` | App identity and installation-token support. |
| `GITHUB_APP_CLIENT_ID`, `GITHUB_APP_CLIENT_SECRET` | GitHub App user authorization and token exchange. |
| `GITHUB_APP_WEBHOOK_SECRET` | Signed GitHub access-event verification. |
| `GITHUB_OAUTH_CALLBACK_URL` | Source default: `http://localhost:8000/api/auth/github/callback`. |
| `FRONTEND_BASE_URL` | Source default: `http://localhost:5173`. |
| `ALLOWED_ORIGINS` | Permitted browser origins and Clerk token parties. |
| `VITE_API_URL` | API origin used by the frontend. |
| `PORT` | API launcher port; default 8000. |
| `DURABLE_REVIEWS_ENABLED` | Source default: true. False blocks submission and worker startup. |
| `BRANCH_REVIEWS_ENABLED` | Source default: false. The development start script sets true. |
| `REVIEW_MAX_FILES` | Default 50; valid range 1–500. |
| `REVIEW_MAX_CHARACTERS` | Default 100,000; valid range 1,000–5,000,000. |
| `REVIEW_CHUNK_CHARACTERS` | Default 12,000; valid range 1,000–100,000. |
| `REVIEW_JOB_TIMEOUT_SECONDS` | Default 900; execution deadline for a claimed run. |
| `WORKER_LEASE_SECONDS` | Default 90; valid range 10–3,600. |

The backend loads `.env` relative to its working directory. Run backend commands from `backend`. The managed script does this for each backend process.

The encryption helper accepts an older 32-hexadecimal-character key by deriving a Fernet key. This compatibility path does not provide a key-rotation procedure. Replacing the key can make saved tokens unreadable.

**Sources:** [settings.py](backend/src/core/settings.py), [crypto.py](backend/src/core/crypto.py), [frontend constants](frontend/src/config/constants.ts), [start-dev.ps1](start-dev.ps1), [vector migration](backend/alembic/versions/2b1c4d5e6f70_vector_and_github_connections.py).

### 6.3 Correct GitHub callback and installation settings

1. Open the GitHub App registration in GitHub Developer settings.
2. Set the OAuth Callback URL to `http://localhost:8000/api/auth/github/callback`.
3. Set the Setup URL to `http://localhost:8000/api/auth/github/setup`.
4. Enable **Redirect on update**.
5. Clear **Request user authorization (OAuth) during installation** for this implemented connection flow.
6. Set repository permissions for contents read, metadata read, and pull requests write if posting is required.
7. Save the registration settings.
8. Connect through DevReason and test the return.

DevReason authorizes the user before the installation grant. GitHub hides the separate Setup URL when installation-time OAuth is selected. Changing the backend `.env` does not update the GitHub registration.

If you use different local ports, change both registered URLs to the actual API port. You can select local ports with this command:

```powershell
.\start-dev.ps1 -ApiPort 8002 -FrontendPort 5174
```

Webhook delivery needs a reachable HTTPS endpoint. A GitHub server cannot send an event to your computer's loopback URL. Local signature tests do not prove real delivery.

**Sources:** [README.md](README.md), [github_app.py](backend/src/api/routes/github_app.py), [webhooks.py](backend/src/api/routes/webhooks.py), and [GitHub's App registration instructions](https://docs.github.com/en/apps/maintaining-github-apps/modifying-a-github-app-registration).

### 6.4 Check health and logs

1. Open `/api/health` to check whether the API process responds.
2. Open `/api/ready` to check database, Redis, and worker readiness.
3. Read `.audit/implementation/runtime/api.error.log` if the API fails.
4. Read `.audit/implementation/runtime/worker.log` and `worker.error.log` if jobs do not progress.
5. Read the frontend logs if the local page does not load.

`/api/health` is a **liveness** check. It does not test dependencies. `/api/ready` returns `200` only when its enabled checks pass. A failed check returns `503` with degraded status.

The database check tests a connection and required job/vector columns. The worker announces itself in Redis every ten seconds. Its heartbeat expires after 30 seconds. A hash of the database URL separates heartbeats for different databases.

Readiness does not verify every GitHub permission, an OpenAI request, OSV, or external webhook delivery. Check the relevant operation if one of those services fails.

**Sources:** [health.py](backend/src/api/routes/health.py), [deployment.py](backend/src/core/deployment.py), [worker.py](backend/src/worker.py), [start-dev.ps1](start-dev.ps1).

### 6.5 Fault table

| Symptom | Likely code condition | Action |
| --- | --- | --- |
| `Activate.ps1` is not found | The Windows environment does not exist, or the terminal uses the wrong directory. | Create `.venv-win` from `backend`. Use its `Scripts` path. |
| Frontend shows Clerk Setup Required | Missing, placeholder, or invalid publishable key. | Set the frontend key and restart Vite. |
| API returns `401` | Missing or invalid Clerk token, expired session, or token-party mismatch. | Sign in again. Check frontend origin and Clerk configuration. |
| A record returns `404` | It is absent or belongs to another user. GitHub can also report an unavailable target. | Check the signed-in account, record, and target. |
| GitHub remains open after an access grant | Missing Setup URL or redirect-on-update registration setting. | Use Procedure 6.3. |
| GitHub connection expired or used | Ten-minute state/ticket expiry or repeated completion. | Start a new connection from DevReason. |
| Wrong account started the connection | Completion ticket belongs to a different Clerk user. | Sign in to the initiating account and connect again. |
| Repository is missing | Filters, wrong GitHub account, no App grant, organization approval, or revoked access. | Clear filters. Check Settings and GitHub installation access. |
| GitHub returns `429` | Primary or secondary rate limit. | Wait and retry. Do not start repeated parallel submissions. |
| Job stays pending | Worker absent, no claim, or earlier jobs occupy workers. | Check worker readiness and logs. |
| Worker restarted but review is still active | Prior lease has not expired, or checkpoint recovery is in progress. | Wait for the lease/recovery path. Check attempts and logs. |
| Live progress reconnects | Browser, proxy, or Redis event failure. | Leave the saved review open or refresh it. Check saved status and readiness. |
| Branch review is unavailable | Feature flag is false. The branch UI can still be visible. | Operator: enable the flag and restart backend processes. |
| Source commit changed after PR submission | Current PR head differs from the queued commit. | Start a review of the current PR head. |
| Snapshot preview/commit constraint fails | Submitted scope and resolved commit disagree. | Refresh the preview or submit a deliberate pinned snapshot. |
| Dependency check is partial | Unsupported, unresolved, skipped, or truncated manifest. | Include a full supported manifest in a suitable scope. |
| Dependency check failed | OSV lookup or timeout failed. | Retry after service recovery. Do not interpret zero results as a clean scan. |
| Analysis check is partial or failed | One or more model chunks failed retries or validation. | Read outcomes and coverage. Rerun with an appropriate scope. |
| Architecture shows `no_rules` | No approved rules exist for that repository. | Add or approve rules, then start another review. |
| Rule save fails | Embedding service error, dimension mismatch, or schema failure. | Check OpenAI configuration, vector size, and migrations. |
| Chat cannot explain a source function | Chat has saved finding context, not full source. | Ask about review findings. Run a source review if needed. |
| Comparison shows Unknown resolved | Reviews are partial or have different scopes/path sets. | Compare complete matching scopes. Do not infer a fix from a missing finding. |
| Posting failed | Current access, permissions, GitHub target, or service error. | Preserve the report. Correct permissions and retry the posting action. |
| Old report cannot post | No immutable commit reference. | Select Review latest commit, then inspect the new posting preview. |
| Port is occupied | Another process already listens on the selected port. | Use other ports. Do not start another API on the same port. |

**Sources:** [frontend QueryState](frontend/src/components/shared/QueryState.tsx), [GitHub API errors](backend/src/core/github_api.py), [review routes](backend/src/api/routes/reviews.py), [jobs.py](backend/src/services/jobs.py), [posting.py](backend/src/services/posting.py).

### 6.6 Run verification checks

Run local regression tests against the dedicated test database. Do not point test fixtures at the configured live project database.

1. Start the local test services from the root:

```powershell
docker compose -f compose.dev.yml -p devreason-dev --profile test up -d
```

2. Use an activated backend terminal:

```powershell
cd backend
$env:DATABASE_URL = 'postgresql+asyncpg://devreason:local-test-only@127.0.0.1:55439/devreason_test'
python -m alembic upgrade head
python -m pytest tests/unit tests/regression -q
Remove-Item Env:DATABASE_URL
```

3. Use a frontend terminal:

```powershell
cd frontend
npm.cmd run build
npm.cmd run lint -- --max-warnings 0
npm.cmd run test:browser
```

The browser tests use a fixture server on port 5190. Its Clerk substitute is test-only. It has a separate Vite cache. Tests do not publish to GitHub or call a paid model.

The recorded gate passed 79 backend tests and 12 browser tests. This manual records that evidence. It does not claim a new application test run for document creation.

Live smoke tests require a real connected account and a privately supplied Clerk bearer token. A paid PR analysis also requires `LIVE_SMOKE_RUN_ANALYSIS=true`. Use a designated authorized test PR. Keep posting disabled unless publication is required.

**Sources:** [pytest configuration](backend/pytest.ini), [regression tests](backend/tests/regression/test_durable_application.py), [browser tests](frontend/tests/browser/workflows.spec.ts), [Playwright configuration](frontend/playwright.config.ts), [live smoke routes](backend/tests/integration/test_live_smoke_routes.py), [README.md](README.md).

## 7. Known limitations and verification

### 7.1 Implemented behavior and recorded proof

| Area | Implementation | Recorded proof |
| --- | --- | --- |
| Clerk sign-in | Real Clerk frontend and backend token checks. | Sign-in screen rendered without page errors. Protected automated browser journeys used fixtures. |
| GitHub connection | User-bound OAuth, one-use completion, verified installation access, and return context. | A real account/installation connected. The user confirmed return to the original page. |
| Discovery | Authorized pagination and repository/PR/branch interfaces. | 20 live authorized repositories; 121-repository browser fixture. |
| Durable execution | Saved jobs, leases, fences, cancellation, checkpoints, and replay. | Real local PostgreSQL/Redis regressions, including replacement of the graph worker instance. |
| PR analysis | Commit-pinned source review and saved results. | Approved Teamflow run saved a partial report with 68 findings. |
| Snapshot analysis | Bounded source review without a PR. | Approved agentflow-dashboard run saved a partial report with 15 findings. |
| Chat and rules | Stored conversations, Markdown, stop/retry, templates, suggestions, approval, edits, and deletion. | Browser/backend fixtures. Earlier audit also recorded a separate live chat service turn. |
| Posting | Separate preview, `COMMENT` publication, marker recovery, and retry. | Controlled tests. Actual GitHub publication remains unverified and unperformed in the recorded acceptance runs. |
| Access webhooks | Signed event validation and status/access changes. | Local signature and revocation fixtures. External delivery remains unverified. |
| Production organization policies | Error and recovery paths for approval or revoked access. | Fixtures. Intended organization/SSO policies still need production acceptance. |

The implementation record reports zero known npm advisories and zero known advisories for pinned Windows backend requirements. Those are dated audit results. They are not a permanent claim about future dependency safety.

### 7.2 Product and analysis limits

1. **Authorized repositories only.** A public URL alone does not grant access. Anonymous public review is not implemented.
2. **Manual review start.** The current access webhooks do not automatically review a new PR or a push.
3. **Bounded coverage.** A selected batch can have fewer retained files than selected files. Each additional batch has a separate report.
4. **No aggregate batch report.** The UI does not combine several scopes into one full-repository result.
5. **Partial scope stays partial.** The scope-complete check compares retained files with all eligible paths. A fully read custom subset can still have partial overall coverage.
6. **Eligibility is a heuristic.** Known paths and patterns are excluded. The code cannot identify every generated or vendor file automatically.
7. **PR API limits.** The current listing handles up to 3,000 changed-file entries. Unlisted files force partial coverage. Missing individual patches and removed-file coverage have separate metadata limits.
8. **Manifest limits.** Yarn, pnpm, and several other known formats lack resolved-version parsers. The code marks their coverage incomplete.
9. **Partial lockfiles are not complete dependency data.** Separate reports do not combine lockfile text for the parser.
10. **Model analysis is not execution.** The review does not compile code, execute tests, run a type checker, or verify exploitability.
11. **Prompt limits.** Chunks can split files. Source-line hints and instructions help, but model locations and claims still need assessment.
12. **Secret scan limits.** Pattern checks can produce false positives and miss secrets in other forms. They scan available text, not every binary or excluded snapshot file.
13. **Report summary limits.** The report prompt selects at most four critical, four high, three medium, and two low finding examples. The structured finding list retains more detail.
14. **Chat context limits.** The model receives 20 messages and up to 30 recent findings. It does not retrieve full source or every report.
15. **Comparison limits.** Message changes can affect finding identity. The structured comparison and model-written report comparison use different inputs and methods.
16. **Rule suggestion limits.** A small default-branch sample can miss architecture boundaries. The scan does not use the review's full commit/coverage contract.
17. **Foreground feature requests.** Chat, rule suggestions, and embedding operations run through API requests. They do not use the durable review-job queue.
18. **Posting limits.** Snapshot reports cannot post to PRs. The current service publishes one PR review body, not a set of inline code comments or a merge action.

**Sources:** [source_service.py](backend/src/services/source_service.py), [analysis.py](backend/src/agents/analysis.py), [report_writer.py](backend/src/agents/nodes/report_writer.py), [chat_service.py](backend/src/services/chat_service.py), [report_actions.py](backend/src/api/routes/report_actions.py), [architecture_rule_service.py](backend/src/services/architecture_rule_service.py), [posting.py](backend/src/services/posting.py).

### 7.3 Operational limits

The defaults bound content and execution. They do not guarantee cost, latency, or a complete security audit. The retained character count is not a token or billing limit.

The database is required for durable work and saved results. Redis is required for connection state, event delivery, heartbeat readiness, and webhook delivery deduplication. A degraded Redis connection affects these operations differently.

Worker restart recovery occurs after a lease expires. It does not promise that every external model call resumes at its exact last generated token. An unfinished node can repeat work. A foreground chat response does not use graph checkpoint recovery.

Memory nodes catch some errors and continue. Their missing memory can leave a saved report intact. The default completed phase label does not prove that every optional memory write succeeded. Aggregate insight updates also lack a documented lock for simultaneous jobs on one repository.

Redis events expire. The database has no user-facing review deletion or retention policy in the current routes. The application also has no documented automatic checkpoint cleanup or connection-key rotation workflow.

Some older files, hooks, and comments remain. The current router uses the new pages. Source constants for older six-file context selection do not define the current 50-file durable scope. LangSmith settings and legacy MCP helpers are not proof of an active tracing dashboard or tool-driven review workflow.

The current UI does not expose every API option. For example, repository sorting is an API option. The repository page has search, account filtering, and pagination, but no sort control. History has title/status filters and repository context, not a full date/severity search.

Basic focus, labels, reduced motion, mobile navigation, and overflow checks exist. The record does not establish a formal accessibility certification or a production performance percentile.

The recorded sign-in baseline was 3,025 milliseconds on one cold local navigation. The recorded live worker times were about 138 and 134 seconds. These values describe individual runs, not service guarantees.

Before wider release, verify external webhook delivery, intended organization policies, deployment secrets, database protection, and production performance. Keep real GitHub publication opt-in.

**Sources:** [worker.py](backend/src/worker.py), [jobs.py](backend/src/services/jobs.py), [stream_service.py](backend/src/services/stream_service.py), [memory nodes](backend/src/agents/nodes), [router.tsx](frontend/src/router.tsx), [discovery.py](backend/src/api/routes/discovery.py). Historical test timings come from local implementation records excluded from Git.

## Appendix A. API reference

Protected routes require a Clerk bearer token. GitHub return routes instead use one-use state or a verified follow-up request. Webhooks use provider signatures.

| Method and path | Use |
| --- | --- |
| `GET /api/health` | Process liveness. |
| `GET /api/ready` | Database, Redis, and enabled worker checks. |
| `POST /api/auth/github/start` | Start OAuth with `return_to`. |
| `GET /api/auth/github/callback` | Consume OAuth state and exchange a code. |
| `POST /api/auth/github/complete` | Bind a ticket to the authenticated initiating user. |
| `GET /api/auth/github/status` | Connection configuration and account states. |
| `GET /api/auth/github/installations` | Authorized installation listing for a connection. |
| `POST /api/auth/github/install` | Start an installation grant with a return path. |
| `GET /api/auth/github/setup` | Handle an installation return or approval notice. |
| `POST /api/auth/github/refresh` | Refresh verified installations and repository import. |
| `POST /api/auth/github/sync` | Explicit verified installation sync. Internal/compatibility interface. |
| `GET /api/auth/github/repositories` | User-authorized repositories for an installation. |
| `DELETE /api/auth/github/connections/{id}` | Remove a local connection. |
| `GET /api/repos/browse` | Paginated authorized repository directory. |
| `GET /api/repos/{id}` | User-owned repository metadata. |
| `GET /api/repos/{id}/pulls` | PR page by state. |
| `GET /api/repos/{id}/branches` | Branch page. |
| `GET /api/repos/{id}/scope` | Snapshot path and commit preview. |
| `POST /api/reviews` | Save a review and durable job; return `202`. |
| `GET /api/reviews` | Paginated user-owned review history. |
| `GET /api/reviews/{id}` | Saved report, findings, status, and coverage. |
| `GET /api/reviews/{id}/stream` | Replayable SSE events; cursor support. |
| `POST /api/reviews/{id}/cancel` | Request cancellation. |
| `POST /api/reviews/{id}/rerun` | Save a new current-target review. |
| `GET /api/reviews/{id}/comparison` | Structured finding comparison. |
| `GET /api/reviews/{id}/posting-preview` | Build the optional GitHub review body. |
| `POST /api/reviews/{id}/post` | Publish or recover a PR `COMMENT` review. |
| `GET /api/repos/{id}/conversation` | Stored conversation page. |
| `POST /api/repos/{id}/chat` | Stream a repository review-history answer as plain text. |
| `GET /api/repos/{id}/rules` | List architecture rules; optional status filter. |
| `POST /api/repos/{id}/rules` | Create an approved manual rule and embedding. |
| `POST /api/repos/{id}/rules/suggest` | Create suggested rules from a bounded repository sample. |
| `PATCH /api/repos/{id}/rules/{rule_id}` | Edit content or status. |
| `DELETE /api/repos/{id}/rules/{rule_id}` | Remove a rule and its vector. |
| `POST /webhooks/clerk` | Verify Svix signature and synchronize user creation/updates. |
| `POST /webhooks/github` | Verify HMAC signature and process installation/access events. |
| `POST /api/metrics` | Record an allowed event and optional duration. |

**HMAC** is a keyed signature method. GitHub webhooks use HMAC-SHA256 and a delivery identifier. The handler deduplicates deliveries through Redis. Added repositories appear at the next user-verified sync.

**Svix** is Clerk's webhook signature-verification library. User deletion is not handled by the current Clerk webhook route.

The older `GET /api/repos` route also lists user-owned repository records. The new directory uses `/browse` with verified installation bindings. The current frontend uses `/browse` for discovery.

**Sources:** [main.py](backend/src/main.py), [api/routes](backend/src/api/routes), [frontend workspace API](frontend/src/api/workspace.ts), [ReviewCreate schema](backend/src/schemas/review.py).

## Appendix B. Source map

Use this map when you need to trace a behavior in the IDE. Names refer to the current source, including legacy files where noted.

| Question | Entry files |
| --- | --- |
| Which pages are active? | [router.tsx](frontend/src/router.tsx), [AppShell.tsx](frontend/src/components/layout/AppShell.tsx). |
| How does a request get a session token? | [client.ts](frontend/src/api/client.ts), [clerk.ts](frontend/src/lib/clerk.ts), [backend Clerk](backend/src/core/clerk.py). |
| How does GitHub return to the correct page? | [githubReturn.ts](frontend/src/lib/githubReturn.ts), [useGitHubConnection.ts](frontend/src/hooks/useGitHubConnection.ts), [GitHub routes](backend/src/api/routes/github_app.py). |
| Where does repository authorization occur? | [github_connection_service.py](backend/src/services/github_connection_service.py), [discovery.py](backend/src/api/routes/discovery.py), [reviews.py](backend/src/api/routes/reviews.py). |
| What becomes a saved review job? | [ReviewCreate](backend/src/schemas/review.py), [review routes](backend/src/api/routes/reviews.py), [db/models.py](backend/src/db/models.py). |
| Who executes and recovers jobs? | [worker.py](backend/src/worker.py), [jobs.py](backend/src/services/jobs.py), [execution.py](backend/src/services/execution.py). |
| What are the graph routes? | [graph.py](backend/src/agents/graph.py), [supervisor.py](backend/src/agents/nodes/supervisor.py), [state.py](backend/src/agents/state.py). |
| What source can a review read? | [fetch_pr.py](backend/src/agents/nodes/fetch_pr.py), [source_service.py](backend/src/services/source_service.py). |
| How does model output become a finding? | [analysis.py](backend/src/agents/analysis.py), [state.py](backend/src/agents/state.py), [schema](backend/src/schemas/review.py). |
| Which vulnerability tools are active? | [security_agent.py](backend/src/agents/nodes/security_agent.py), [dependencies.py](backend/src/tools/dependencies.py), [osv_search.py](backend/src/tools/osv_search.py). |
| How does a report reach the browser? | [execution.py](backend/src/services/execution.py), [stream_service.py](backend/src/services/stream_service.py), [useLiveReview.ts](frontend/src/hooks/useLiveReview.ts). |
| How do findings and report commit? | [persist_review.py](backend/src/agents/nodes/persist_review.py), [review_repo.py](backend/src/db/repositories/review_repo.py). |
| What survives a graph restart? | [checkpointer.py](backend/src/core/checkpointer.py), [store.py](backend/src/core/store.py), [memory nodes](backend/src/agents/nodes). |
| Why can a snapshot result be reused? | [review_cache.py](backend/src/services/review_cache.py), [execution.py](backend/src/services/execution.py). |
| Which rules affect analysis? | [rule routes](backend/src/api/routes/repos.py), [memory_service.py](backend/src/services/memory_service.py), [architecture_agent.py](backend/src/agents/nodes/architecture_agent.py). |
| What does chat know? | [RepoChatPage.tsx](frontend/src/pages/RepoChatPage.tsx), [chat_service.py](backend/src/services/chat_service.py). |
| How does posting avoid a duplicate? | [posting.py](backend/src/services/posting.py), [report_actions.py](backend/src/api/routes/report_actions.py). |
| Which assertions have recorded tests? | [backend regressions](backend/tests/regression/test_durable_application.py), [browser workflows](frontend/tests/browser/workflows.spec.ts). Run-specific results are in local implementation records. |

The source controls implementation facts. The records control claims about tests and live acceptance. If either changes, update this manual before you use it as a release manual.

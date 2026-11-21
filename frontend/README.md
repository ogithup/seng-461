# Frontend (owner: Sam)

React + Vite + TypeScript UI for the AI Website Agent. It talks **only** to the REST API in
`backend/api/` (contract: `docs/api-contracts.md`, `docs/sprint4-contracts.md`) and never
imports backend code.

## What it does (Sprint 4: live frontend and preview)

- **Projects**: create one, or reopen an existing one from the start screen or the top-bar
  selector. The open project's id is kept in `localStorage`, so a page refresh reopens it.
- **Chat**: input + **Send** (Enter sends, Shift+Enter adds a line). Chat history lives in the
  browser session only; the API does not store messages yet. If a request fails, its text stays
  in the box so it can be edited and sent again.
- **Latest request**: a card at the top of the Status panel shows what happened to the last
  thing you asked, using only what the backend reported:
  `Pending` (sent, nothing planned yet, or tasks planned but not started) → `Running` (with a
  progress bar) → `Succeeded`, or `Failed` with the backend's reason. Also `Awaiting approval`,
  `Cancelled`, `Interrupted` (the answer never arrived and the backend shows nothing for it)
  and `Unknown` (a status this UI doesn't know). See "How task states are decided" below.
- **Status**: the project's own status from the backend and every task's status (`Pending /
  Running / Succeeded / Failed / Awaiting approval / Skipped / Cancelled`). A failed task shows
  the error the executor recorded (`stderr` from `GET /logs`); skipped tasks say why.
- **Approvals**: when the API returns a `pending_action`, an approval card shows the exact
  command with **Approve** / **Reject**. The UI only sends the decision with the
  `command_hash` it displayed; the server decides what needs approval and what a decision does.
- **Files**: the generated files (`GET /files`); click one to read it (`GET /files/content`).
  Files that can't be shown (binary, too large, gone) say so instead.
- **Preview**: the site in `<iframe sandbox="allow-scripts">` from `GET /preview`, with
  **Reload** and **Open in new tab**. If the last run failed, a warning says the preview may be
  incomplete; if the last request was refused, a note says the preview is from an earlier one.
- **Execution log**: every action (`write_file <path>`, or a command) with status, duration
  and output, newest first.
- **Connection**: the top-bar badge shows `Mock API`, or `Live API · connected / unreachable`
  from `GET /health` (hover for the URL; **Retry** re-checks).
- **Errors**: API errors become readable messages in a dismissible banner, chat bubbles, the
  request card, or the panel they belong to. A failed background status check shows a small
  "Status updates paused" line and polling keeps going.

## Run

```bash
cd frontend
npm install
npm run dev          # mock mode: http://localhost:5173, no backend needed
npm run dev:live     # live mode: talks to the API at http://localhost:8000/api (.env.live)
npm test             # all unit and UI tests (mocked; the live smoke test is skipped)
npm run typecheck
npm run build
```

### Mock vs. live API

| Variable | Default | Meaning |
|---|---|---|
| `VITE_USE_MOCK` | `true` | `true`/unset: in-browser fake backend. `false` (or `0`/`no`/`off`): the real API |
| `VITE_API_BASE_URL` | `http://localhost:8000/api` | Base URL of the API; must end in `/api` |

Three ways to choose, from simplest:

1. `npm run dev:live` uses `frontend/.env.live` (`VITE_USE_MOCK=false`, local API). Works the
   same on Windows, macOS and Linux.
2. Copy `.env.example` to `.env.local` (git-ignored) and edit it; `npm run dev` picks it up.
3. Set the variables in the shell: `VITE_USE_MOCK=false VITE_API_BASE_URL=... npx vite`.

Restart the dev server after changing them. The backend must allow the page's origin
(`CORS_ORIGINS`, default `http://localhost:5173`). `VITE_*` values are compiled into the
browser bundle, so never put secrets in them. The v1 API has no authentication; if one is put
in front of it, a 401/403 is shown as a sign-in/access message rather than a raw error.

### Running against the real backend

From the repo root:

```bash
pip install -r backend/requirements-dev.txt
uvicorn backend.main:app --port 8000        # Swagger at http://localhost:8000/docs
cd frontend && npm run dev:live              # then open http://localhost:5173
```

Manual check: create a project, send `Create a blog called Travel Notes`. The request card goes
`Pending` → `Succeeded`, every task shows `Succeeded`, the files list `index.html` and friends,
clicking one shows its content, and the preview shows the site. Send
`Create a portfolio for Ada Lovelace` and the preview changes. Reload the page: the project,
tasks, files and preview come back from the backend.

### Mock mode

The mock answers in the browser with the same contract and labels its files and preview as
mock data. POST /chat creates every task as `pending` and runs them one by one, so polling shows
progress. Phrases that exercise the other states (mock only):

| You send | The mock does |
|---|---|
| `Create a blog` / `portfolio` / `landing page`, `... called X` | Builds a small site: one `write_file` task per file |
| anything with `simulate failure` | The second write fails (reason in the log), later tasks are `skipped` |
| a shop, store, e-commerce, mobile app, booking system... | `422 unsupported_request`, as the Sprint 4 interpreter does |
| `run <command>` | Waits for approval; approving fails because `run_command` is closed |

## Tests

| File | What it covers |
|---|---|
| `__tests__/App.test.tsx` | The UI on the mock: project creation, chat, Pending/Running/Succeeded/Failed, unsupported and interrupted requests, stale polls, unknown statuses, loading, files, preview, log, approvals |
| `__tests__/LiveApp.test.tsx` | The UI on the **live client** over a fake HTTP backend: request URLs, bodies and headers, preview URL resolution, unreachable backend, unreadable responses |
| `__tests__/httpApi.test.ts` | The HTTP client: contract shapes, idempotency keys, retries, timeouts, response validation, preview URL safety, error messages |
| `__tests__/mockApi.test.ts` | The mock backend and the mock/live configuration (`VITE_USE_MOCK`, `VITE_API_BASE_URL`) |
| `__tests__/requestSummary.test.ts` | How the latest request's state is derived from the backend's answers |
| `__tests__/live.smoke.test.ts` | **Integrated** smoke test against a running backend (skipped by default) |

Integrated smoke test, with the API running:

```bash
VITE_SMOKE_API_URL=http://127.0.0.1:8000/api npm run test:smoke
```

It creates a project, generates a blog and a portfolio, checks tasks against `/logs`, files,
file contents, the sandboxed preview (status, CSP header, every file reachable) and the error
envelope. The unsupported-request check is skipped on a backend that builds a site for
"Build an online shop" (no Sprint 4 interpreter yet); set `VITE_SMOKE_EXPECT_UNSUPPORTED=true`
to make it mandatory once that is merged. `VITE_SMOKE_ORIGIN` changes the origin used for the
CORS check (default `http://localhost:5173`). It writes to whatever database that backend uses.

## Structure

```
src/
  services/   types.ts (API contract types), httpApi.ts (real client), mockApi.ts (in-browser fake),
              validate.ts (response shape checks), errors.ts (error envelope → readable message),
              index.ts (picks mock/live from env)
  hooks/      useAgentSession.ts — projects, open project, task state, latest request, chat,
              approvals, polling; useBackendHealth.ts — connection badge;
              useExecutionLogs.ts, useProjectFiles.ts, usePreview.ts — one per workspace panel
  components/ ProjectForm, ProjectList, ProjectSelector, ChatPanel, ChatInput, StatusPanel,
              ApprovalCard, FilesPanel, PreviewPanel, LogsPanel
  pages/      WorkspacePage
  utils/      requestSummary.ts — latest request state; format.ts — times, sizes, prompts
```

## How task states are decided

- The API has no request id, but it numbers tasks in order and a request only appends tasks.
  When you send, the UI notes the highest task id; tasks above it belong to that request.
- **Succeeded** only when every one of the request's tasks is `succeeded` per the backend, and
  either `POST /chat` has answered or the backend reports the project `completed`.
- **Failed** when one of its tasks is `failed` (reason from `GET /logs`), or when the backend
  refused the request (4xx such as `unsupported_request`, or 502 from planning: nothing was
  created, so no later tasks are attributed to it).
- **Interrupted** when the answer never arrived (network error, timeout after 60 s, 500). The
  UI then re-reads `GET /tasks`; if the request did run, its tasks decide the state as usual.
- A status this UI doesn't know is shown as `Unknown (<value>)` and never counted as success.
- A status check that started before `POST /chat` answered is dropped if it arrives later, so an
  older "running" snapshot can't replace the final result.

## Contract notes (from docs/api-contracts.md)

- `POST` requests send a fresh `Idempotency-Key`; the same key is reused when retrying.
- Retryable errors (`409 project_busy`, `429 rate_limited`, `502 agent_error`) are retried up to
  twice, honouring `Retry-After`. Other errors are shown to the user via the error envelope.
- Every 2xx body is checked against the contract's shape; anything else is reported as
  `invalid_response` instead of being rendered.
- The API returns the **full** task list each time, so the UI replaces its state rather than merging.
- `GET /tasks` is polled every 1.5 s while a request is in flight or `status` is `running` (no
  push channel yet). Reads don't take the project lock, so this shows tasks finishing during
  the synchronous `POST /chat`.
- Files, log and preview refetch when the project state changes. The log is read incrementally
  with `after_id`, re-reading from the first entry still awaiting approval (its status changes).
- `GET /preview` returns a path (`/api/preview/<id>/`); the client resolves it against
  `VITE_API_BASE_URL` so the iframe loads it from the API's origin. Only `http(s)` URLs are used.
- A task prompt may end in an opaque `[delta:…]` token (Sprint 4 orchestrator); the task list
  hides it and shows the full prompt on hover.

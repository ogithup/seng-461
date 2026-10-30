# Frontend (owner: Sam)

React + Vite + TypeScript UI for the AI Website Agent. It talks **only** to the REST API in
`backend/api/` (contract: `docs/api-contracts.md`) and never imports backend code.

## Sprint 3 scope: website-building workspace

- **Projects**: create one, or reopen an existing one from the start screen or the top-bar
  selector. The open project's id is kept in `localStorage`, so a page refresh reopens it.
- **Chat**: input + **Send** (Enter sends, Shift+Enter adds a line). Chat history lives in the
  browser session only; the API does not store messages yet.
- **Status**: run status and every task's status (`Pending / Running / Completed / Failed /
  Awaiting approval / Skipped / Cancelled`). Updated live while a request is running.
- **Approvals**: when the API returns a `pending_action`, an approval card shows the exact
  command with **Approve** / **Reject**. The UI only sends the decision with the
  `command_hash` it displayed; what needs approval, and what a decision does, is decided by
  the server.
- **Files**: the generated files (`GET /files`); click one to read it (`GET /files/content`).
- **Preview**: empty, loading, ready and error states. Ready shows the site in
  `<iframe sandbox="allow-scripts">`, with **Reload** and **Open in new tab**.
- **Execution log**: every action (`write_file <path>`, or a command) with status, duration
  and output, newest first.
- **Errors**: API errors become readable messages in a dismissible banner, chat bubbles, or the
  panel they belong to.
- Runs on **mock responses** by default, so it works without the backend.

Target flow: `"Create a blog"` → API → agent plans one `write_file` task per file → executor
writes them → tasks, files, log and preview update in the workspace.

In mock mode, `run <command>` (e.g. `run npm install`) asks for approval so the approval card
can be tried. As in the real Sprint 3 backend, approving it still fails: `run_command` is closed.

## Run

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 (the origin the API allows by default)
npm test           # Vitest + Testing Library
npm run build
```

### Mock vs. live API

Copy `.env.example` to `.env.local`:

| Variable | Default | Meaning |
|---|---|---|
| `VITE_USE_MOCK` | `true` | `true`: in-browser fake backend. `false`: call the real API |
| `VITE_API_BASE_URL` | `http://localhost:8000/api` | Base URL of Oğuz's API |

For the live API, start the backend from the repo root (`uvicorn backend.main:app --reload`),
set `VITE_USE_MOCK=false`, and restart `npm run dev`. The header badge shows which mode is active.

## Structure

```
src/
  services/   types.ts (API contract types), httpApi.ts (real client), mockApi.ts (in-browser fake),
              errors.ts (error envelope → readable message), index.ts (picks mock/live)
  hooks/      useAgentSession.ts — projects, open project, task state, chat, approvals, polling
              useExecutionLogs.ts, useProjectFiles.ts, usePreview.ts — one per workspace panel
  components/ ProjectForm, ProjectList, ProjectSelector, ChatPanel, ChatInput, StatusPanel,
              ApprovalCard, FilesPanel, PreviewPanel, LogsPanel
  pages/      WorkspacePage
  utils/      format.ts — times, sizes, durations
```

## Contract notes (from docs/api-contracts.md)

- `POST` requests send a fresh `Idempotency-Key`; the same key is reused when retrying.
- Retryable errors (`409 project_busy`, `429 rate_limited`, `502 agent_error`) are retried up to
  twice, honouring `Retry-After`. Other errors are shown to the user via the error envelope.
- The API returns the **full** task list each time, so the UI replaces its state rather than merging.
- `GET /tasks` is polled every 1.5 s while a request is in flight or `status` is `running` (no
  push channel yet). Reads don't take the project lock, so this shows tasks finishing during
  the synchronous `POST /chat`.
- Files, log and preview refetch when the project state changes. The log is read incrementally
  with `after_id`, re-reading from the first entry still awaiting approval (its status changes).
- `GET /preview` returns a path (`/api/preview/<id>/`); the client resolves it against
  `VITE_API_BASE_URL` so the iframe loads it from the API's origin.

# Frontend (owner: Rana)

React + Vite + TypeScript UI for the AI Website Agent. It talks **only** to the REST API in
`backend/api/` (contract: `docs/api-contracts.md`) and never imports backend code.

## Sprint 1 scope

- Create a project (the chat needs a `project_id`)
- Chat input + **Send** button (Enter sends, Shift+Enter adds a line)
- Status panel: run status (`Idle / Working / Waiting for approval / Completed / Failed / Cancelled`),
  task list with per-task status, and a notice when a command waits for approval
- Runs on **mock responses** by default, so it works before the backend is integrated

Target flow: `"Create a blog"` → API → fake agent → two tasks (`create project`,
`create index.html`) → shown in the status panel.

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
  services/   types.ts (API contract types), httpApi.ts (real client), mockApi.ts (Sprint 1 fake),
              errors.ts (error envelope → readable message), index.ts (picks mock/live)
  hooks/      useAgentSession.ts — project, task state, chat messages, polling while "running"
  components/ ProjectForm, ChatPanel, ChatInput, StatusPanel
  pages/      WorkspacePage
```

## Contract notes (from docs/api-contracts.md)

- `POST` requests send a fresh `Idempotency-Key`; the same key is reused when retrying.
- Retryable errors (`409 project_busy`, `429 rate_limited`, `502 agent_error`) are retried up to
  twice, honouring `Retry-After`. Other errors are shown to the user via the error envelope.
- The API returns the **full** task list each time, so the UI replaces its state rather than merging.
- `GET /tasks` is polled every 1.5 s while `status` is `running` (no push channel yet).

## Later sprints

Approval card (approve/reject with `command_hash`), logs (`GET /logs?after_id=`), file viewer,
and the preview iframe (`<iframe sandbox="allow-scripts">`).

# Sprint 4 demo: run the whole application locally

Everything below runs on the real backend (agent, generator, bounded file executor, SQLite).
There are no mock responses in this path.

## Set up (once)

```
pip install -r backend/requirements.txt -r backend/requirements-dev.txt
cd frontend && npm install && cd ..
```

## Start

```
# terminal 1, repo root: API on http://localhost:8000 (Swagger at /docs)
python -m uvicorn backend.main:app --port 8000

# terminal 2: React UI on http://localhost:5173, talking to the API above
cd frontend && npm run dev:live
```

Data lives in `data/app.db` (override with `DATABASE_PATH`) and generated sites in
`workspaces/project_<id>/` (override with `WORKSPACE_ROOT`). Delete both for a clean start.

## What to type

| Request | Result |
|---|---|
| `Create a blog` | blog with Home and About pages |
| `Create a blog called Travel Notes` | same, with that title |
| `Create a portfolio for Ada Lovelace; pages: Projects, Contact; primary: #112233; font: serif` | portfolio with extra pages and theme |
| `Create a landing page for Acme` | landing page |
| `Create an online shop` | refused with a clear message (not turned into another site) |

Optional labelled parts after the first `;`: `pages:` (comma list), `section:` (heading added to the
home page), `primary:`, `accent:`, `font:` (`sans`, `serif`, `mono`). Anything else is rejected.

## Demo script

1. Create a project named "Sprint 4 Demo" in the UI.
2. Request a blog; watch the tasks go to succeeded, open the generated files, open the preview.
3. Create a second project, request the portfolio above; the files and look differ.
4. Stop and restart the backend (`Ctrl+C`, start it again); refresh the page, reopen the project:
   tasks, files and preview are the same and nothing is regenerated.
5. Send "Create an online shop": the UI shows the refusal, not a success.

## Checks

```
python -m pytest -q                      # backend: unit, integration, acceptance
cd frontend && npx vitest run            # frontend (mocked)
# with the API running (step "Start"):
cd frontend && VITE_SMOKE_API_URL=http://127.0.0.1:8000/api VITE_SMOKE_EXPECT_UNSUPPORTED=true npm run test:smoke
cd frontend && npx tsc --noEmit          # type check
```

`tests/integration/test_sprint4_acceptance.py` automates the acceptance script of
`docs/sprint4-contracts.md` (blog, portfolio, restart, unsupported request, controlled failure,
interrupted work).

## Known limits

- A malformed labelled part (for example `colour: blue`) is rejected as a generic `502 agent_error`;
  it should be a `422` once the agent raises a user-facing error for it (Bejan).
- No automatic retries or AI repair; shell commands stay disabled even when approved.
- Conversation memory and editing an existing site are out of scope.

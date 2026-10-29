# Sprint 4 baseline and contracts (published by Oğuz, branch `integration/sprint-4`)

Goal: a deterministic end-to-end MVP. A user creates a project in the React UI, asks for a
supported site, sees real task results, inspects the files and previews the site, and finds it
all again after a restart. No live LLM this sprint, but nothing here may block adding one.

## 1. Baseline

Everyone branches from `main` (Sprint 3 fully integrated: storage, generator, agent, API;
253 tests pass). Sam's Sprint 3 frontend work was not part of it. One branch per person:

| Person | Branch | Owns |
|---|---|---|
| Bejan | `feature/sprint4-agent-spec` | `backend/agent/**` |
| Rana | `feature/sprint4-generator` | `backend/generator/**` (also owns the `WebsiteSpec` definition) |
| Sam | `feature/sprint4-frontend-preview` | `frontend/**` |
| Koray | `feature/sprint4-storage-recovery` | `backend/storage/**` |
| Oğuz | `integration/sprint-4` | `backend/api/**`, `backend/integration/**`, `docs/*contracts*.md`, `tests/integration/**` |

Shared files (`backend/api/services/ports.py`, `backend/api/schemas/contracts.py`,
`backend/api/services/container.py`, `docs/*contracts*.md`) change only through Oğuz.
Propose a change in a PR description or message; do not edit them on a feature branch.

## 2. Pipeline and separation

```
Request interpreter -> validated WebsiteSpec -> Orchestrator -> Generator
        -> write_file actions -> API runner -> WorkspaceExecutor -> verified result
```

- The interpreter and orchestrator never touch the filesystem, database, network or shell.
- The generator never writes files. It returns `{path: text}`.
- Only `WorkspaceExecutor` writes, after validating path, type and size and reading the file back.
- A task is `succeeded` only from a successful executor result. Storage does not decide success.
- A future LLM replaces only the interpreter, and its output goes through the same spec validation.

## 3. WebsiteSpec v1 (approved subset)

Definition and validation live in `backend/generator/spec.py` (`normalize_spec`). Rana owns it.
The interpreter may set only these fields this sprint:

| Field | Rule |
|---|---|
| `site_type` | `blog`, `portfolio` or `landing` (required) |
| `title` | 1-80 characters (required) |
| `pages[]` | 1-12, must contain `index`; each has `slug` (`a-z0-9-`), `title`, `sections[]` |
| `sections[]` | `heading`, and `body` or `items`; optional `kind` from the generator's list |
| `theme` | `primary` and `accent` as `#rrggbb`, `font` one of `sans`, `serif`, `mono` |

Optional and already supported: `tagline`, `footer`, `options.include_script`. Adding any field
or making one required needs Bejan and Rana to agree on the definition and Oğuz to approve it
here first. `spec_for()` in `backend/integration/reference_generator.py` is a Sprint 3
stand-in; Bejan should move to Rana's `starter_spec` and then it can be retired.

## 4. Interpreter boundary (Bejan, internal to `backend/agent/`)

```python
interpret(message: str) -> dict      # a spec that already passes normalize_spec
```

Same message in, same spec out for the rule-based version. The orchestrator takes the
interpreter as a constructor argument. `plan(message)` and `next_action(task, last_result)` keep
their current `AgentPort` behaviour.

## 5. Unsupported requests (implemented in the API)

The agent must not turn an unsupported request into some other site. It raises an exception
carrying two attributes, without importing anything from `backend/api`:

```python
class UnsupportedRequest(ValueError):
    code = "unsupported_request"
    user_message = "Online shops are not supported yet. Try a blog, portfolio or landing page."
```

The API answers `422` with the standard error envelope, `code: "unsupported_request"` and that
`user_message` (max 300 characters; a generic text is used if it is missing or has control
characters). No task is created. Any other exception from `plan` remains a generic `502
agent_error`, and its text never reaches the browser.

## 6. Failures and what the UI can rely on

- A failed write marks the task `failed`, later tasks `skipped`, the project `failed`.
- The reason is in `GET /api/logs` (`stderr`); there is no automatic retry this sprint.
- Task statuses: `pending running waiting_for_approval succeeded failed skipped cancelled`.
  Project: `idle running waiting_for_approval completed failed cancelled`.
- `POST /api/chat` returns when the work is done. To show progress, poll `GET /api/tasks`.
- Preview: `GET /api/preview?project_id=` gives `static` plus a URL relative to the API origin;
  embed it in `<iframe sandbox="allow-scripts">`. Files: `/api/files`, `/api/files/content`.
- Sending another message to a project adds tasks; it does not replace earlier ones.

## 7. Integration order and pull requests

Merge into `integration/sprint-4` in this order, running `pytest` (and `npx vitest run` in
`frontend/`) after each: Koray, Rana, Bejan, Sam. A failure after a merge is fixed by the owner of
the module that broke it.

Each PR describes: purpose, branch and commits, exact files changed, new behaviour, tests run
and results, known limits, shared-interface changes, integration notes, and screenshots for UI.

## 8. Final acceptance (Oğuz runs it on `integration/sprint-4` before merging into `main`)

1. Create a project named "Sprint 4 Demo" in the UI; request a blog; files are written.
2. Task results match `/api/logs`; the files can be inspected; the preview opens.
3. Repeat with a portfolio; the output differs meaningfully.
4. Restart the backend; the project, tasks, files and preview are unchanged.
5. Trigger a controlled failure (for example an unsupported request); the UI shows it, not success.
6. Full test suite run and any remaining failures documented.

## 9. Run it locally

```
pip install -r backend/requirements.txt -r backend/requirements-dev.txt
uvicorn backend.main:app --port 8000            # API; Swagger at /docs
cd frontend && npm install
VITE_USE_MOCK=false VITE_API_BASE_URL=http://localhost:8000/api npx vite --port 5173
pytest                                          # backend tests; `npx vitest run` for the UI
```

Environment variables are listed in `docs/api-contracts.md`.

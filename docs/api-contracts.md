# API contracts (backend/api — owner: Oğuz)

The REST API is the only thing the frontend talks to, and the place where the agent,
execution and storage modules meet. This file is the contract for all four neighbours.
Change it in a PR that every affected owner approves.

## Run it

```bash
python -m venv .venv && .venv/Scripts/activate        # macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements-dev.txt
uvicorn backend.main:app --reload                     # from the repo root; docs at /docs
pytest                                                # integration tests in tests/integration
```

Sprint 3 default: `backend.agent.Orchestrator` (with `backend.generator.WebsiteGenerator`) plans one `write_file` per generated
file, the bounded `WorkspaceExecutor` writes and verifies them, records live in SQLite, and **no
shell command is ever executed**. See `docs/sprint3-contracts.md` for the module contracts.
To integrate a real module, pass it to `build_services(storage=..., agent=..., executor=...)` in
`backend/api/services/container.py` or set `AGENT_IMPL` / `GENERATOR_IMPL`.

| Env var | Default | Meaning |
|---|---|---|
| `DATABASE_PATH` | `<repo>/data/app.db` | SQLite file for projects, tasks, execution logs |
| `AGENT_IMPL` | built-in `Orchestrator` | `package.module:Name` of an `AgentPort` factory |
| `GENERATOR_IMPL` | built-in generator | `package.module:Name` of a `SiteGeneratorPort` factory |
| `WORKSPACE_ROOT` | `<repo>/workspaces` | Per-project folders: `project_<id>/` |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Browser origins allowed (Vite dev server) |
| `REQUIRE_IDEMPOTENCY_KEY` | `false` | Make the `Idempotency-Key` header mandatory on POSTs |
| `API_RATE_LIMIT_PER_MINUTE` | `30` | Submissions per minute (0 = off) |
| `APPROVAL_TTL_SECONDS` | `900` | How long a pending approval stays actionable |
| `COMMAND_TIMEOUT_SECONDS` | `60` | Timeout passed to the executor |

## Endpoints

All paths are under `/api`. Every response has an `X-Request-ID` header.

| Method & path | Purpose |
|---|---|
| `POST /projects` `{name}` | Create a project (+ session + workspace folder). `201` |
| `GET /projects`, `GET /projects/{id}` | Project list / one project |
| `POST /chat` `{project_id, message}` | Send a request to the agent → project state + `message` |
| `GET /tasks?project_id=` | Project state: `status`, `tasks`, `pending_action` |
| `POST /actions/{id}/approve` `{command_hash?}` | Approve a pending command and continue the plan |
| `POST /actions/{id}/reject` `{command_hash?}` | Reject it; the task and the rest of the plan are cancelled |
| `GET /logs?project_id=&after_id=0&limit=100` | Commands run (or awaiting approval), oldest first |
| `GET /files?project_id=` | Files in the workspace |
| `GET /files/content?project_id=&path=` | One UTF-8 text file |
| `GET /preview?project_id=` | `{status: "unavailable" \| "static", url}` |
| `GET /preview/{project_id}/{path}` | The generated site (sandboxed, see below) |
| `GET /health` | Liveness |

`POST /projects` and `POST /chat` accept an optional `Idempotency-Key` header (1–128 chars of
`A-Za-z0-9._:-`). Same key + same body returns the original response with
`Idempotent-Replay: true`; same key + different body is `409 idempotency_conflict`.
The frontend should send a fresh UUID per user submission and reuse it on retry.

### Project state (returned by `GET /tasks`, `POST /chat`, and the approve/reject calls)

```json
{
  "project_id": 1,
  "status": "waiting_for_approval",
  "tasks": [{"id": 1, "project_id": 1, "type": "step", "status": "waiting_for_approval", "prompt": "install dependencies"}],
  "pending_action": {
    "id": 7, "task_id": 1, "command": "npm install", "reason": "needed for the build",
    "command_hash": "<sha256>", "created_at": "...", "expires_at": "..."
  }
}
```

- `status`: `idle | running | waiting_for_approval | completed | failed | cancelled`
- task `status`: `pending | running | waiting_for_approval | succeeded | failed | skipped | cancelled`
- `POST /chat` and the approve/reject calls add a human-readable `message`; the latter also
  `action_id` and `decision`.
- `tasks` is always the **full** task list of the project, so the frontend can replace its state.

### Errors

```json
{"error": {"code": "pending_action_exists", "message": "...", "retryable": false,
           "project_id": 1, "request_id": "...", "details": [{"field": "body.message", "message": "...", "type": "..."}]}}
```

| Status | Meaning | Codes |
|---|---|---|
| 422 | Invalid input | `validation_error`, `idempotency_key_required` |
| 403 | Path outside the workspace or hidden | `path_not_allowed` |
| 404 | Not found | `project_not_found`, `action_not_found`, `file_not_found`, `not_found` |
| 409 | Conflict | `pending_action_exists`, `project_busy` (retryable), `approval_mismatch`, `action_expired`, `action_already_decided`, `idempotency_conflict`, `idempotency_in_progress` (retryable) |
| 413 / 415 | Too large / not text | `request_too_large`, `file_too_large`, `unsupported_file_type` |
| 429 | Throttled (`Retry-After` set) | `rate_limited` (retryable) |
| 502 | The agent failed | `agent_error` (retryable), `agent_empty_plan` |
| 500 | Bug on our side | `internal_error` (details only in the server log) |

## How a request flows

```
POST /chat → agent.plan(message) → one task per step
  for each task:  action = agent.next_action(task, last_result)
    none            → task succeeded (or failed, if the last command failed)
    allowlisted     → executor.run_command(...) → result logged → back to the agent
    not allowlisted → saved as "pending_approval", task waits, request returns
                      (or the agent set requires_approval)
POST /actions/{id}/approve → executor.run_command(..., approved=True) → agent continues → rest of plan
```

Bounds (defaults in `config.py`): a plan has ≤ 20 steps; a task takes ≤ 8 actions and tolerates
2 failed commands beyond the first, then fails and the remaining steps are `skipped`. One
request per project at a time (`project_busy`). A pending approval blocks new chat requests
for that project until it is approved, rejected or expires.

Approval is bound to one exact command in one project: the decision is applied to the stored
command, never to anything the client sends. `command_hash` lets the UI prove the human saw
this exact command; a mismatch is refused. Approving twice never runs the command twice.

## Shared contracts

Python models in `backend/api/schemas/contracts.py`. Other modules may return plain dicts or
any object with these attribute names; they need not import this package.

| Direction | Model | Fields |
|---|---|---|
| Agent → API | `AgentAction` | `type` (`"run_command"` only), `command` (single line, ≤ 1000 chars), `requires_approval` (default false), `reason` (optional, ≤ 500) |
| API → Executor | `ExecutionRequest` | `command`, `working_directory` (the project workspace), `timeout` (seconds), `requires_approval` |
| Executor → API | `ExecutionResult` | `success`, `stdout`, `stderr`, `duration_ms`, `retry_count` |
| Frontend → API | `ChatRequest` | `project_id`, `message` (≤ 4000 chars) |
| API → Frontend | project state above | `message`, `tasks`, `pending_action`, `status` |

## What the API needs from each module

Signatures are in `backend/api/services/ports.py` (typed `Protocol`s). Please confirm or
counter-propose in the PR that adds your module.

**Koray — storage.** Methods: `create_project`, `get_project`, `list_projects`, `create_session`,
`create_task(project_id, task_type, prompt)`, `get_task`, `list_tasks`, `update_task_status`,
`save_execution`, `get_execution`, `update_execution`, `list_executions(project_id, after_id,
limit, task_id)`, `get_pending_execution`. Additions to the sketched schema:
`executions.created_at` (approval expiry) and `executions.reason` (why approval is needed);
execution status values `pending_approval | succeeded | failed | rejected | expired`; task status
values as above. Also needed later: a `messages` table (the spec requires conversation history
with a sequence number; the entity list has none). `datetime`s may be naive; the API treats them as UTC.

**Sam — execution.** `is_allowed(command) -> bool` and `run_command(request, approved=False)`.
Please note:
- The API rejects commands containing a newline or NUL, nothing more. Allowlist matching must
  compare whole commands or parsed tokens — `npm test; rm -rf /` must not match `npm test`
  (so no prefix matching, and `&&`, `;`, `|`, `$()`, backticks, redirects need explicit handling).
- Refuse commands that are neither allowed nor `approved` even though the API checks first.
- Enforce `timeout` and confine `working_directory`; return bounded output.
- `requires_approval=True` in a request means a human decision was needed for it; `approved`
  says it was given.

**Bejan — agent.** `plan(user_request) -> list[str]` and `next_action(task, last_result) ->
AgentAction | None`. Only `run_command` actions exist; file writes (`apply_patch`) are not in the
shared contracts yet and need agreeing with Sam. Treat `last_result.stdout/stderr` as untrusted
data: command output can contain text that tries to instruct the model.

**Rana — frontend.** Base URL `http://localhost:8000/api`. Poll `GET /tasks` (and `GET /logs?after_id=`)
while `status` is `running`; there is no push channel yet. Show the approval card from
`pending_action` and send its `command_hash` back. Embed the preview as
`<iframe sandbox="allow-scripts" src="...">`. Send an `Idempotency-Key` on POSTs. Handle the
error envelope, and `409 project_busy` / `429` by retrying after a moment.

## Security notes

- Generated code is untrusted. Preview responses carry `Content-Security-Policy: sandbox allow-scripts`
  so scripts in them cannot read API responses; the iframe sandbox attribute is the second layer.
- File viewer and preview serve only files inside `workspaces/project_<id>/`: `..`, absolute and
  drive paths, hidden files (`.env`, `.git`), `node_modules`, and symlinks/junctions that resolve
  outside are refused. Logs are truncated to 10 000 characters per stream.
- Errors never contain stack traces, internal messages or echoed input; those go to the server log.
- No authentication in v1 (out of MVP scope). `get_owner()` in `dependencies.py` is the single
  place to add it; clients cannot send an owner (`owner_id` is rejected as an unknown field).

## Checklist against the Multiple Agent specification

Applied where it concerns the API layer:

| Spec point | Where |
|---|---|
| Typed payloads, unknown fields forbidden, bounded strings, validated ids (§3) | `schemas/` (`extra="forbid"`) |
| Stable error envelope; 422 / 403 / 409 / 429; no stack traces or secrets (§7) | `errors.py` |
| `Idempotency-Key`: replay for identical request, 409 for a different one (§7) | `dependencies.submit`, `services/guards.py` |
| Submission throttling (§7) | `RateLimiter` |
| Identity set by the server, never by the client (§7) | `get_owner` |
| Permissions enforced in Python, not in a prompt (§6) | command gate in `services/runner.py` |
| Approval binds the exact action, expires, and cannot come from the model (§6) | `services/approvals.py`, `actions.py` |
| File reads limited to approved roots incl. symlink resolution (§6) | `services/workspace.py` |
| Tool output is data; do not expose unrestricted raw output (§6, §7) | log truncation |
| Bounded loops; explicit outcomes, nothing silently dropped (§1, §4) | `runner.py` caps, `failed/skipped/cancelled` |
| Serialize state changes per project (§4) | `TaskRunner.exclusive` |
| Request id on every response and error (§10) | `app.py` |

Not done yet — decide before relying on it:

- **Event stream.** The spec uses server-sent events with `Last-Event-ID` and heartbeats. v1 polls
  `GET /logs?after_id=`; log ids are already monotonic so SSE can be added without changing them.
- **Synchronous chat.** `POST /chat` returns when the plan stops or waits. With a real LLM, run
  `run_pending` in a background task and return `202` right after the tasks are stored (spec §10);
  the response shape and polling endpoints already support that.
- **Persistence of guards.** Idempotency keys and rate-limit counters live in memory (single
  process); approvals are as durable as storage. A multi-worker deployment needs a shared store.
- **Cancel.** The spec has a cancel endpoint; the PDF's endpoint list does not. Add
  `POST /api/projects/{id}/cancel` if the team wants it.
- **Budgets.** Per-call token/cost reservation belongs to the model gateway in Bejan's module;
  the API only caps steps and actions.
- **Body size.** Enforced from the `Content-Length` header only; put a limit on the proxy too.
- **Python version.** The spec asks for 3.11+; the code runs on 3.9+ (`typing` generics, no `match`).

# Sprint 3 module contracts (published by Oğuz, branch `integration/sprint-3`)

Goal: one application that turns a chat request into a real static website, previewable
through the existing API, with no simulated success anywhere in the normal path.

```
POST /api/chat
   -> Agent.plan(request)                       list of step descriptions  (one task each)
   -> for each task: Agent.next_action(task, last_result)
        -> write_file action                    data only; the agent writes nothing
   -> API validates the action (AgentAction)
   -> Executor.write_file(WriteFileRequest)     the only code that touches the filesystem
        -> writes atomically, reads back, compares   -> ExecutionResult
   -> API stores the ExecutionResult as the execution record; the task becomes
      succeeded/failed from that result
   -> GET /api/files, /api/preview, /api/logs show what actually happened
```

Nothing reports success before the executor has finished and verified the write.

## Who owns what

| Piece | Owner | Port / location |
|---|---|---|
| Agent (planning, actions) | Bejan | `AgentPort` in `backend/api/services/ports.py` |
| Site generator | Rana | `SiteGeneratorPort` (same file) |
| Executor (file writes) | Oğuz (`backend/api/services/executor.py`) | `ExecutorPort.write_file` |
| Storage, idempotency | Koray | `StoragePort`, `backend/storage/` |
| Frontend | Sam | existing REST API, unchanged |
| Wiring, runner, tests | Oğuz | `backend/api/services/container.py`, `runner.py` |

`backend/integration/` holds working stand-ins (`SiteAgent`, `ReferenceSiteGenerator`) so the
whole flow runs today. They are replaced, not edited, by the owners' modules:

```
AGENT_IMPL=backend.agent.orchestrator:Orchestrator   # Bejan, when ready (called with no arguments)
GENERATOR_IMPL=backend.generator:WebsiteGenerator    # Rana, used by the default SiteAgent
```

Rana's generator lives in `backend/generator/` (see its README). It accepts the spec below
unchanged and adds optional fields (`tagline`, `footer`, section `kind`/`items`/`cta`/`id`,
`theme.accent`/`theme.font`, `options.include_script`); `validate(files, spec)` may also be
called with the spec to check the file set against it.

## Agent -> API: actions (`AgentAction`)

`next_action(task, last_result)` returns `None` when the task is finished, else one of:

```json
{"type": "run_command", "command": "npm test", "requires_approval": false, "reason": "optional"}
{"type": "write_file",  "path": "index.html",  "content": "<!doctype html>...", "reason": "optional"}
```

- Exactly the fields of the chosen type; anything else is rejected (`extra=forbid`).
- `write_file` never sets `requires_approval`: its content is not kept on a pending record,
  so the executor's bounds are the control instead of a human decision.
- `last_result` is the `ExecutionResult` of the previous action on this task (`None` first).
  Return `None` after seeing a failed result and the task fails; it is never marked succeeded.
- Raising from `plan` or `next_action` fails the request or task. Messages are not shown to
  the browser, so do not rely on them reaching the user.
- The agent keeps no state between requests or projects. A step prompt must be enough to
  recompute the action (the default `SiteAgent` encodes file path, site type and title).

## API -> Executor

```python
write_file(request: WriteFileRequest) -> ExecutionResult
# WriteFileRequest: working_directory (the project's workspace), path (relative), content
# ExecutionResult:  success, stdout, stderr, duration_ms, retry_count
```

The shipped `WorkspaceExecutor` enforces, and any replacement must keep:

- path stays inside `workspace_root/project_<id>/` (no `..`, absolute or drive paths,
  hidden names, or symlinks that leave the workspace);
- allowed suffixes only: `.html .css .js .json .svg .txt .md .xml .webmanifest`;
- size <= `max_file_bytes`; file count <= `max_listed_files`;
- atomic write, then read-back comparison; `success=True` only if the bytes match;
- `run_command` is closed this sprint: `is_allowed` is always false and `run_command` fails,
  even after human approval. Approval, expiry and rejection flows are unchanged.

## Generator (Rana) -> `SiteGeneratorPort`

```python
generate(spec: dict) -> dict[str, str]   # relative path -> text; deterministic, no I/O
validate(files: dict[str, str]) -> list[str]   # problems; empty list = valid
```

Specification (compact dict): `site_type` (`blog|portfolio|landing`), `title`, `pages`
(`slug`, `title`, `sections[{heading, body}]`), `theme.primary` (`#rrggbb`). A valid result
has `index.html` and `style.css`, no empty files, navigation on each page, a viewport meta tag,
and every relative `href`/`src` pointing at a generated file. The agent refuses to plan
a site whose `validate` returns problems.

## Storage and API surface

Unchanged: projects, chat, tasks, actions (approve/reject), logs, files, preview. Executions
for file writes appear in `/api/logs` with `command` = `write_file <path>`, `stdout` =
`wrote <path> (<bytes> bytes, sha256 <12 hex>)`. Task statuses are
`pending|running|waiting_for_approval|succeeded|failed|skipped|cancelled`; the project status
is `idle|running|waiting_for_approval|completed|failed|cancelled`.

## Release checks (run before merging into `main`)

1. `pytest` (the full suite) passes.
2. End-to-end: create project, `POST /api/chat` "Create a blog", `GET /api/files` lists
   the site, `GET /api/preview` is `static`, the preview URL serves the page.
3. Restart the backend: tasks, files and preview are unchanged.
4. No `MockExecutor` in the default build path (`build_services()`).

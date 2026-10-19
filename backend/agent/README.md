# Agent module - Sprint 1 (Bejan)

This module demonstrates the connection between user requests and task records.
It uses only the Python standard library and needs no model credentials.

```python
from backend.agent import Orchestrator

agent = Orchestrator()
assert agent.plan("Create a blog") == ["create project", "create index.html"]
assert agent.next_action({"prompt": "create index.html"}, None) is None
```

`planner.py` returns the same two steps for every non-empty string request.
`orchestrator.py` implements the API's `AgentPort` methods. Returning `None`
from `next_action` means there is no command to perform for this fake step.
The API creates the records and marks these simulated steps succeeded. This
does not mean an actual project or HTML file was generated.

`action_schema.py` describes future command proposals using the API's field
names; it is a typing contract, not runtime validation or permission enforcement.
`prompts.py` and `state.py` document extension points for later sprints.
There are no shell calls, file writes, database access, model calls, or automatic
repairs in this agent. The API runner remains responsible for task transitions.

## Run the connected demo

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

Open `http://localhost:8000/docs` and:

1. Call `POST /api/projects` with `{"name": "Blog"}` and copy the returned ID.
2. Call `POST /api/chat` with `{"project_id": 1, "message": "Create a blog"}`
   using that ID.
3. Call `GET /api/tasks?project_id=1` using that ID. The two task descriptions
   are available for the frontend to display, with status `succeeded`.

The default service container now selects this agent; custom agents can still
be injected through `build_services(agent=...)`.

Run verification with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Integration limits and later work

The current API stores tasks in memory. Koray's SQLite branch still needs
alignment with `StoragePort` (package location, IDs, method signatures,
sessions, and execution approval fields). Rana's frontend is also separate.
This branch verifies API -> agent -> in-memory storage -> task response;
the full frontend -> SQLite demonstration is a team integration milestone.

The October 19 decision summary updates the October 13 options document.
Future work includes real planning, context selection, code edits, execution
feedback and at most two automatic repairs, plus final user review and Git/SQLite
rollback. Final change acceptance is separate from permission for an individual
command. None of those later workflows are simulated as implemented here.

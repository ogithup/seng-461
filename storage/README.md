# Storage Layer Guide (`backend.storage`)

The `backend.storage` package manages SQLite persistence for projects, tasks, and command execution results. Other modules (`backend/api`, `backend/agent`, `backend/execution`) must call the public functions exposed by `backend.storage` rather than writing raw SQL queries.

---

## 1. Quick Start

```python
from backend import storage

# Optional: initialize schema explicitly at startup (also auto-runs on calls)
storage.init_db()

# 1. Create a project
project = storage.create_project("Personal Blog")
# -> {'id': '...', 'name': 'Personal Blog', 'created_at': '2026-10-16T17:25:00.123456Z'}

# 2. Create a task linked to the project
task = storage.create_task(project["id"], "Generate homepage layout")
# -> {'id': '...', 'project_id': '...', 'description': 'Generate homepage layout', 'status': 'pending', 'created_at': '...'}

# 3. Query tasks (all tasks, or filtered by project_id / status)
all_tasks = storage.get_tasks()
project_tasks = storage.get_tasks(project_id=project["id"])

# 4. Save an execution result (matches Sam's execution contract)
execution = storage.save_execution(
    {
        "success": True,
        "stdout": "Created index.html",
        "stderr": "",
        "duration_ms": 125,
        "retry_count": 0,
    },
    task_id=task["id"],
)
```

---

## 2. Database Path Resolution

By default, the SQLite file is stored at `backend/storage/ai_website_agent.db` (anchored to the module's directory, never dependent on the process current working directory).

You can override the database location in three ways:
1. Per-call argument: `storage.create_project("Demo", db_path="/tmp/custom.db")`
2. Module-wide configuration: `storage.configure_database("/tmp/custom.db")`
3. Environment variable: `AI_WEBSITE_AGENT_DB_PATH=/tmp/custom.db`
4. Scoped service instance: `svc = storage.StorageService("/tmp/custom.db")`

---

## 3. Public API Reference

### `init_db(db_path=None) -> Path`
Idempotently creates the `projects`, `tasks`, and `executions` tables and enables foreign keys. Returns the resolved `Path`.

### `create_project(name, *, project_id=None, created_at=None, db_path=None) -> dict`
- **Required**: `name: str` (non-empty)
- **Returns**: `{"id": str, "name": str, "created_at": str}`
- **Raises**: `ValidationError`, `StorageError`

### `get_project(project_id, *, db_path=None) -> dict | None`
- **Returns**: Project `dict` or `None` if not found.

### `get_projects(*, db_path=None) -> list[dict]`
- **Returns**: List of all project `dict`s ordered by `created_at` ascending.

### `create_task(project_id, description, *, status="pending", task_id=None, created_at=None, db_path=None) -> dict`
- **Required**: `project_id: str`, `description: str`
- **Returns**: `{"id": str, "project_id": str, "description": str, "status": str, "created_at": str}`
- **Raises**: `NotFoundError` (if `project_id` does not exist), `ValidationError`, `StorageError`

### `get_task(task_id, *, db_path=None) -> dict | None`
- **Returns**: Task `dict` or `None` if not found.

### `get_tasks(project_id=None, *, status=None, db_path=None) -> list[dict]`
- **Optional filters**: `project_id: str | None`, `status: str | None`
- **Returns**: List of matching task `dict`s ordered by `created_at` ascending.

### `update_task_status(task_id, status, *, db_path=None) -> dict`
- **Required**: `task_id: str`, `status: str`
- **Returns**: Updated task `dict`.
- **Raises**: `NotFoundError` (if `task_id` does not exist), `ValidationError`, `StorageError`

### `save_execution(result=None, *, task_id=None, success=None, stdout=None, stderr=None, duration_ms=None, retry_count=None, execution_id=None, created_at=None, db_path=None) -> dict`
- Accepts either a dictionary `result` with the shared contract (`success`, `stdout`, `stderr`, `duration_ms`, `retry_count`) or keyword arguments.
- **Returns**:
  ```python
  {
      "id": str,
      "task_id": str | None,
      "success": bool,
      "stdout": str,
      "stderr": str,
      "duration_ms": int,
      "retry_count": int,
      "created_at": str,
  }
  ```
- **Raises**: `NotFoundError` (if `task_id` is provided but does not exist), `ValidationError`, `StorageError`

### `get_execution(execution_id, *, db_path=None) -> dict | None`
- **Returns**: Execution `dict` or `None` if not found.

### `get_executions(task_id=None, *, db_path=None) -> list[dict]`
- **Optional filter**: `task_id: str | None`
- **Returns**: List of execution `dict`s ordered by `created_at` ascending.

---

## 4. Exceptions

All exceptions inherit from `storage.StorageError`:
- `storage.ValidationError(StorageError, ValueError)`: Invalid types, empty strings, negative integers, or duplicate primary keys.
- `storage.NotFoundError(StorageError, LookupError)`: Missing referenced `project_id` or `task_id` (foreign-key violation) or updating a nonexistent task.

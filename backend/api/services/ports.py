"""What the API expects from the other modules.

These are the integration seams. Bejan (agent), Sam (execution) and Koray (storage)
implement them; until they land, `mocks.py` stands in. Return values may be dicts or
objects (ORM rows, dataclasses): the API reads fields by name, so no module has to
import another module's classes.

Record fields the API reads:
  project    id, name, created_at
  session    id, project_id, started_at
  task       id, project_id, type, status, prompt
  execution  id, task_id, command, status, stdout, stderr, retry_count, duration_ms,
             reason, created_at
"""
from typing import Any, List, Optional, Protocol

from backend.api.schemas.contracts import ExecutionRequest, WriteFileRequest
from backend.api.schemas.tasks import TaskOut


class StoragePort(Protocol):
    """Koray. The API never writes SQL; it only calls these."""

    def create_project(self, name: str) -> Any: ...

    def get_project(self, project_id: int) -> Optional[Any]: ...

    def list_projects(self) -> List[Any]: ...

    def create_session(self, project_id: int) -> Any: ...

    def create_task(self, project_id: int, task_type: str, prompt: str) -> Any:
        """New tasks start with status "pending"."""

    def get_task(self, task_id: int) -> Optional[Any]: ...

    def list_tasks(self, project_id: int) -> List[Any]:
        """Oldest first."""

    def update_task_status(self, task_id: int, status: str) -> Any: ...

    def save_execution(
        self,
        task_id: int,
        command: str,
        status: str,
        stdout: str = "",
        stderr: str = "",
        retry_count: int = 0,
        duration_ms: int = 0,
        reason: Optional[str] = None,
    ) -> Any:
        """Stamps `created_at`."""

    def get_execution(self, execution_id: int) -> Optional[Any]: ...

    def update_execution(
        self,
        execution_id: int,
        status: str,
        stdout: Optional[str] = None,
        stderr: Optional[str] = None,
        retry_count: Optional[int] = None,
        duration_ms: Optional[int] = None,
    ) -> Any:
        """Fields passed as None are left unchanged."""

    def list_executions(
        self,
        project_id: int,
        after_id: int = 0,
        limit: int = 100,
        task_id: Optional[int] = None,
    ) -> List[Any]:
        """Executions of the project's tasks with id > after_id, oldest first."""

    def get_pending_execution(self, project_id: int) -> Optional[Any]:
        """The project's execution with status "pending_approval", if any."""


class AgentPort(Protocol):
    """Bejan. Produces plans and actions; never runs a command."""

    def plan(self, user_request: str) -> List[str]:
        """Short, ordered step descriptions for the request."""

    def next_action(self, task: TaskOut, last_result: Optional[Any]) -> Optional[Any]:
        """The next action for `task`, or None when the task is finished.

        `last_result` is the ExecutionResult of the previous action on this task
        (None on the first call). Actions follow `AgentAction`.
        """


class ExecutorPort(Protocol):
    """Sam. Runs commands inside the project workspace and decides what is allowed."""

    def is_allowed(self, command: str) -> bool:
        """True if the command is on the pre-approved allowlist (runs without asking)."""

    def run_command(self, request: ExecutionRequest, approved: bool = False) -> Any:
        """Run it and return an ExecutionResult-shaped object.

        `approved=True` means a human approved this exact command; an executor must
        still refuse commands that are not allowed and not approved.
        """

    def write_file(self, request: WriteFileRequest) -> Any:
        """Write `request.path` under `request.working_directory` and return an
        ExecutionResult-shaped object.

        Optional for executors that only run commands. `success=True` must mean the
        file exists on disk with exactly this content: verify before reporting.
        """


class SiteGeneratorPort(Protocol):
    """Rana. Turns a validated website specification into static files. No model, no I/O."""

    def generate(self, spec: Any) -> Any:
        """Return {relative path: text content} for the whole site."""

    def validate(self, files: Any) -> List[str]:
        """Problems found in a generated file set (empty list = valid)."""

"""Stand-ins for the other modules so the API runs end to end in Sprint 1.

Nothing here touches a database, calls a model, or runs a shell command.
"""
import itertools
import threading
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from backend.api.schemas.contracts import ExecutionRequest, ExecutionResult
from backend.api.schemas.tasks import TaskOut


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ProjectRecord:
    id: int
    name: str
    created_at: datetime


@dataclass
class SessionRecord:
    id: int
    project_id: int
    started_at: datetime


@dataclass
class TaskRecord:
    id: int
    project_id: int
    type: str
    status: str
    prompt: str


@dataclass
class ExecutionRecord:
    id: int
    task_id: int
    command: str
    status: str
    stdout: str
    stderr: str
    retry_count: int
    duration_ms: int
    reason: Optional[str]
    created_at: datetime


class InMemoryStorage:
    """Koray's persistence layer, in a dict. Returns copies, like a database would."""

    def __init__(self, clock: Callable[[], datetime] = _utcnow):
        self._clock = clock
        self._lock = threading.RLock()
        self._ids = {kind: itertools.count(1) for kind in ("project", "session", "task", "execution")}
        self._projects: Dict[int, ProjectRecord] = {}
        self._sessions: Dict[int, SessionRecord] = {}
        self._tasks: Dict[int, TaskRecord] = {}
        self._executions: Dict[int, ExecutionRecord] = {}

    def create_project(self, name: str) -> ProjectRecord:
        with self._lock:
            record = ProjectRecord(next(self._ids["project"]), name, self._clock())
            self._projects[record.id] = record
            return replace(record)

    def get_project(self, project_id: int) -> Optional[ProjectRecord]:
        with self._lock:
            record = self._projects.get(project_id)
            return replace(record) if record else None

    def list_projects(self) -> List[ProjectRecord]:
        with self._lock:
            return [replace(p) for p in sorted(self._projects.values(), key=lambda p: p.id)]

    def create_session(self, project_id: int) -> SessionRecord:
        with self._lock:
            record = SessionRecord(next(self._ids["session"]), project_id, self._clock())
            self._sessions[record.id] = record
            return replace(record)

    def create_task(self, project_id: int, task_type: str, prompt: str) -> TaskRecord:
        with self._lock:
            record = TaskRecord(next(self._ids["task"]), project_id, task_type, "pending", prompt)
            self._tasks[record.id] = record
            return replace(record)

    def get_task(self, task_id: int) -> Optional[TaskRecord]:
        with self._lock:
            record = self._tasks.get(task_id)
            return replace(record) if record else None

    def list_tasks(self, project_id: int) -> List[TaskRecord]:
        with self._lock:
            tasks = [t for t in self._tasks.values() if t.project_id == project_id]
            return [replace(t) for t in sorted(tasks, key=lambda t: t.id)]

    def update_task_status(self, task_id: int, status: str) -> TaskRecord:
        with self._lock:
            self._tasks[task_id].status = str(getattr(status, "value", status))
            return replace(self._tasks[task_id])

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
    ) -> ExecutionRecord:
        with self._lock:
            record = ExecutionRecord(
                next(self._ids["execution"]),
                task_id,
                command,
                str(getattr(status, "value", status)),
                stdout,
                stderr,
                retry_count,
                duration_ms,
                reason,
                self._clock(),
            )
            self._executions[record.id] = record
            return replace(record)

    def get_execution(self, execution_id: int) -> Optional[ExecutionRecord]:
        with self._lock:
            record = self._executions.get(execution_id)
            return replace(record) if record else None

    def update_execution(
        self,
        execution_id: int,
        status: str,
        stdout: Optional[str] = None,
        stderr: Optional[str] = None,
        retry_count: Optional[int] = None,
        duration_ms: Optional[int] = None,
    ) -> ExecutionRecord:
        with self._lock:
            record = self._executions[execution_id]
            record.status = str(getattr(status, "value", status))
            if stdout is not None:
                record.stdout = stdout
            if stderr is not None:
                record.stderr = stderr
            if retry_count is not None:
                record.retry_count = retry_count
            if duration_ms is not None:
                record.duration_ms = duration_ms
            return replace(record)

    def list_executions(
        self,
        project_id: int,
        after_id: int = 0,
        limit: int = 100,
        task_id: Optional[int] = None,
    ) -> List[ExecutionRecord]:
        with self._lock:
            task_ids = {t.id for t in self._tasks.values() if t.project_id == project_id}
            rows = [
                e
                for e in self._executions.values()
                if e.task_id in task_ids
                and e.id > after_id
                and (task_id is None or e.task_id == task_id)
            ]
            rows.sort(key=lambda e: e.id)
            return [replace(e) for e in rows[:limit]]

    def get_pending_execution(self, project_id: int) -> Optional[ExecutionRecord]:
        with self._lock:
            task_ids = {t.id for t in self._tasks.values() if t.project_id == project_id}
            pending = [
                e
                for e in self._executions.values()
                if e.task_id in task_ids and e.status == "pending_approval"
            ]
            return replace(max(pending, key=lambda e: e.id)) if pending else None


class MockAgent:
    """Bejan's agent for Sprint 1: a fixed plan and no commands."""

    def plan(self, user_request: str) -> List[str]:
        return ["create project", "create index.html"]

    def next_action(self, task: TaskOut, last_result: Optional[Any]) -> Optional[Any]:
        return None


class MockExecutor:
    """Sam's executor for Sprint 1. Pretends to run commands; never starts a process."""

    ALLOWED = frozenset({"echo hello", "npm test", "npm run build", "npm run lint"})

    def is_allowed(self, command: str) -> bool:
        return command in self.ALLOWED

    def run_command(self, request: ExecutionRequest, approved: bool = False) -> ExecutionResult:
        if not approved and not self.is_allowed(request.command):
            return ExecutionResult(success=False, stderr="command requires approval")
        return ExecutionResult(
            success=True, stdout="[mock] would run: %s" % request.command, duration_ms=1
        )

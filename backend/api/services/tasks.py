from typing import List, Optional, Tuple

from backend.api.config import Settings
from backend.api.schemas.enums import RunStatus, TaskStatus
from backend.api.schemas.logs import LogEntry, LogsResponse
from backend.api.schemas.tasks import ExecutionOut, PendingAction, ProjectState, TaskOut
from backend.api.services.approvals import ApprovalGate
from backend.api.services.ports import StoragePort
from backend.api.services.projects import ProjectService

_LAST_TASK_TO_STATUS = {
    TaskStatus.SUCCEEDED: RunStatus.COMPLETED,
    TaskStatus.FAILED: RunStatus.FAILED,
    TaskStatus.SKIPPED: RunStatus.FAILED,
    TaskStatus.CANCELLED: RunStatus.CANCELLED,
}


def compute_status(tasks: List[TaskOut], pending: Optional[PendingAction]) -> RunStatus:
    if pending is not None:
        return RunStatus.WAITING_FOR_APPROVAL
    if not tasks:
        return RunStatus.IDLE
    if any(t.status in (TaskStatus.RUNNING, TaskStatus.PENDING) for t in tasks):
        return RunStatus.RUNNING
    return _LAST_TASK_TO_STATUS.get(tasks[-1].status, RunStatus.RUNNING)


def describe(state: ProjectState) -> str:
    """One plain sentence the chat UI can show under the user's message."""
    if state.pending_action is not None:
        return "I need your approval to run: %s" % state.pending_action.command
    counts = {}
    for task in state.tasks:
        counts[task.status] = counts.get(task.status, 0) + 1
    succeeded = counts.get(TaskStatus.SUCCEEDED, 0)
    if state.status == RunStatus.COMPLETED:
        return "Finished %d task(s)." % succeeded
    if state.status == RunStatus.FAILED:
        return "Stopped after a failure: %d task(s) done, %d not run." % (
            succeeded,
            counts.get(TaskStatus.SKIPPED, 0),
        )
    if state.status == RunStatus.CANCELLED:
        return "Cancelled: %d task(s) done before it stopped." % succeeded
    return "Working on it."


class TaskService:
    """Read side: task lists, project status and the command log."""

    def __init__(
        self,
        storage: StoragePort,
        projects: ProjectService,
        gate: ApprovalGate,
        settings: Settings,
    ):
        self._storage = storage
        self._projects = projects
        self._gate = gate
        self._settings = settings

    def state(self, project_id: int) -> ProjectState:
        self._projects.require(project_id)
        pending = self._gate.get_pending(project_id)  # may expire a stale request first
        tasks = [TaskOut.model_validate(t) for t in self._storage.list_tasks(project_id)]
        return ProjectState(
            project_id=project_id,
            status=compute_status(tasks, pending),
            tasks=tasks,
            pending_action=pending,
        )

    def logs(self, project_id: int, after_id: int, limit: int) -> LogsResponse:
        self._projects.require(project_id)
        rows = self._storage.list_executions(project_id, after_id=after_id, limit=limit)
        entries = [self._entry(ExecutionOut.model_validate(r)) for r in rows]
        return LogsResponse(
            project_id=project_id,
            entries=entries,
            next_after_id=entries[-1].id if entries else after_id,
        )

    def _entry(self, e: ExecutionOut) -> LogEntry:
        stdout, cut_out = _clip(e.stdout, self._settings.max_log_output_chars)
        stderr, cut_err = _clip(e.stderr, self._settings.max_log_output_chars)
        return LogEntry(
            id=e.id,
            task_id=e.task_id,
            command=e.command,
            status=e.status,
            stdout=stdout,
            stderr=stderr,
            output_truncated=cut_out or cut_err,
            retry_count=e.retry_count,
            duration_ms=e.duration_ms,
            reason=e.reason,
            created_at=e.created_at,
        )


def _clip(text: str, limit: int) -> Tuple[str, bool]:
    return (text[:limit], True) if len(text) > limit else (text, False)

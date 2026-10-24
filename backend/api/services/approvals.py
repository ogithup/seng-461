"""Human approval of commands that are not on the allowlist.

A pending approval is an execution row with status "pending_approval". It binds one
exact command in one project (`command_hash`), and it expires: a pending approval that
nobody answered must not stay actionable forever.
"""
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from backend.api.config import Settings
from backend.api.schemas.enums import OPEN_TASK_STATUSES, ExecutionStatus, TaskStatus
from backend.api.schemas.tasks import ExecutionOut, PendingAction, TaskOut
from backend.api.services.ports import StoragePort


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ApprovalGate:
    def __init__(
        self,
        storage: StoragePort,
        settings: Settings,
        clock: Optional[Callable[[], datetime]] = None,
    ):
        self._storage = storage
        self._settings = settings
        self._clock = clock or _utcnow

    @staticmethod
    def hash_command(project_id: int, command: str) -> str:
        return hashlib.sha256(("%d\n%s" % (project_id, command)).encode("utf-8")).hexdigest()

    def expires_at(self, execution: ExecutionOut) -> datetime:
        return execution.created_at + timedelta(seconds=self._settings.approval_ttl_seconds)

    def is_expired(self, execution: ExecutionOut) -> bool:
        return self._clock() >= self.expires_at(execution)

    def get_pending(self, project_id: int) -> Optional[PendingAction]:
        """The project's unanswered approval request. Expires it first if it timed out."""
        raw = self._storage.get_pending_execution(project_id)
        if raw is None:
            return None
        execution = ExecutionOut.model_validate(raw)
        if self.is_expired(execution):
            self.expire(project_id, execution)
            return None
        return PendingAction(
            id=execution.id,
            task_id=execution.task_id,
            command=execution.command,
            command_hash=self.hash_command(project_id, execution.command),
            reason=execution.reason,
            created_at=execution.created_at,
            expires_at=self.expires_at(execution),
        )

    def expire(self, project_id: int, execution: ExecutionOut) -> None:
        self._storage.update_execution(execution.id, ExecutionStatus.EXPIRED.value)
        self.cancel_open_tasks(project_id)

    def cancel_open_tasks(self, project_id: int) -> None:
        """Stop the rest of the request after a rejection or an expiry."""
        for raw in self._storage.list_tasks(project_id):
            task = TaskOut.model_validate(raw)
            if task.status in OPEN_TASK_STATUSES:
                self._storage.update_task_status(task.id, TaskStatus.CANCELLED.value)

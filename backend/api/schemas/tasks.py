from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, field_validator

from backend.api.schemas.common import OutputModel
from backend.api.schemas.enums import ExecutionStatus, RunStatus, TaskStatus


def as_utc(value: datetime) -> datetime:
    """SQLite drivers often return naive datetimes; treat those as UTC."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class TaskOut(OutputModel):
    id: int
    project_id: int
    type: str
    status: TaskStatus
    prompt: str


class ExecutionOut(OutputModel):
    id: int
    task_id: int
    command: str
    status: ExecutionStatus
    stdout: str = ""
    stderr: str = ""
    retry_count: int = 0
    duration_ms: int = 0
    reason: Optional[str] = None
    created_at: datetime

    @field_validator("stdout", "stderr", mode="before")
    @classmethod
    def _none_is_empty(cls, value):
        return "" if value is None else value

    @field_validator("created_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return as_utc(value)


class PendingAction(BaseModel):
    """A command waiting for a human decision. `id` is what /api/actions/{id}/... takes."""

    id: int
    task_id: int
    command: str
    # Echo this back on approve to prove the human saw this exact command.
    command_hash: str
    reason: Optional[str] = None
    created_at: datetime
    expires_at: datetime


class ProjectState(BaseModel):
    """What the frontend needs to redraw: status, every task, and any pending approval."""

    project_id: int
    status: RunStatus
    tasks: List[TaskOut]
    pending_action: Optional[PendingAction] = None

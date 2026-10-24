from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from backend.api.schemas.enums import ExecutionStatus


class LogEntry(BaseModel):
    """One command the system ran (or asked permission to run). `id` only ever grows."""

    id: int
    task_id: int
    command: str
    status: ExecutionStatus
    stdout: str
    stderr: str
    output_truncated: bool
    retry_count: int
    duration_ms: int
    reason: Optional[str] = None
    created_at: datetime


class LogsResponse(BaseModel):
    project_id: int
    entries: List[LogEntry]
    # Pass as `after_id` to fetch only newer entries.
    next_after_id: int

"""Public interface for the AI Website Agent SQLite storage layer."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from backend.storage.database import (
    DEFAULT_DB_PATH,
    configure_database,
    connection_scope,
    get_connection,
    init_db,
    resolve_db_path,
)
from backend.storage.models import (
    ExecutionRecord,
    NotFoundError,
    ProjectRecord,
    StorageError,
    TaskRecord,
    ValidationError,
)
from backend.storage.repositories import (
    create_project,
    create_task,
    get_execution,
    get_executions,
    get_project,
    get_projects,
    get_task,
    get_tasks,
    save_execution,
    update_task_status,
)


class StorageService:
    """Convenience service bound to a specific SQLite database path."""

    def __init__(self, db_path: Path | str | None = None, *, auto_init: bool = True) -> None:
        self.db_path = resolve_db_path(db_path)
        if auto_init:
            init_db(self.db_path)

    def init_db(self) -> Path:
        return init_db(self.db_path)

    def create_project(
        self,
        name: str,
        *,
        project_id: str | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        return create_project(
            name,
            project_id=project_id,
            created_at=created_at,
            db_path=self.db_path,
        )

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        return get_project(project_id, db_path=self.db_path)

    def get_projects(self) -> list[dict[str, Any]]:
        return get_projects(db_path=self.db_path)

    def create_task(
        self,
        project_id: str,
        description: str,
        *,
        status: str = "pending",
        task_id: str | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        return create_task(
            project_id,
            description,
            status=status,
            task_id=task_id,
            created_at=created_at,
            db_path=self.db_path,
        )

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        return get_task(task_id, db_path=self.db_path)

    def get_tasks(
        self,
        project_id: str | None = None,
        *,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        return get_tasks(project_id, status=status, db_path=self.db_path)

    def update_task_status(self, task_id: str, status: str) -> dict[str, Any]:
        return update_task_status(task_id, status, db_path=self.db_path)

    def save_execution(
        self,
        result: Mapping[str, Any] | None = None,
        *,
        task_id: str | None = None,
        success: bool | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
        duration_ms: int | None = None,
        retry_count: int | None = None,
        execution_id: str | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        return save_execution(
            result,
            task_id=task_id,
            success=success,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            retry_count=retry_count,
            execution_id=execution_id,
            created_at=created_at,
            db_path=self.db_path,
        )

    def get_execution(self, execution_id: str) -> dict[str, Any] | None:
        return get_execution(execution_id, db_path=self.db_path)

    def get_executions(self, task_id: str | None = None) -> list[dict[str, Any]]:
        return get_executions(task_id, db_path=self.db_path)


__all__ = [
    "DEFAULT_DB_PATH",
    "StorageService",
    "StorageError",
    "ValidationError",
    "NotFoundError",
    "ProjectRecord",
    "TaskRecord",
    "ExecutionRecord",
    "configure_database",
    "resolve_db_path",
    "get_connection",
    "connection_scope",
    "init_db",
    "create_project",
    "get_project",
    "get_projects",
    "create_task",
    "get_task",
    "get_tasks",
    "update_task_status",
    "save_execution",
    "get_execution",
    "get_executions",
]

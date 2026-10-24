"""Repository for task persistence operations."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from backend.storage.database import connection_scope, init_db
from backend.storage.models import (
    NotFoundError,
    StorageError,
    TaskRecord,
    ValidationError,
    generate_id,
    utc_now_iso,
    validate_non_empty_str,
)


def create_task(
    project_id: str,
    description: str,
    *,
    status: str = "pending",
    task_id: str | None = None,
    created_at: str | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Create and persist a task linked to an existing project.

    Args:
        project_id: ID of an existing project.
        description: Non-empty task description.
        status: Initial task status (defaults to ``"pending"``).
        task_id: Optional custom unique ID (defaults to UUID4).
        created_at: Optional UTC ISO 8601 timestamp (defaults to current UTC time).
        db_path: Optional override path to the SQLite database file.

    Returns:
        Dictionary with keys ``id``, ``project_id``, ``description``, ``status``, and ``created_at``.

    Raises:
        ValidationError: If any input field is invalid or duplicate ID is provided.
        NotFoundError: If ``project_id`` does not reference an existing project.
        StorageError: On underlying database failure.
    """
    pid = validate_non_empty_str(project_id, "project_id")
    cleaned_desc = validate_non_empty_str(description, "description")
    cleaned_status = validate_non_empty_str(status, "status")
    tid = validate_non_empty_str(task_id, "task_id") if task_id is not None else generate_id()
    timestamp = validate_non_empty_str(created_at, "created_at") if created_at is not None else utc_now_iso()

    init_db(db_path)
    try:
        with connection_scope(db_path) as conn:
            conn.execute(
                """
                INSERT INTO tasks (id, project_id, description, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (tid, pid, cleaned_desc, cleaned_status, timestamp),
            )
            row = conn.execute(
                "SELECT id, project_id, description, status, created_at FROM tasks WHERE id = ?",
                (tid,),
            ).fetchone()
    except sqlite3.IntegrityError as exc:
        msg = str(exc).lower()
        if "foreign key" in msg:
            raise NotFoundError(f"Referenced project '{pid}' does not exist.") from exc
        raise ValidationError(f"Could not create task (duplicate id or constraint violation): {exc}") from exc
    except sqlite3.Error as exc:
        raise StorageError(f"Database error while creating task: {exc}") from exc

    return TaskRecord.from_row(row).to_dict()


def get_task(
    task_id: str,
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Retrieve a single task by ID, or return ``None`` if not found."""
    tid = validate_non_empty_str(task_id, "task_id")
    init_db(db_path)
    try:
        with connection_scope(db_path) as conn:
            row = conn.execute(
                "SELECT id, project_id, description, status, created_at FROM tasks WHERE id = ?",
                (tid,),
            ).fetchone()
    except sqlite3.Error as exc:
        raise StorageError(f"Database error while retrieving task: {exc}") from exc

    if row is None:
        return None
    return TaskRecord.from_row(row).to_dict()


def get_tasks(
    project_id: str | None = None,
    *,
    status: str | None = None,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve tasks, optionally filtered by ``project_id`` and/or ``status``."""
    query = "SELECT id, project_id, description, status, created_at FROM tasks"
    clauses: list[str] = []
    params: list[Any] = []

    if project_id is not None:
        clauses.append("project_id = ?")
        params.append(validate_non_empty_str(project_id, "project_id"))

    if status is not None:
        clauses.append("status = ?")
        params.append(validate_non_empty_str(status, "status"))

    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY created_at ASC, rowid ASC"

    init_db(db_path)
    try:
        with connection_scope(db_path) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
    except sqlite3.Error as exc:
        raise StorageError(f"Database error while listing tasks: {exc}") from exc

    return [TaskRecord.from_row(row).to_dict() for row in rows]


def update_task_status(
    task_id: str,
    status: str,
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Update the status of an existing task and return the updated task record.

    Raises:
        ValidationError: If ``task_id`` or ``status`` is invalid.
        NotFoundError: If the task does not exist.
    """
    tid = validate_non_empty_str(task_id, "task_id")
    cleaned_status = validate_non_empty_str(status, "status")

    init_db(db_path)
    try:
        with connection_scope(db_path) as conn:
            cursor = conn.execute(
                "UPDATE tasks SET status = ? WHERE id = ?",
                (cleaned_status, tid),
            )
            if cursor.rowcount == 0:
                raise NotFoundError(f"Task '{tid}' does not exist.")
            row = conn.execute(
                "SELECT id, project_id, description, status, created_at FROM tasks WHERE id = ?",
                (tid,),
            ).fetchone()
    except NotFoundError:
        raise
    except sqlite3.Error as exc:
        raise StorageError(f"Database error while updating task status: {exc}") from exc

    return TaskRecord.from_row(row).to_dict()

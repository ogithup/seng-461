"""Repository for project persistence operations."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from backend.storage.database import connection_scope, init_db
from backend.storage.models import (
    ProjectRecord,
    StorageError,
    ValidationError,
    generate_id,
    utc_now_iso,
    validate_non_empty_str,
)


def create_project(
    name: str,
    *,
    project_id: str | None = None,
    created_at: str | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Create and persist a project record.

    Args:
        name: Non-empty project name.
        project_id: Optional custom unique ID (defaults to UUID4).
        created_at: Optional UTC ISO 8601 timestamp (defaults to current UTC time).
        db_path: Optional override path to the SQLite database file.

    Returns:
        Dictionary with keys ``id``, ``name``, and ``created_at``.

    Raises:
        ValidationError: If input fields are invalid or duplicate ID is provided.
        StorageError: On underlying database failure.
    """
    cleaned_name = validate_non_empty_str(name, "name")
    pid = validate_non_empty_str(project_id, "project_id") if project_id is not None else generate_id()
    timestamp = validate_non_empty_str(created_at, "created_at") if created_at is not None else utc_now_iso()

    init_db(db_path)
    try:
        with connection_scope(db_path) as conn:
            conn.execute(
                "INSERT INTO projects (id, name, created_at) VALUES (?, ?, ?)",
                (pid, cleaned_name, timestamp),
            )
            row = conn.execute(
                "SELECT id, name, created_at FROM projects WHERE id = ?",
                (pid,),
            ).fetchone()
    except sqlite3.IntegrityError as exc:
        raise ValidationError(f"Could not create project (duplicate id or constraint violation): {exc}") from exc
    except sqlite3.Error as exc:
        raise StorageError(f"Database error while creating project: {exc}") from exc

    return ProjectRecord.from_row(row).to_dict()


def get_project(
    project_id: str,
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Retrieve a project by ID, or return ``None`` if not found."""
    pid = validate_non_empty_str(project_id, "project_id")
    init_db(db_path)
    try:
        with connection_scope(db_path) as conn:
            row = conn.execute(
                "SELECT id, name, created_at FROM projects WHERE id = ?",
                (pid,),
            ).fetchone()
    except sqlite3.Error as exc:
        raise StorageError(f"Database error while retrieving project: {exc}") from exc

    if row is None:
        return None
    return ProjectRecord.from_row(row).to_dict()


def get_projects(
    *,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve all projects ordered by creation time ascending."""
    init_db(db_path)
    try:
        with connection_scope(db_path) as conn:
            rows = conn.execute(
                "SELECT id, name, created_at FROM projects ORDER BY created_at ASC, rowid ASC"
            ).fetchall()
    except sqlite3.Error as exc:
        raise StorageError(f"Database error while listing projects: {exc}") from exc

    return [ProjectRecord.from_row(row).to_dict() for row in rows]

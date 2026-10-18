"""Repository for execution-result persistence operations."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Mapping

from backend.storage.database import connection_scope, init_db
from backend.storage.models import (
    ExecutionRecord,
    NotFoundError,
    StorageError,
    ValidationError,
    generate_id,
    utc_now_iso,
    validate_non_empty_str,
    validate_non_negative_int,
)


def save_execution(
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
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Persist a command execution result.

    Can be called either with a dict/mapping matching the shared execution-result
    contract (``success``, ``stdout``, ``stderr``, ``duration_ms``, ``retry_count``)
    or via explicit keyword arguments, or a combination of both (keyword arguments
    take precedence over keys in ``result``).

    Args:
        result: Optional mapping containing execution result fields.
        task_id: Optional ID of the associated task.
        success: Boolean indicating whether execution succeeded.
        stdout: Standard output captured during execution.
        stderr: Standard error captured during execution.
        duration_ms: Execution duration in milliseconds (>= 0).
        retry_count: Number of retries performed (>= 0).
        execution_id: Optional custom unique ID (defaults to UUID4).
        created_at: Optional UTC ISO 8601 timestamp (defaults to current UTC time).
        db_path: Optional override path to the SQLite database file.

    Returns:
        Dictionary containing ``id``, ``task_id``, ``success``, ``stdout``,
        ``stderr``, ``duration_ms``, ``retry_count``, and ``created_at``.

    Raises:
        ValidationError: If required fields are missing or invalid.
        NotFoundError: If ``task_id`` is provided and does not exist in ``tasks``.
        StorageError: On underlying database failure.
    """
    payload: dict[str, Any] = {}
    if result is not None:
        if not isinstance(result, Mapping):
            raise ValidationError("'result' must be a mapping/dict when provided.")
        payload.update(result)

    resolved_task_id = task_id if task_id is not None else payload.get("task_id")
    resolved_success = success if success is not None else payload.get("success")
    resolved_stdout = stdout if stdout is not None else payload.get("stdout", "")
    resolved_stderr = stderr if stderr is not None else payload.get("stderr", "")
    resolved_duration = duration_ms if duration_ms is not None else payload.get("duration_ms", 0)
    resolved_retries = retry_count if retry_count is not None else payload.get("retry_count", 0)
    resolved_exec_id = execution_id if execution_id is not None else payload.get("id")
    resolved_created_at = created_at if created_at is not None else payload.get("created_at")

    if resolved_task_id is not None:
        resolved_task_id = validate_non_empty_str(resolved_task_id, "task_id")

    if not isinstance(resolved_success, bool):
        raise ValidationError("'success' is required and must be a boolean.")

    if not isinstance(resolved_stdout, str):
        raise ValidationError("'stdout' must be a string.")
    if not isinstance(resolved_stderr, str):
        raise ValidationError("'stderr' must be a string.")

    validated_duration = validate_non_negative_int(resolved_duration, "duration_ms")
    validated_retries = validate_non_negative_int(resolved_retries, "retry_count")

    eid = (
        validate_non_empty_str(resolved_exec_id, "execution_id")
        if resolved_exec_id is not None
        else generate_id()
    )
    timestamp = (
        validate_non_empty_str(resolved_created_at, "created_at")
        if resolved_created_at is not None
        else utc_now_iso()
    )

    init_db(db_path)
    try:
        with connection_scope(db_path) as conn:
            conn.execute(
                """
                INSERT INTO executions (
                    id, task_id, success, stdout, stderr, duration_ms, retry_count, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    eid,
                    resolved_task_id,
                    1 if resolved_success else 0,
                    resolved_stdout,
                    resolved_stderr,
                    validated_duration,
                    validated_retries,
                    timestamp,
                ),
            )
            row = conn.execute(
                """
                SELECT id, task_id, success, stdout, stderr, duration_ms, retry_count, created_at
                FROM executions
                WHERE id = ?
                """,
                (eid,),
            ).fetchone()
    except sqlite3.IntegrityError as exc:
        msg = str(exc).lower()
        if "foreign key" in msg:
            raise NotFoundError(f"Referenced task '{resolved_task_id}' does not exist.") from exc
        raise ValidationError(
            f"Could not save execution (duplicate id or constraint violation): {exc}"
        ) from exc
    except sqlite3.Error as exc:
        raise StorageError(f"Database error while saving execution: {exc}") from exc

    return ExecutionRecord.from_row(row).to_dict()


def get_execution(
    execution_id: str,
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Retrieve a single execution result by ID, or return ``None`` if not found."""
    eid = validate_non_empty_str(execution_id, "execution_id")
    init_db(db_path)
    try:
        with connection_scope(db_path) as conn:
            row = conn.execute(
                """
                SELECT id, task_id, success, stdout, stderr, duration_ms, retry_count, created_at
                FROM executions
                WHERE id = ?
                """,
                (eid,),
            ).fetchone()
    except sqlite3.Error as exc:
        raise StorageError(f"Database error while retrieving execution: {exc}") from exc

    if row is None:
        return None
    return ExecutionRecord.from_row(row).to_dict()


def get_executions(
    task_id: str | None = None,
    *,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve execution records, optionally filtered by ``task_id``."""
    query = """
        SELECT id, task_id, success, stdout, stderr, duration_ms, retry_count, created_at
        FROM executions
    """
    params: list[Any] = []
    if task_id is not None:
        query += " WHERE task_id = ?"
        params.append(validate_non_empty_str(task_id, "task_id"))
    query += " ORDER BY created_at ASC, rowid ASC"

    init_db(db_path)
    try:
        with connection_scope(db_path) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
    except sqlite3.Error as exc:
        raise StorageError(f"Database error while listing executions: {exc}") from exc

    return [ExecutionRecord.from_row(row).to_dict() for row in rows]

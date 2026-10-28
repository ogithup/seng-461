"""Data models, exceptions, and serialization helpers for the storage layer."""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


class StorageError(Exception):
    """Base exception for storage-layer failures."""


class ValidationError(StorageError, ValueError):
    """Raised when input arguments fail storage validation."""


class NotFoundError(StorageError, LookupError):
    """Raised when a requested record or referenced foreign key does not exist."""


class IdempotencyError(StorageError):
    """Base exception for storage-level idempotency errors."""


class IdempotencyConflictError(IdempotencyError):
    """Raised when an idempotency key is used with conflicting payload."""


class IdempotencyInProgressError(IdempotencyError):
    """Raised when an idempotency key is currently being processed."""


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format (e.g. '2026-10-16T17:20:00Z')."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def generate_id() -> str:
    """Generate a unique string identifier using UUID4."""
    return str(uuid.uuid4())


def validate_non_empty_str(value: Any, field_name: str) -> str:
    """Validate that ``value`` is a non-empty string and return it stripped."""
    if not isinstance(value, str):
        raise ValidationError(f"'{field_name}' must be a string.")
    cleaned = value.strip()
    if not cleaned:
        raise ValidationError(f"'{field_name}' cannot be empty.")
    return cleaned


def validate_non_negative_int(value: Any, field_name: str) -> int:
    """Validate that ``value`` is a non-negative integer (excluding booleans)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"'{field_name}' must be an integer.")
    if value < 0:
        raise ValidationError(f"'{field_name}' must be >= 0.")
    return value


@dataclass(frozen=True)
class ProjectRecord:
    """Typed representation of a persisted project."""

    id: str
    name: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> ProjectRecord:
        return cls(
            id=row["id"],
            name=row["name"],
            created_at=row["created_at"],
        )


@dataclass(frozen=True)
class TaskRecord:
    """Typed representation of a persisted task."""

    id: str
    project_id: str
    description: str
    status: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> TaskRecord:
        return cls(
            id=row["id"],
            project_id=row["project_id"],
            description=row["description"],
            status=row["status"],
            created_at=row["created_at"],
        )


@dataclass(frozen=True)
class ExecutionRecord:
    """Typed representation of a persisted command execution result."""

    id: str
    task_id: str | None
    success: bool
    stdout: str
    stderr: str
    duration_ms: int
    retry_count: int
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> ExecutionRecord:
        return cls(
            id=row["id"],
            task_id=row["task_id"],
            success=bool(row["success"]),
            stdout=row["stdout"],
            stderr=row["stderr"],
            duration_ms=int(row["duration_ms"]),
            retry_count=int(row["retry_count"]),
            created_at=row["created_at"],
        )

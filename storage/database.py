"""SQLite connection management and schema initialization for the storage layer."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "ai_website_agent.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    description TEXT NOT NULL CHECK (length(trim(description)) > 0),
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id);

CREATE TABLE IF NOT EXISTS executions (
    id TEXT PRIMARY KEY,
    task_id TEXT,
    success INTEGER NOT NULL CHECK (success IN (0, 1)),
    stdout TEXT NOT NULL DEFAULT '',
    stderr TEXT NOT NULL DEFAULT '',
    duration_ms INTEGER NOT NULL DEFAULT 0 CHECK (duration_ms >= 0),
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    created_at TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_executions_task_id ON executions(task_id);
"""

_configured_db_path: Path | str | None = None


def configure_database(db_path: Path | str | None) -> None:
    """Set or reset the module-level default database path."""
    global _configured_db_path
    _configured_db_path = db_path


def resolve_db_path(db_path: Path | str | None = None) -> Path:
    """Resolve the SQLite database path without relying on the current working directory.

    Resolution order:
    1. Explicit ``db_path`` argument.
    2. Module-level path set via ``configure_database()``.
    3. ``AI_WEBSITE_AGENT_DB_PATH`` environment variable.
    4. ``DEFAULT_DB_PATH`` anchored to ``backend/storage/ai_website_agent.db``.
    """
    target = db_path if db_path is not None else _configured_db_path
    if target is None:
        env_path = os.environ.get("AI_WEBSITE_AGENT_DB_PATH")
        target = env_path if env_path else DEFAULT_DB_PATH

    path = Path(target)
    if not path.is_absolute():
        path = (Path(__file__).resolve().parent / path).resolve()
    return path


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with row factory and foreign-key enforcement enabled."""
    resolved = resolve_db_path(db_path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(resolved))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def connection_scope(db_path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    """Context manager that opens a connection, commits on success, rolls back on error, and closes."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | str | None = None) -> Path:
    """Initialize all database tables and indexes idempotently.

    Returns the resolved database path.
    """
    resolved = resolve_db_path(db_path)
    with connection_scope(resolved) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.execute("PRAGMA foreign_keys = ON;")
    return resolved

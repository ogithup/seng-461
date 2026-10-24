"""SQLite implementation of the API's `StoragePort` (integer IDs, sessions, executions).

Each call opens its own short-lived connection, so the object is safe to share between
request threads and a restart only needs a new `SQLiteStorage` on the same file.
Schema changes go in `MIGRATIONS`; `PRAGMA user_version` records how many have run.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, List, Optional

from backend.storage.models import NotFoundError

MIGRATIONS = [
    """
    CREATE TABLE projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        started_at TEXT NOT NULL
    );
    CREATE TABLE tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        type TEXT NOT NULL,
        prompt TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending'
    );
    CREATE INDEX idx_tasks_project ON tasks(project_id);
    CREATE TABLE executions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        command TEXT NOT NULL,
        status TEXT NOT NULL,
        stdout TEXT NOT NULL DEFAULT '',
        stderr TEXT NOT NULL DEFAULT '',
        retry_count INTEGER NOT NULL DEFAULT 0,
        duration_ms INTEGER NOT NULL DEFAULT 0,
        reason TEXT,
        created_at TEXT NOT NULL
    );
    CREATE INDEX idx_executions_task ON executions(task_id);
    """,
]


@dataclass
class ProjectRecord:
    id: int
    name: str
    created_at: datetime


@dataclass
class SessionRecord:
    id: int
    project_id: int
    started_at: datetime


@dataclass
class TaskRecord:
    id: int
    project_id: int
    type: str
    status: str
    prompt: str


@dataclass
class ExecutionRecord:
    id: int
    task_id: int
    command: str
    status: str
    stdout: str
    stderr: str
    retry_count: int
    duration_ms: int
    reason: Optional[str]
    created_at: datetime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _text(value: Any) -> str:
    return str(getattr(value, "value", value))


class SQLiteStorage:
    def __init__(
        self, db_path: Path | str, clock: Callable[[], datetime] = _utcnow
    ) -> None:
        self.db_path = Path(db_path)
        self._clock = clock
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:  # commit, or roll back on error
                yield conn
        finally:
            conn.close()

    def _migrate(self) -> None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            applied = conn.execute("PRAGMA user_version").fetchone()[0]
            for number, script in enumerate(MIGRATIONS[applied:], start=applied + 1):
                for statement in script.split(";"):
                    if statement.strip():
                        conn.execute(statement)
                conn.execute("PRAGMA user_version = %d" % number)

    def _now(self) -> str:
        return self._clock().astimezone(timezone.utc).isoformat()

    @staticmethod
    def _when(raw: str) -> datetime:
        return datetime.fromisoformat(raw)

    @staticmethod
    def _task(row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(row["id"], row["project_id"], row["type"], row["status"], row["prompt"])

    def _execution(self, row: sqlite3.Row) -> ExecutionRecord:
        return ExecutionRecord(
            row["id"], row["task_id"], row["command"], row["status"], row["stdout"],
            row["stderr"], row["retry_count"], row["duration_ms"], row["reason"],
            self._when(row["created_at"]),
        )

    def _insert(self, sql: str, params: tuple, what: str) -> int:
        try:
            with self._connect() as conn:
                return conn.execute(sql, params).lastrowid
        except sqlite3.IntegrityError as exc:
            raise NotFoundError("%s does not exist" % what) from exc

    # projects / sessions

    def create_project(self, name: str) -> ProjectRecord:
        created = self._now()
        new_id = self._insert(
            "INSERT INTO projects (name, created_at) VALUES (?, ?)", (name, created), "project"
        )
        return ProjectRecord(new_id, name, self._when(created))

    def get_project(self, project_id: int) -> Optional[ProjectRecord]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return ProjectRecord(row["id"], row["name"], self._when(row["created_at"])) if row else None

    def list_projects(self) -> List[ProjectRecord]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY id").fetchall()
        return [ProjectRecord(r["id"], r["name"], self._when(r["created_at"])) for r in rows]

    def create_session(self, project_id: int) -> SessionRecord:
        started = self._now()
        new_id = self._insert(
            "INSERT INTO sessions (project_id, started_at) VALUES (?, ?)",
            (project_id, started),
            "project %s" % project_id,
        )
        return SessionRecord(new_id, project_id, self._when(started))

    # tasks

    def create_task(self, project_id: int, task_type: str, prompt: str) -> TaskRecord:
        new_id = self._insert(
            "INSERT INTO tasks (project_id, type, prompt) VALUES (?, ?, ?)",
            (project_id, task_type, prompt),
            "project %s" % project_id,
        )
        return TaskRecord(new_id, project_id, task_type, "pending", prompt)

    def get_task(self, task_id: int) -> Optional[TaskRecord]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return self._task(row) if row else None

    def list_tasks(self, project_id: int) -> List[TaskRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE project_id = ? ORDER BY id", (project_id,)
            ).fetchall()
        return [self._task(r) for r in rows]

    def update_task_status(self, task_id: int, status: str) -> TaskRecord:
        with self._connect() as conn:
            conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (_text(status), task_id))
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise NotFoundError("task %s does not exist" % task_id)
        return self._task(row)

    # executions

    def save_execution(
        self,
        task_id: int,
        command: str,
        status: str,
        stdout: str = "",
        stderr: str = "",
        retry_count: int = 0,
        duration_ms: int = 0,
        reason: Optional[str] = None,
    ) -> ExecutionRecord:
        created = self._now()
        new_id = self._insert(
            "INSERT INTO executions (task_id, command, status, stdout, stderr, retry_count,"
            " duration_ms, reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id, command, _text(status), stdout, stderr, retry_count, duration_ms, reason, created),
            "task %s" % task_id,
        )
        return ExecutionRecord(
            new_id, task_id, command, _text(status), stdout, stderr, retry_count,
            duration_ms, reason, self._when(created),
        )

    def get_execution(self, execution_id: int) -> Optional[ExecutionRecord]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM executions WHERE id = ?", (execution_id,)).fetchone()
        return self._execution(row) if row else None

    def update_execution(
        self,
        execution_id: int,
        status: str,
        stdout: Optional[str] = None,
        stderr: Optional[str] = None,
        retry_count: Optional[int] = None,
        duration_ms: Optional[int] = None,
    ) -> ExecutionRecord:
        with self._connect() as conn:
            conn.execute(
                "UPDATE executions SET status = ?, stdout = COALESCE(?, stdout),"
                " stderr = COALESCE(?, stderr), retry_count = COALESCE(?, retry_count),"
                " duration_ms = COALESCE(?, duration_ms) WHERE id = ?",
                (_text(status), stdout, stderr, retry_count, duration_ms, execution_id),
            )
            row = conn.execute("SELECT * FROM executions WHERE id = ?", (execution_id,)).fetchone()
        if row is None:
            raise NotFoundError("execution %s does not exist" % execution_id)
        return self._execution(row)

    def list_executions(
        self,
        project_id: int,
        after_id: int = 0,
        limit: int = 100,
        task_id: Optional[int] = None,
    ) -> List[ExecutionRecord]:
        sql = (
            "SELECT e.* FROM executions e JOIN tasks t ON t.id = e.task_id"
            " WHERE t.project_id = ? AND e.id > ?"
        )
        params: list = [project_id, after_id]
        if task_id is not None:
            sql += " AND e.task_id = ?"
            params.append(task_id)
        sql += " ORDER BY e.id LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            return [self._execution(r) for r in conn.execute(sql, params).fetchall()]

    def get_pending_execution(self, project_id: int) -> Optional[ExecutionRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT e.* FROM executions e JOIN tasks t ON t.id = e.task_id"
                " WHERE t.project_id = ? AND e.status = 'pending_approval'"
                " ORDER BY e.id DESC LIMIT 1",
                (project_id,),
            ).fetchone()
        return self._execution(row) if row else None

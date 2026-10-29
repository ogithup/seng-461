"""SQLite implementation of the API's `StoragePort` (integer IDs, sessions, executions).

Each call opens its own short-lived connection, so the object is safe to share between
request threads and a restart only needs a new `SQLiteStorage` on the same file.
Schema changes go in `MIGRATIONS`; `PRAGMA user_version` records how many have run.
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, List, Optional, Tuple

from backend.storage.models import (
    IdempotencyConflictError,
    IdempotencyInProgressError,
    NotFoundError,
)

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
    CREATE TABLE IF NOT EXISTS idempotency_keys (
        owner TEXT NOT NULL,
        scope TEXT NOT NULL,
        key TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        status_code INTEGER,
        response_json TEXT,
        created_at REAL NOT NULL,
        PRIMARY KEY (owner, scope, key)
    );
    CREATE INDEX IF NOT EXISTS idx_idempotency_created ON idempotency_keys(created_at);
    CREATE TABLE IF NOT EXISTS file_metadata (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        path TEXT NOT NULL,
        size_bytes INTEGER NOT NULL,
        sha256 TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE (project_id, path)
    );
    CREATE INDEX IF NOT EXISTS idx_file_metadata_project ON file_metadata(project_id);
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


@dataclass
class FileMetadataRecord:
    id: int
    project_id: int
    path: str
    size_bytes: int
    sha256: str
    created_at: datetime
    updated_at: datetime


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
            if applied == 0:
                # Check for legacy Sprint 1 schema without user_version
                has_tasks = conn.execute(
                    "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='tasks'"
                ).fetchone()[0]
                if has_tasks > 0:
                    cols = [r["name"] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()]
                    if "description" in cols and "prompt" not in cols:
                        self._migrate_legacy_schema(conn)
                        applied = 1
            for number, script in enumerate(MIGRATIONS[applied:], start=applied + 1):
                for statement in script.split(";"):
                    if statement.strip():
                        conn.execute(statement)
                conn.execute("PRAGMA user_version = %d" % number)
            # Ensure tables from migration 1 exist even if user_version was already 1
            conn.execute("""
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    owner TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    key TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    status_code INTEGER,
                    response_json TEXT,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (owner, scope, key)
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_idempotency_created ON idempotency_keys(created_at);")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS file_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    path TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    sha256 TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (project_id, path)
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_file_metadata_project ON file_metadata(project_id);")

    def _migrate_legacy_schema(self, conn: sqlite3.Connection) -> None:
        """Migrate legacy Sprint 1 schema (UUID text IDs, tasks.description, executions.success) to canonical schema."""
        conn.execute("""
            CREATE TABLE projects_v1 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
        conn.execute("""
            CREATE TABLE sessions_v1 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects_v1(id) ON DELETE CASCADE,
                started_at TEXT NOT NULL
            );
        """)
        conn.execute("""
            CREATE TABLE tasks_v1 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects_v1(id) ON DELETE CASCADE,
                type TEXT NOT NULL,
                prompt TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
            );
        """)
        conn.execute("""
            CREATE TABLE executions_v1 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL REFERENCES tasks_v1(id) ON DELETE CASCADE,
                command TEXT NOT NULL,
                status TEXT NOT NULL,
                stdout TEXT NOT NULL DEFAULT '',
                stderr TEXT NOT NULL DEFAULT '',
                retry_count INTEGER NOT NULL DEFAULT 0,
                duration_ms INTEGER NOT NULL DEFAULT 0,
                reason TEXT,
                created_at TEXT NOT NULL
            );
        """)

        old_projects = conn.execute("SELECT id, name, created_at FROM projects ORDER BY rowid").fetchall()
        project_id_map = {}
        for p in old_projects:
            cur = conn.execute(
                "INSERT INTO projects_v1 (name, created_at) VALUES (?, ?)", (p["name"], p["created_at"])
            )
            project_id_map[p["id"]] = cur.lastrowid

        old_tasks = conn.execute("SELECT id, project_id, description, status FROM tasks ORDER BY rowid").fetchall()
        task_id_map = {}
        for t in old_tasks:
            new_pid = project_id_map.get(t["project_id"])
            if new_pid is not None:
                cur = conn.execute(
                    "INSERT INTO tasks_v1 (project_id, type, prompt, status) VALUES (?, 'step', ?, ?)",
                    (new_pid, t["description"], t["status"]),
                )
                task_id_map[t["id"]] = cur.lastrowid

        has_exec = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='executions'"
        ).fetchone()[0]
        if has_exec > 0:
            old_execs = conn.execute(
                "SELECT id, task_id, success, stdout, stderr, retry_count, duration_ms, created_at FROM executions ORDER BY rowid"
            ).fetchall()
            for e in old_execs:
                new_tid = task_id_map.get(e["task_id"])
                if new_tid is not None:
                    status = "succeeded" if e["success"] == 1 else "failed"
                    conn.execute(
                        "INSERT INTO executions_v1 (task_id, command, status, stdout, stderr, retry_count, duration_ms, reason, created_at)"
                        " VALUES (?, 'execution', ?, ?, ?, ?, ?, '', ?)",
                        (
                            new_tid,
                            status,
                            e["stdout"] or "",
                            e["stderr"] or "",
                            e["retry_count"] or 0,
                            e["duration_ms"] or 0,
                            e["created_at"],
                        ),
                    )

        conn.execute("DROP TABLE IF EXISTS executions")
        conn.execute("DROP TABLE IF EXISTS tasks")
        conn.execute("DROP TABLE IF EXISTS projects")

        conn.execute("ALTER TABLE projects_v1 RENAME TO projects")
        conn.execute("ALTER TABLE sessions_v1 RENAME TO sessions")
        conn.execute("ALTER TABLE tasks_v1 RENAME TO tasks")
        conn.execute("ALTER TABLE executions_v1 RENAME TO executions")

        conn.execute("CREATE INDEX idx_tasks_project ON tasks(project_id)")
        conn.execute("CREATE INDEX idx_executions_task ON executions(task_id)")
        conn.execute("PRAGMA user_version = 1")

    def _now(self) -> str:
        return self._clock().astimezone(timezone.utc).isoformat()

    @staticmethod
    def _when(raw: str) -> datetime:
        # Python < 3.11 cannot parse a trailing 'Z' (legacy rows use it).
        return datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)

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
        project_id: Optional[int] = None,
    ) -> ExecutionRecord:
        task = self.get_task(task_id)
        if task is None:
            raise NotFoundError("task %s does not exist" % task_id)
        if project_id is not None and task.project_id != project_id:
            raise NotFoundError("task %s does not belong to project %s" % (task_id, project_id))
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

    def get_execution(self, execution_id: int, project_id: Optional[int] = None) -> Optional[ExecutionRecord]:
        with self._connect() as conn:
            if project_id is not None:
                row = conn.execute(
                    "SELECT e.* FROM executions e JOIN tasks t ON t.id = e.task_id"
                    " WHERE e.id = ? AND t.project_id = ?",
                    (execution_id, project_id),
                ).fetchone()
            else:
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

    # file metadata

    def save_file_metadata(
        self,
        project_id: int,
        path: str,
        size_bytes: int,
        sha256: str = "",
    ) -> FileMetadataRecord:
        if self.get_project(project_id) is None:
            raise NotFoundError("project %s does not exist" % project_id)
        now = self._now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, created_at FROM file_metadata WHERE project_id = ? AND path = ?",
                (project_id, path),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE file_metadata SET size_bytes = ?, sha256 = ?, updated_at = ? WHERE id = ?",
                    (size_bytes, sha256, now, row["id"]),
                )
                return FileMetadataRecord(
                    row["id"], project_id, path, size_bytes, sha256,
                    self._when(row["created_at"]), self._when(now),
                )
            new_id = conn.execute(
                "INSERT INTO file_metadata (project_id, path, size_bytes, sha256, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (project_id, path, size_bytes, sha256, now, now),
            ).lastrowid
            return FileMetadataRecord(
                new_id, project_id, path, size_bytes, sha256,
                self._when(now), self._when(now),
            )

    def get_file_metadata(self, project_id: int, path: str) -> Optional[FileMetadataRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM file_metadata WHERE project_id = ? AND path = ?", (project_id, path)
            ).fetchone()
        if not row:
            return None
        return FileMetadataRecord(
            row["id"], row["project_id"], row["path"], row["size_bytes"], row["sha256"],
            self._when(row["created_at"]), self._when(row["updated_at"]),
        )

    def list_file_metadata(self, project_id: int) -> List[FileMetadataRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM file_metadata WHERE project_id = ? ORDER BY path", (project_id,)
            ).fetchall()
        return [
            FileMetadataRecord(
                r["id"], r["project_id"], r["path"], r["size_bytes"], r["sha256"],
                self._when(r["created_at"]), self._when(r["updated_at"]),
            )
            for r in rows
        ]

    # durable idempotency

    def idempotency_begin(
        self,
        owner: str,
        scope: str,
        key: str,
        fingerprint: str,
        ttl_seconds: float = 86400.0,
        max_entries: int = 1000,
    ) -> Optional[Tuple[int, Any]]:
        with self._connect() as conn:
            now_sec = time.time()
            conn.execute("DELETE FROM idempotency_keys WHERE created_at < ?", (now_sec - ttl_seconds,))

            count = conn.execute("SELECT count(*) FROM idempotency_keys").fetchone()[0]
            if count >= max_entries:
                conn.execute(
                    "DELETE FROM idempotency_keys WHERE (owner, scope, key) IN ("
                    " SELECT owner, scope, key FROM idempotency_keys WHERE status_code IS NOT NULL"
                    " ORDER BY created_at ASC LIMIT ?"
                    ")",
                    (max_entries // 10 or 1,),
                )

            row = conn.execute(
                "SELECT * FROM idempotency_keys WHERE owner = ? AND scope = ? AND key = ?",
                (owner, scope, key),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO idempotency_keys (owner, scope, key, fingerprint, created_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (owner, scope, key, fingerprint, now_sec),
                )
                return None

            if row["fingerprint"] != fingerprint:
                raise IdempotencyConflictError("This Idempotency-Key was already used with a different request.")
            if row["status_code"] is None:
                raise IdempotencyInProgressError("A request with this Idempotency-Key is still being processed.")

            body = json.loads(row["response_json"]) if row["response_json"] is not None else None
            return int(row["status_code"]), body

    def idempotency_complete(
        self,
        owner: str,
        scope: str,
        key: str,
        status_code: int,
        response_body: Any,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE idempotency_keys SET status_code = ?, response_json = ? WHERE owner = ? AND scope = ? AND key = ?",
                (status_code, json.dumps(response_body), owner, scope, key),
            )

    def idempotency_abort(self, owner: str, scope: str, key: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM idempotency_keys WHERE owner = ? AND scope = ? AND key = ?",
                (owner, scope, key),
            )

"""Unit tests for storage consistency, migration, file metadata, and durable idempotency."""
import sqlite3
import pytest

from backend.storage.models import (
    IdempotencyConflictError,
    IdempotencyInProgressError,
    NotFoundError,
)
from backend.storage.sqlite_storage import SQLiteStorage


def test_legacy_schema_migration_to_canonical(tmp_path):
    """A legacy Sprint 1 database (UUID text IDs, tasks.description, executions.success)

    is cleanly migrated to the canonical schema with auto-increment IDs and sessions.
    """
    db_file = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript("""
        CREATE TABLE projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        CREATE TABLE executions (
            id TEXT PRIMARY KEY,
            task_id TEXT,
            success INTEGER NOT NULL,
            stdout TEXT NOT NULL DEFAULT '',
            stderr TEXT NOT NULL DEFAULT '',
            duration_ms INTEGER NOT NULL DEFAULT 0,
            retry_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
        );
    """)
    conn.execute(
        "INSERT INTO projects (id, name, created_at) VALUES ('p-uuid-1', 'Legacy Blog', '2026-10-16T12:00:00Z')"
    )
    conn.execute(
        "INSERT INTO tasks (id, project_id, description, status, created_at) VALUES ('t-uuid-1', 'p-uuid-1', 'Write index', 'succeeded', '2026-10-16T12:01:00Z')"
    )
    conn.execute(
        "INSERT INTO executions (id, task_id, success, stdout, stderr, duration_ms, retry_count, created_at) VALUES ('e-uuid-1', 't-uuid-1', 1, 'wrote index.html', '', 45, 0, '2026-10-16T12:01:05Z')"
    )
    conn.commit()
    conn.close()

    # Open with SQLiteStorage -> triggers migration
    storage = SQLiteStorage(db_file)

    # Verify project
    projects = storage.list_projects()
    assert len(projects) == 1
    p = projects[0]
    assert p.id == 1
    assert p.name == "Legacy Blog"

    # Verify tasks
    tasks = storage.list_tasks(p.id)
    assert len(tasks) == 1
    t = tasks[0]
    assert t.project_id == p.id
    assert t.prompt == "Write index"
    assert t.status == "succeeded"

    # Verify executions
    execs = storage.list_executions(p.id)
    assert len(execs) == 1
    e = execs[0]
    assert e.task_id == t.id
    assert e.status == "succeeded"
    assert e.stdout == "wrote index.html"

    # Verify re-running migration on the same database is safe and idempotent
    storage_reopen = SQLiteStorage(db_file)
    assert len(storage_reopen.list_projects()) == 1
    assert len(storage_reopen.list_tasks(p.id)) == 1


def test_file_metadata_operations_and_foreign_key(tmp_path):
    storage = SQLiteStorage(tmp_path / "files.db")
    project = storage.create_project("Site")

    # Record file metadata
    rec1 = storage.save_file_metadata(project.id, "index.html", 120, "abc123sha")
    assert rec1.project_id == project.id
    assert rec1.path == "index.html"
    assert rec1.size_bytes == 120
    assert rec1.sha256 == "abc123sha"

    # Get file metadata
    fetched = storage.get_file_metadata(project.id, "index.html")
    assert fetched is not None
    assert fetched.size_bytes == 120

    # Update file metadata
    rec1_updated = storage.save_file_metadata(project.id, "index.html", 250, "def456sha")
    assert rec1_updated.id == rec1.id
    assert rec1_updated.size_bytes == 250
    assert rec1_updated.sha256 == "def456sha"

    # Add second file
    storage.save_file_metadata(project.id, "style.css", 80, "css789sha")
    file_list = storage.list_file_metadata(project.id)
    assert len(file_list) == 2
    assert [f.path for f in file_list] == ["index.html", "style.css"]

    # Missing project raises NotFoundError
    with pytest.raises(NotFoundError):
        storage.save_file_metadata(999, "test.html", 10)

    # Missing file returns None
    assert storage.get_file_metadata(project.id, "nonexistent.html") is None


def test_execution_project_validation(tmp_path):
    storage = SQLiteStorage(tmp_path / "exec.db")
    p1 = storage.create_project("P1")
    p2 = storage.create_project("P2")
    t1 = storage.create_task(p1.id, "step", "task 1")
    t2 = storage.create_task(p2.id, "step", "task 2")

    # Save execution with matching project_id
    e1 = storage.save_execution(t1.id, "cmd1", "succeeded", project_id=p1.id)
    assert e1.task_id == t1.id

    # Saving execution with mismatched project_id raises NotFoundError
    with pytest.raises(NotFoundError):
        storage.save_execution(t1.id, "cmd2", "succeeded", project_id=p2.id)

    # Saving execution with nonexistent task_id raises NotFoundError
    with pytest.raises(NotFoundError):
        storage.save_execution(9999, "cmd", "succeeded")

    # Get execution with project_id verification
    assert storage.get_execution(e1.id, project_id=p1.id) is not None
    assert storage.get_execution(e1.id, project_id=p2.id) is None


def test_durable_idempotency_in_sqlite(tmp_path):
    db_file = tmp_path / "idemp.db"
    storage = SQLiteStorage(db_file)

    # 1. First claim succeeds
    res = storage.idempotency_begin("local", "chat", "k1", "fp123")
    assert res is None

    # 2. In-progress claim raises IdempotencyInProgressError
    with pytest.raises(IdempotencyInProgressError):
        storage.idempotency_begin("local", "chat", "k1", "fp123")

    # 3. Complete request
    storage.idempotency_complete("local", "chat", "k1", 200, {"result": "ok"})

    # 4. Replay returns stored response
    replay = storage.idempotency_begin("local", "chat", "k1", "fp123")
    assert replay == (200, {"result": "ok"})

    # 5. Same key with different fingerprint raises IdempotencyConflictError
    with pytest.raises(IdempotencyConflictError):
        storage.idempotency_begin("local", "chat", "k1", "different_fp")

    # 6. Preserved across reopening SQLiteStorage (process restart simulation)
    reopened = SQLiteStorage(db_file)
    replay_after_restart = reopened.idempotency_begin("local", "chat", "k1", "fp123")
    assert replay_after_restart == (200, {"result": "ok"})

    # 7. Aborted key can be claimed again
    storage.idempotency_begin("local", "chat", "k2", "fp2")
    storage.idempotency_abort("local", "chat", "k2")
    retry_claim = storage.idempotency_begin("local", "chat", "k2", "fp2")
    assert retry_claim is None

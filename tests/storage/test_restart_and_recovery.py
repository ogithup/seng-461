"""K2: Tests verifying full restart and recovery across database and workspace."""
import hashlib

from backend.api.config import Settings
from backend.api.schemas.enums import RunStatus, TaskStatus
from backend.api.services.container import build_services
from backend.storage.sqlite_storage import SQLiteStorage


def test_full_project_session_task_execution_and_workspace_recovery_across_restart(tmp_path):
    """Creating a project, session, tasks, execution records, file metadata, and workspace files,
    then recreating SQLiteStorage and backend services against the same DB & workspace recovers
    every record and workspace file accurately and unchanged.
    """
    db_path = tmp_path / "app.db"
    workspace_root = tmp_path / "workspaces"

    storage1 = SQLiteStorage(db_path)
    project = storage1.create_project("Portfolio Site")
    session = storage1.create_session(project.id)

    task1 = storage1.create_task(project.id, "step", "Write index.html")
    task2 = storage1.create_task(project.id, "step", "Write style.css")

    project_dir = workspace_root / ("project_%d" % project.id)
    project_dir.mkdir(parents=True, exist_ok=True)
    html_text = "<!doctype html><html><body><h1>Portfolio</h1></body></html>"
    css_text = "body { font-family: sans-serif; }"
    (project_dir / "index.html").write_text(html_text, encoding="utf-8")
    (project_dir / "style.css").write_text(css_text, encoding="utf-8")

    html_bytes = html_text.encode("utf-8")
    css_bytes = css_text.encode("utf-8")
    html_sha = hashlib.sha256(html_bytes).hexdigest()[:12]
    css_sha = hashlib.sha256(css_bytes).hexdigest()[:12]

    exec1 = storage1.save_execution(
        task1.id,
        "write_file index.html",
        "succeeded",
        stdout="wrote index.html (%d bytes, sha256 %s)" % (len(html_bytes), html_sha),
        duration_ms=12,
        retry_count=0,
        project_id=project.id,
    )
    meta1 = storage1.save_file_metadata(project.id, "index.html", len(html_bytes), html_sha)
    storage1.update_task_status(task1.id, "succeeded")

    exec2 = storage1.save_execution(
        task2.id,
        "write_file style.css",
        "succeeded",
        stdout="wrote style.css (%d bytes, sha256 %s)" % (len(css_bytes), css_sha),
        duration_ms=8,
        retry_count=0,
        project_id=project.id,
    )
    meta2 = storage1.save_file_metadata(project.id, "style.css", len(css_bytes), css_sha)
    storage1.update_task_status(task2.id, "succeeded")

    del storage1

    # Simulate process restart with a fresh SQLiteStorage on the same database file.
    storage2 = SQLiteStorage(db_path)

    assert storage2.get_project(project.id) == project
    assert storage2.list_projects() == [project]
    assert storage2.get_session(session.id) == session
    assert storage2.list_sessions(project.id) == [session]

    recovered_tasks = storage2.list_tasks(project.id)
    assert [(t.id, t.type, t.prompt, t.status) for t in recovered_tasks] == [
        (task1.id, "step", "Write index.html", "succeeded"),
        (task2.id, "step", "Write style.css", "succeeded"),
    ]
    assert storage2.get_task(task1.id) == recovered_tasks[0]
    assert storage2.get_task(task2.id) == recovered_tasks[1]

    recovered_execs = storage2.list_executions(project.id)
    assert recovered_execs == [exec1, exec2]
    assert storage2.get_execution(exec1.id, project_id=project.id) == exec1
    assert storage2.get_execution(exec2.id, project_id=project.id) == exec2

    assert storage2.get_file_metadata(project.id, "index.html") == meta1
    assert storage2.get_file_metadata(project.id, "style.css") == meta2
    assert storage2.list_file_metadata(project.id) == [meta1, meta2]
    assert storage2.verify_workspace_files(project.id, project_dir) == {
        "verified": ["index.html", "style.css"],
        "missing": [],
        "mismatched": [],
    }

    # Recreate full backend services against the exact same DB and workspace root.
    services = build_services(
        Settings(
            workspace_root=workspace_root,
            database_path=db_path,
            rate_limit_per_minute=0,
        )
    )
    recovered_project = services.projects.require(project.id)
    assert recovered_project.id == project.id
    assert recovered_project.name == "Portfolio Site"

    state = services.tasks.state(project.id)
    assert state.status == RunStatus.COMPLETED
    assert [t.status for t in state.tasks] == [TaskStatus.SUCCEEDED, TaskStatus.SUCCEEDED]

    logs = services.tasks.logs(project.id, after_id=0, limit=100)
    assert [e.id for e in logs.entries] == [exec1.id, exec2.id]
    assert [e.command for e in logs.entries] == ["write_file index.html", "write_file style.css"]

    assert services.workspace.project_dir(project.id) == project_dir.resolve()
    files, truncated = services.workspace.list_files(project.id)
    assert not truncated
    assert [f.path for f in files] == ["index.html", "style.css"]
    assert services.workspace.read_text(project.id, "index.html")[2] == html_text
    assert services.workspace.read_text(project.id, "style.css")[2] == css_text


def test_end_to_end_services_restart_preserves_workspace_and_records(tmp_path):
    """Run a real chat build through build_services, restart build_services on the same DB
    and workspace directory, and verify all records and files remain identical.
    """
    settings = Settings(
        workspace_root=tmp_path / "workspaces",
        database_path=tmp_path / "app.db",
        rate_limit_per_minute=0,
    )
    first_services = build_services(settings)
    created = first_services.projects.create("Recovery Blog")
    pid = created.id
    chat_result = first_services.chat.handle(pid, "Create a blog called Recovery Notes")
    assert chat_result.status == RunStatus.COMPLETED

    files_before, _ = first_services.workspace.list_files(pid)
    logs_before = first_services.tasks.logs(pid, after_id=0, limit=100)
    tasks_before = first_services.tasks.state(pid)
    project_dir_before = first_services.workspace.project_dir(pid)

    del first_services

    # Restart services on the exact same DB and workspace directory.
    restarted_services = build_services(settings)
    assert restarted_services.projects.require(pid).name == "Recovery Blog"
    assert restarted_services.tasks.state(pid) == tasks_before
    assert restarted_services.tasks.logs(pid, after_id=0, limit=100) == logs_before
    assert restarted_services.workspace.project_dir(pid) == project_dir_before

    files_after, _ = restarted_services.workspace.list_files(pid)
    assert files_after == files_before
    assert restarted_services.workspace.has_index_html(pid)

    reopened_storage = SQLiteStorage(settings.database_path)
    sessions = reopened_storage.list_sessions(pid)
    assert len(sessions) == 1
    assert sessions[0].id == created.session_id
    verification = reopened_storage.verify_workspace_files(pid, project_dir_before)
    assert verification["missing"] == []
    assert verification["mismatched"] == []
    assert set(verification["verified"]) == {f.path for f in files_before}


def test_id_sequences_and_multi_project_isolation_continue_cleanly_after_restart(tmp_path):
    """IDs continue monotonically without reuse and multi-project records stay isolated after restart."""
    db_path = tmp_path / "multi.db"
    first = SQLiteStorage(db_path)

    p1 = first.create_project("Alpha")
    p2 = first.create_project("Beta")
    s1 = first.create_session(p1.id)
    s2 = first.create_session(p2.id)
    t1 = first.create_task(p1.id, "step", "alpha step")
    t2 = first.create_task(p2.id, "step", "beta step")
    e1 = first.save_execution(t1.id, "write_file index.html", "succeeded", stdout="ok")
    e2 = first.save_execution(t2.id, "write_file index.html", "succeeded", stdout="ok")
    first.update_task_status(t1.id, "succeeded")
    first.update_task_status(t2.id, "succeeded")

    del first
    second = SQLiteStorage(db_path)

    p3 = second.create_project("Gamma")
    s3 = second.create_session(p3.id)
    t3 = second.create_task(p3.id, "step", "gamma step")
    e3 = second.save_execution(t3.id, "write_file index.html", "succeeded", stdout="ok")
    second.update_task_status(t3.id, "succeeded")

    assert [p.id for p in second.list_projects()] == [p1.id, p2.id, p3.id]
    assert p3.id > p2.id > p1.id
    assert s3.id > s2.id > s1.id
    assert t3.id > t2.id > t1.id
    assert e3.id > e2.id > e1.id

    assert second.list_sessions(p1.id) == [s1]
    assert second.list_sessions(p2.id) == [s2]
    assert second.list_sessions(p3.id) == [s3]
    assert [t.prompt for t in second.list_tasks(p1.id)] == ["alpha step"]
    assert [t.prompt for t in second.list_tasks(p2.id)] == ["beta step"]
    assert [t.prompt for t in second.list_tasks(p3.id)] == ["gamma step"]
    assert [e.id for e in second.list_executions(p1.id)] == [e1.id]
    assert [e.id for e in second.list_executions(p2.id)] == [e2.id]
    assert [e.id for e in second.list_executions(p3.id)] == [e3.id]


def test_legacy_sprint1_database_with_completed_status_recovers_after_restart(tmp_path):
    """Legacy Sprint 1 rows with status='completed' normalize to canonical 'succeeded'
    so migrated records survive restart and validate cleanly in TaskService.state().
    """
    import sqlite3

    db_path = tmp_path / "legacy_completed.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
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
            created_at TEXT NOT NULL
        );
        CREATE TABLE executions (
            id TEXT PRIMARY KEY,
            task_id TEXT,
            success INTEGER NOT NULL,
            stdout TEXT NOT NULL DEFAULT '',
            stderr TEXT NOT NULL DEFAULT '',
            duration_ms INTEGER NOT NULL DEFAULT 0,
            retry_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.execute(
        "INSERT INTO projects (id, name, created_at) VALUES ('p-1', 'Legacy Site', '2026-10-16T12:00:00Z')"
    )
    conn.execute(
        "INSERT INTO tasks (id, project_id, description, status, created_at)"
        " VALUES ('t-1', 'p-1', 'Build index', 'completed', '2026-10-16T12:01:00Z')"
    )
    conn.execute(
        "INSERT INTO executions (id, task_id, success, stdout, stderr, duration_ms, retry_count, created_at)"
        " VALUES ('e-1', 't-1', 1, 'wrote index.html', '', 15, 0, '2026-10-16T12:01:05Z')"
    )
    conn.commit()
    conn.close()

    # First open migrates the legacy DB; second open simulates restart.
    SQLiteStorage(db_path)
    restarted = SQLiteStorage(db_path)

    projects = restarted.list_projects()
    assert len(projects) == 1
    pid = projects[0].id
    tasks = restarted.list_tasks(pid)
    assert len(tasks) == 1
    assert tasks[0].status == "succeeded"

    services = build_services(
        Settings(
            workspace_root=tmp_path / "workspaces",
            database_path=db_path,
            rate_limit_per_minute=0,
        )
    )
    state = services.tasks.state(pid)
    assert state.status == RunStatus.COMPLETED
    assert [t.status for t in state.tasks] == [TaskStatus.SUCCEEDED]

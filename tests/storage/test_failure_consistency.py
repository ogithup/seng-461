"""K3 & K4: Tests for failure consistency, interrupted state recovery, and mismatch checks."""
import hashlib
import sqlite3
import pytest

from backend.api.config import Settings
from backend.api.schemas.enums import RunStatus, TaskStatus
from backend.api.services.container import build_services
from backend.storage.models import ValidationError
from backend.storage.sqlite_storage import SQLiteStorage
from tests.integration.fakes import FixedPlanAgent, ScriptedAgent


# --- K3/K4 Storage-owned defects & invariants -------------------------------------------


def test_cannot_mark_task_succeeded_when_latest_execution_failed_or_unapproved(tmp_path):
    """Storage must never allow marking a task 'succeeded' if its latest execution failed,
    is pending approval, was rejected, or expired.
    """
    storage = SQLiteStorage(tmp_path / "s.db")
    project = storage.create_project("Site")

    for bad_status in ("failed", "pending_approval", "rejected", "expired"):
        task = storage.create_task(project.id, "step", "write %s" % bad_status)
        storage.update_task_status(task.id, "running")
        storage.save_execution(task.id, "write_file index.html", bad_status, stderr="err")

        with pytest.raises(ValidationError):
            storage.update_task_status(task.id, "succeeded")
        assert storage.get_task(task.id).status == "running"

    # Once a repair execution succeeds, marking the task succeeded is allowed.
    repair_task = storage.create_task(project.id, "step", "retry write")
    storage.update_task_status(repair_task.id, "running")
    storage.save_execution(repair_task.id, "write_file index.html", "failed", stderr="transient")
    with pytest.raises(ValidationError):
        storage.update_task_status(repair_task.id, "succeeded")

    storage.save_execution(repair_task.id, "write_file index.html", "succeeded", stdout="ok")
    updated = storage.update_task_status(repair_task.id, "succeeded")
    assert updated.status == "succeeded"


def test_saving_or_updating_failed_execution_demotes_previously_succeeded_task(tmp_path):
    """If a task is currently 'succeeded' and a new non-succeeded execution is saved (or its
    latest execution is updated to a non-succeeded status), storage demotes the task status
    instead of leaving a false 'succeeded' state.
    """
    storage = SQLiteStorage(tmp_path / "s.db")
    project = storage.create_project("Site")

    # Case 1: save_execution with failed/rejected/expired/pending_approval demotes succeeded task.
    t_fail = storage.create_task(project.id, "step", "step 1")
    storage.save_execution(t_fail.id, "write_file index.html", "succeeded", stdout="ok")
    storage.update_task_status(t_fail.id, "succeeded")
    storage.save_execution(t_fail.id, "write_file index.html", "failed", stderr="write error")
    assert storage.get_task(t_fail.id).status == "failed"

    t_rej = storage.create_task(project.id, "step", "step 2")
    storage.update_task_status(t_rej.id, "succeeded")
    storage.save_execution(t_rej.id, "npm install", "rejected")
    assert storage.get_task(t_rej.id).status == "cancelled"

    t_wait = storage.create_task(project.id, "step", "step 3")
    storage.update_task_status(t_wait.id, "succeeded")
    storage.save_execution(t_wait.id, "npm install", "pending_approval")
    assert storage.get_task(t_wait.id).status == "waiting_for_approval"

    # Case 2: update_execution on the latest execution demotes succeeded task.
    t_upd = storage.create_task(project.id, "step", "step 4")
    e_ok = storage.save_execution(t_upd.id, "write_file style.css", "succeeded", stdout="ok")
    storage.update_task_status(t_upd.id, "succeeded")
    storage.update_execution(e_ok.id, "failed", stderr="readback mismatch")
    assert storage.get_task(t_upd.id).status == "failed"

    # Case 3: updating an older superseded execution does not demote when latest execution succeeded.
    t_hist = storage.create_task(project.id, "step", "step 5")
    e_old = storage.save_execution(t_hist.id, "write_file a.html", "pending_approval")
    storage.save_execution(t_hist.id, "write_file a.html", "succeeded", stdout="ok")
    storage.update_task_status(t_hist.id, "succeeded")
    storage.update_execution(e_old.id, "expired")
    assert storage.get_task(t_hist.id).status == "succeeded"


def test_legacy_migration_reconciles_false_succeeded_task_with_failed_execution(tmp_path):
    """Legacy migration must not preserve 'succeeded'/'completed' when the task's latest
    execution failed (success = 0).
    """
    db_file = tmp_path / "legacy_false_success.db"
    conn = sqlite3.connect(db_file)
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
        "INSERT INTO projects (id, name, created_at) VALUES ('p1', 'Broken Legacy', '2026-10-16T12:00:00Z')"
    )
    conn.execute(
        "INSERT INTO tasks (id, project_id, description, status, created_at)"
        " VALUES ('t1', 'p1', 'Write index', 'completed', '2026-10-16T12:01:00Z')"
    )
    conn.execute(
        "INSERT INTO executions (id, task_id, success, stdout, stderr, duration_ms, retry_count, created_at)"
        " VALUES ('e1', 't1', 0, '', 'disk full', 10, 0, '2026-10-16T12:01:05Z')"
    )
    conn.commit()
    conn.close()

    storage = SQLiteStorage(db_file)
    projects = storage.list_projects()
    tasks = storage.list_tasks(projects[0].id)
    assert len(tasks) == 1
    assert tasks[0].status == "failed"


def test_interrupted_running_task_and_queued_pending_tasks_recover_on_restart(tmp_path):
    """If the process dies mid-run while a task is 'running' and later tasks are 'pending',
    restarting SQLiteStorage and backend services against the same DB/workspace must recover
    the interrupted task to 'failed' and queued 'pending' tasks to 'skipped', so the project
    does not stay stuck in 'running'.
    """
    db_path = tmp_path / "crashed.db"
    workspace_root = tmp_path / "workspaces"

    storage1 = SQLiteStorage(db_path)
    project = storage1.create_project("Interrupted Site")
    project_dir = workspace_root / ("project_%d" % project.id)
    project_dir.mkdir(parents=True, exist_ok=True)

    # Task 1 succeeded and wrote index.html
    t1 = storage1.create_task(project.id, "step", "Write index.html")
    (project_dir / "index.html").write_text("<h1>OK</h1>", encoding="utf-8")
    storage1.save_execution(t1.id, "write_file index.html", "succeeded", stdout="wrote index.html")
    storage1.update_task_status(t1.id, "succeeded")

    # Task 2 was mid-execution ('running') when the process died before writing style.css
    t2 = storage1.create_task(project.id, "step", "Write style.css")
    storage1.update_task_status(t2.id, "running")

    # Task 3 was queued behind Task 2
    t3 = storage1.create_task(project.id, "step", "Write script.js")

    del storage1

    # Simulate process restart
    storage2 = SQLiteStorage(db_path)
    recovered_tasks = storage2.list_tasks(project.id)
    assert [(t.id, t.status) for t in recovered_tasks] == [
        (t1.id, "succeeded"),
        (t2.id, "failed"),
        (t3.id, "skipped"),
    ]
    assert not (project_dir / "style.css").exists()
    assert not (project_dir / "script.js").exists()

    services = build_services(
        Settings(
            workspace_root=workspace_root,
            database_path=db_path,
            rate_limit_per_minute=0,
        )
    )
    state = services.tasks.state(project.id)
    assert state.status == RunStatus.FAILED
    assert [t.status for t in state.tasks] == [
        TaskStatus.SUCCEEDED,
        TaskStatus.FAILED,
        TaskStatus.SKIPPED,
    ]


def test_interrupted_in_flight_idempotency_key_is_cleaned_up_on_restart(tmp_path):
    """An in-flight idempotency key (status_code IS NULL) left behind by a crashed process
    must be cleared on restart so clients can safely retry instead of getting stuck with
    IdempotencyInProgressError forever.
    """
    db_file = tmp_path / "idemp_crash.db"
    storage1 = SQLiteStorage(db_file)
    assert storage1.idempotency_begin("local", "chat", "crash-key", "fp1") is None
    del storage1

    reopened = SQLiteStorage(db_file)
    assert reopened.idempotency_begin("local", "chat", "crash-key", "fp1") is None


def test_invalid_statuses_and_invalid_inputs_rejected_by_storage(tmp_path):
    """Storage rejects invalid task/execution statuses, empty fields, negative numbers,
    and unsafe file metadata paths with ValidationError.
    """
    storage = SQLiteStorage(tmp_path / "validate.db")

    for bad_name in ("", "   ", 123):
        with pytest.raises(ValidationError):
            storage.create_project(bad_name)  # type: ignore[arg-type]

    project = storage.create_project("Valid")

    for bad_type, bad_prompt in (("", "ok"), ("   ", "ok"), ("step", ""), ("step", "   ")):
        with pytest.raises(ValidationError):
            storage.create_task(project.id, bad_type, bad_prompt)

    task = storage.create_task(project.id, "step", "write index.html")

    for bad_task_status in ("", "completed", "done", "unknown_status"):
        with pytest.raises(ValidationError):
            storage.update_task_status(task.id, bad_task_status)

    with pytest.raises(ValidationError):
        storage.save_execution(task.id, "", "succeeded")
    with pytest.raises(ValidationError):
        storage.save_execution(task.id, "write_file index.html", "unknown_exec_status")
    with pytest.raises(ValidationError):
        storage.save_execution(task.id, "write_file index.html", "succeeded", duration_ms=-1)
    with pytest.raises(ValidationError):
        storage.save_execution(task.id, "write_file index.html", "succeeded", retry_count=-1)

    ex = storage.save_execution(task.id, "write_file index.html", "pending_approval")
    with pytest.raises(ValidationError):
        storage.update_execution(ex.id, "bogus")
    with pytest.raises(ValidationError):
        storage.update_execution(ex.id, "succeeded", duration_ms=-5)
    with pytest.raises(ValidationError):
        storage.update_execution(ex.id, "succeeded", retry_count=-2)

    for bad_path in ("", "   ", "../escape.html", "/etc/passwd", "C:/x.html", "./index.html", "a\x00b.html"):
        with pytest.raises(ValidationError):
            storage.save_file_metadata(project.id, bad_path, 10)
    with pytest.raises(ValidationError):
        storage.save_file_metadata(project.id, "index.html", -1)


def test_workspace_file_verification_detects_missing_and_modified_files(tmp_path):
    """verify_workspace_files reports missing and content/size-mismatched files compared
    with persisted file_metadata records.
    """
    storage = SQLiteStorage(tmp_path / "verify.db")
    project = storage.create_project("Verify Site")
    project_dir = tmp_path / "workspaces" / ("project_%d" % project.id)
    project_dir.mkdir(parents=True, exist_ok=True)

    expected_html = b"<h1>Expected</h1>"
    expected_css = b"body { color: black; }"
    html_sha = hashlib.sha256(expected_html).hexdigest()[:12]
    css_sha = hashlib.sha256(expected_css).hexdigest()[:12]

    storage.save_file_metadata(project.id, "index.html", len(expected_html), html_sha)
    storage.save_file_metadata(project.id, "style.css", len(expected_css), css_sha)

    # Disk has modified index.html and missing style.css
    (project_dir / "index.html").write_bytes(b"<h1>Corrupted</h1>")
    report = storage.verify_workspace_files(project.id, project_dir)
    assert report == {
        "verified": [],
        "missing": ["style.css"],
        "mismatched": ["index.html"],
    }

    # Restore expected files on disk
    (project_dir / "index.html").write_bytes(expected_html)
    (project_dir / "style.css").write_bytes(expected_css)
    assert storage.verify_workspace_files(project.id, project_dir) == {
        "verified": ["index.html", "style.css"],
        "missing": [],
        "mismatched": [],
    }

    # Deleting metadata removes it cleanly
    assert storage.delete_file_metadata(project.id, "style.css") is True
    assert storage.delete_file_metadata(project.id, "style.css") is False
    assert [f.path for f in storage.list_file_metadata(project.id)] == ["index.html"]


# --- K3 Reproducing Tests for API / Runner / Workspace Mismatches (Owned by Oguz) -------


def test_k3_mismatch_orphan_pending_tasks_without_running_task_report_project_running_until_recovered(tmp_path):
    """Reproduces K3 mismatch #1 (API compute_status + ChatService crash window):
    If the process crashes after ChatService creates 'pending' tasks but before TaskRunner
    transitions the first task to 'running', TaskService.state() returns status='running'
    indefinitely on restart because no task is 'running' for automatic startup recovery.
    Explicit storage.recover_interrupted_tasks(..., include_pending=True) cleans them up.
    """
    db_path = tmp_path / "orphan_pending.db"
    workspace_root = tmp_path / "workspaces"
    storage1 = SQLiteStorage(db_path)
    project = storage1.create_project("Crash Before Run")
    storage1.create_task(project.id, "step", "Write index.html")
    storage1.create_task(project.id, "step", "Write style.css")
    del storage1

    # Restart without include_pending recovery: TaskService.state() reports 'running' with 0 files!
    services = build_services(
        Settings(workspace_root=workspace_root, database_path=db_path, rate_limit_per_minute=0)
    )
    state_before = services.tasks.state(project.id)
    assert state_before.status == RunStatus.RUNNING
    assert services.workspace.list_files(project.id)[0] == []

    # Storage helper can explicitly recover orphan pending tasks when caller knows no run is active.
    storage2 = SQLiteStorage(db_path)
    changed = storage2.recover_interrupted_tasks(project.id, include_pending=True)
    assert [(t.status) for t in changed] == ["failed", "skipped"]

    state_after = services.tasks.state(project.id)
    assert state_after.status == RunStatus.FAILED

    # Legitimate waiting_for_approval projects keep their queued pending tasks intact.
    waiting_proj = storage2.create_project("Waiting Approval")
    w1 = storage2.create_task(waiting_proj.id, "step", "run command")
    w2 = storage2.create_task(waiting_proj.id, "step", "after approval")
    storage2.save_execution(w1.id, "npm install", "pending_approval")
    storage2.update_task_status(w1.id, "waiting_for_approval")
    assert storage2.recover_interrupted_tasks(waiting_proj.id, include_pending=True) == []
    assert [(t.id, t.status) for t in storage2.list_tasks(waiting_proj.id)] == [
        (w1.id, "waiting_for_approval"),
        (w2.id, "pending"),
    ]


def test_k3_mismatch_noop_agent_marks_task_succeeded_without_execution_or_workspace_file(tmp_path):
    """Reproduces K3 mismatch #2 (TaskRunner):
    When an agent returns None on the very first next_action() call, TaskRunner marks the
    task 'succeeded' and TaskService reports project status 'completed' with zero execution
    records and zero workspace files.
    """
    settings = Settings(
        workspace_root=tmp_path / "workspaces",
        database_path=tmp_path / "noop.db",
        rate_limit_per_minute=0,
    )
    services = build_services(settings, agent=FixedPlanAgent())
    project = services.projects.create("Noop Project")
    chat = services.chat.handle(project.id, "Create a blog")

    assert chat.status == RunStatus.COMPLETED
    assert [t.status for t in chat.tasks] == [TaskStatus.SUCCEEDED, TaskStatus.SUCCEEDED]

    storage = SQLiteStorage(settings.database_path)
    assert storage.list_executions(project.id) == []
    assert services.workspace.list_files(project.id)[0] == []


def test_k3_mismatch_later_succeeded_task_masks_earlier_failed_task_in_project_status(tmp_path):
    """Reproduces K3 mismatch #3 (API compute_status in backend/api/services/tasks.py):
    compute_status() checks only tasks[-1].status for terminal states. If an earlier task
    failed (and its file is absent) and a subsequent task succeeded, TaskService.state()
    returns project status 'completed' despite the earlier failure.
    """
    db_path = tmp_path / "masked_failure.db"
    workspace_root = tmp_path / "workspaces"
    storage = SQLiteStorage(db_path)
    project = storage.create_project("Masked Failure")

    t1 = storage.create_task(project.id, "step", "Write index.html")
    storage.save_execution(t1.id, "write_file index.html", "failed", stderr="write failed")
    storage.update_task_status(t1.id, "failed")

    t2 = storage.create_task(project.id, "step", "Write style.css")
    storage.save_execution(t2.id, "write_file style.css", "succeeded", stdout="wrote style.css")
    storage.update_task_status(t2.id, "succeeded")

    services = build_services(
        Settings(workspace_root=workspace_root, database_path=db_path, rate_limit_per_minute=0)
    )
    state = services.tasks.state(project.id)
    assert [t.status for t in state.tasks] == [TaskStatus.FAILED, TaskStatus.SUCCEEDED]
    # Mismatch: project status is 'completed' even though Task 1 failed!
    assert state.status == RunStatus.COMPLETED


def test_k3_mismatch_partial_multitask_failure_leaves_earlier_index_html_previewable(tmp_path):
    """Reproduces K3 mismatch #4 (Partial multi-task site write):
    When Task 1 writes index.html ('succeeded') and Task 2 fails to write style.css
    ('failed', Task 3 'skipped'), project status is 'failed' and style.css does not exist,
    yet index.html remains in the workspace and WorkspaceService.has_index_html() is True.
    """
    agent = ScriptedAgent(
        ["Write index.html", "Write bad file", "Write script.js"],
        {
            "Write index.html": [
                {"type": "write_file", "path": "index.html", "content": "<h1>Partial</h1>"}
            ],
            "Write bad file": [
                {"type": "write_file", "path": "../escape.html", "content": "<p>bad</p>"}
            ],
            "Write script.js": [
                {"type": "write_file", "path": "script.js", "content": "console.log(1);"}
            ],
        },
    )
    settings = Settings(
        workspace_root=tmp_path / "workspaces",
        database_path=tmp_path / "partial.db",
        rate_limit_per_minute=0,
    )
    services = build_services(settings, agent=agent)
    project = services.projects.create("Partial Site")
    chat = services.chat.handle(project.id, "Create site")

    assert chat.status == RunStatus.FAILED
    assert [t.status for t in chat.tasks] == [
        TaskStatus.SUCCEEDED,
        TaskStatus.FAILED,
        TaskStatus.SKIPPED,
    ]
    files = [f.path for f in services.workspace.list_files(project.id)[0]]
    assert files == ["index.html"]
    # Mismatch: failed project still reports previewable index.html
    assert services.workspace.has_index_html(project.id) is True

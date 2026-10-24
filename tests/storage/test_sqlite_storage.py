"""SQLiteStorage against the StoragePort contract: persistence, updates, ordering, bad references."""
import pytest

from backend.storage.models import NotFoundError
from backend.storage.sqlite_storage import SQLiteStorage


@pytest.fixture
def storage(tmp_path):
    return SQLiteStorage(tmp_path / "s.db")


def test_records_persist_across_instances(tmp_path):
    first = SQLiteStorage(tmp_path / "s.db")
    project = first.create_project("Blog")
    task = first.create_task(project.id, "plan_step", "create project")
    first.update_task_status(task.id, "succeeded")

    second = SQLiteStorage(tmp_path / "s.db")  # reopening must not re-run migrations destructively
    assert second.get_project(project.id) == project
    assert second.list_projects() == [project]
    assert [(t.prompt, t.status) for t in second.list_tasks(project.id)] == [
        ("create project", "succeeded")
    ]


def test_integer_ids_increase_and_are_not_reused(storage):
    ids = [storage.create_project("p%d" % i).id for i in range(3)]
    assert ids == [1, 2, 3]


def test_session_and_task_defaults(storage):
    project = storage.create_project("Blog")
    session = storage.create_session(project.id)
    task = storage.create_task(project.id, "plan_step", "do it")
    assert (session.project_id, session.started_at.tzinfo is not None) == (project.id, True)
    assert (task.status, task.type, task.prompt) == ("pending", "plan_step", "do it")


def test_missing_records_return_none_and_bad_references_raise(storage):
    assert storage.get_project(9) is None
    assert storage.get_task(9) is None
    assert storage.get_execution(9) is None
    assert storage.get_pending_execution(9) is None
    assert storage.list_tasks(9) == []
    for call in (
        lambda: storage.create_session(9),
        lambda: storage.create_task(9, "t", "p"),
        lambda: storage.save_execution(9, "echo", "succeeded"),
        lambda: storage.update_task_status(9, "failed"),
        lambda: storage.update_execution(9, "failed"),
    ):
        with pytest.raises(NotFoundError):
            call()


def test_tasks_and_executions_are_scoped_to_their_project_and_ordered(storage):
    a, b = storage.create_project("A").id, storage.create_project("B").id
    ta1, tb, ta2 = (
        storage.create_task(a, "t", "a1"),
        storage.create_task(b, "t", "b1"),
        storage.create_task(a, "t", "a2"),
    )
    e1 = storage.save_execution(ta2.id, "one", "succeeded")
    storage.save_execution(tb.id, "other project", "succeeded")
    e3 = storage.save_execution(ta1.id, "three", "failed", stderr="x")
    e4 = storage.save_execution(ta1.id, "four", "succeeded")

    assert [t.prompt for t in storage.list_tasks(a)] == ["a1", "a2"]
    assert [e.id for e in storage.list_executions(a)] == [e1.id, e3.id, e4.id]
    assert [e.id for e in storage.list_executions(a, after_id=e1.id, limit=1)] == [e3.id]
    assert [e.id for e in storage.list_executions(a, task_id=ta1.id)] == [e3.id, e4.id]


def test_update_execution_changes_only_given_fields(storage):
    project = storage.create_project("A")
    task = storage.create_task(project.id, "t", "p")
    saved = storage.save_execution(
        task.id, "npm test", "pending_approval", reason="needs a human", retry_count=1
    )
    assert storage.get_pending_execution(project.id).id == saved.id

    updated = storage.update_execution(saved.id, "succeeded", stdout="ok", duration_ms=7)

    assert (updated.status, updated.stdout, updated.duration_ms) == ("succeeded", "ok", 7)
    assert (updated.retry_count, updated.reason, updated.stderr) == (1, "needs a human", "")
    assert updated.created_at == saved.created_at
    assert storage.get_pending_execution(project.id) is None


def test_status_enums_are_stored_as_their_values(storage):
    from backend.api.schemas.enums import TaskStatus

    project = storage.create_project("A")
    task = storage.create_task(project.id, "t", "p")
    assert storage.update_task_status(task.id, TaskStatus.SUCCEEDED).status == "succeeded"


def test_schema_version_is_recorded_and_migration_is_idempotent(tmp_path):
    import sqlite3

    SQLiteStorage(tmp_path / "s.db")
    SQLiteStorage(tmp_path / "s.db")
    version = sqlite3.connect(tmp_path / "s.db").execute("PRAGMA user_version").fetchone()[0]
    assert version == 1

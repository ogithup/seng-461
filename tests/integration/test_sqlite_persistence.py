"""Sprint 2 target: API -> agent -> SQLite -> API, and the same data after a restart."""
from fastapi.testclient import TestClient

from tests.integration.fakes import FixedPlanAgent
from backend.api.app import create_app
from backend.api.config import Settings
from backend.api.services.container import build_services


def restart(tmp_path, agent=None):
    """A brand-new application on the same database file, as after a process restart."""
    settings = Settings(
        workspace_root=tmp_path / "workspaces",
        database_path=tmp_path / "test.db",
        rate_limit_per_minute=0,
    )
    return TestClient(
        create_app(build_services(settings, agent=agent or FixedPlanAgent())),
        raise_server_exceptions=False,
    )


def test_project_and_tasks_survive_a_restart(make_app, tmp_path):
    app = make_app(agent=FixedPlanAgent())
    pid = app.project("Blog")
    chat = app.chat(pid, "Create a blog").json()
    assert [t["prompt"] for t in chat["tasks"]] == ["create project", "create index.html"]
    assert {t["status"] for t in chat["tasks"]} == {"succeeded"}
    before = app.client.get("/api/tasks", params={"project_id": pid}).json()
    project_before = app.client.get("/api/projects/%d" % pid).json()

    reborn = restart(tmp_path)

    assert reborn.get("/api/projects/%d" % pid).json() == project_before
    assert reborn.get("/api/projects").json() == [project_before]
    after = reborn.get("/api/tasks", params={"project_id": pid}).json()
    assert after == before
    assert after["status"] == "completed"


def test_work_continues_after_a_restart_without_reusing_ids(make_app, tmp_path):
    app = make_app(agent=FixedPlanAgent())
    pid = app.project()
    app.chat(pid, "Create a blog")

    reborn = restart(tmp_path)
    second = reborn.post("/api/chat", json={"project_id": pid, "message": "again"}).json()

    ids = [t["id"] for t in second["tasks"]]
    assert len(ids) == 4 and len(set(ids)) == 4
    other = reborn.post("/api/projects", json={"name": "Other"}).json()
    assert other["id"] != pid


def test_projects_do_not_share_tasks(make_app, tmp_path):
    app = make_app(agent=FixedPlanAgent())
    first, second = app.project("A"), app.project("B")
    app.chat(first, "Create a blog")
    app.chat(first, "Create a blog")
    app.chat(second, "Create a blog")

    reborn = restart(tmp_path)
    counts = {
        pid: len(reborn.get("/api/tasks", params={"project_id": pid}).json()["tasks"])
        for pid in (first, second)
    }
    assert counts == {first: 4, second: 2}


def test_pending_approval_survives_a_restart_and_can_be_approved(make_app, tmp_path):
    from tests.integration.fakes import RecordingExecutor, ScriptedAgent, run

    agent = ScriptedAgent(["install"], {"install": [run("npm install")]})
    app = make_app(agent=agent, executor=RecordingExecutor())
    pid = app.project()
    waiting = app.chat(pid).json()
    assert waiting["status"] == "waiting_for_approval"
    action_id = waiting["pending_action"]["id"]

    settings = Settings(
        workspace_root=tmp_path / "workspaces",
        database_path=tmp_path / "test.db",
        rate_limit_per_minute=0,
    )
    executor = RecordingExecutor()
    reborn = TestClient(
        create_app(build_services(settings, agent=ScriptedAgent(["install"]), executor=executor)),
        raise_server_exceptions=False,
    )

    state = reborn.get("/api/tasks", params={"project_id": pid}).json()
    assert state["status"] == "waiting_for_approval"
    assert state["pending_action"]["id"] == action_id

    approved = reborn.post("/api/actions/%d/approve" % action_id)
    assert approved.status_code == 200
    assert [(c.command, c.approved) for c in executor.calls] == [("npm install", True)]
    logs = reborn.get("/api/logs", params={"project_id": pid}).json()["entries"]
    assert [e["status"] for e in logs] == ["succeeded"]

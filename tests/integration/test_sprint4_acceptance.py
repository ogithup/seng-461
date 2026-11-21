"""Sprint 4 final acceptance (docs/sprint4-contracts.md, section 8) on the real modules.

Real agent, generator, executor and SQLite; nothing here is a mock response.
"""
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.config import Settings
from backend.api.services.container import build_services
from tests.integration.fakes import ScriptedAgent

PORTFOLIO = (
    "Create a portfolio for Ada Lovelace; pages: Projects, Contact; "
    "primary: #112233; font: serif"
)


def state(client, pid):
    return client.get("/api/tasks", params={"project_id": pid}).json()


def files(client, pid):
    body = client.get("/api/files", params={"project_id": pid}).json()
    return {f["path"] for f in body["files"]}


def text(client, pid, path):
    response = client.get("/api/files/content", params={"project_id": pid, "path": path})
    assert response.status_code == 200, response.text
    return response.json()["content"]


def restart(tmp_path, **kwargs):
    settings = Settings(
        workspace_root=tmp_path / "workspaces",
        database_path=tmp_path / "test.db",
        rate_limit_per_minute=0,
    )
    return TestClient(create_app(build_services(settings, **kwargs)), raise_server_exceptions=False)


def test_blog_then_portfolio_then_restart(make_app, tmp_path):
    app = make_app()
    client = app.client
    blog, portfolio = app.project("Sprint 4 Demo"), app.project("Portfolio")

    # 1-2. A supported blog is generated and every task is backed by a verified write.
    blog_state = app.chat(blog, "Create a blog called Sprint Notes").json()
    assert blog_state["status"] == "completed"
    assert {t["status"] for t in blog_state["tasks"]} == {"succeeded"}
    logs = client.get("/api/logs", params={"project_id": blog}).json()["entries"]
    assert len(logs) == len(blog_state["tasks"])
    for entry in logs:
        assert entry["status"] == "succeeded"
        assert (app.project_dir(blog) / entry["command"].split(" ", 1)[1]).is_file()

    # 3. Files can be inspected and the static preview opens.
    assert "Sprint Notes" in text(client, blog, "index.html")
    preview = client.get("/api/preview", params={"project_id": blog}).json()
    assert preview["status"] == "static"
    assert client.get(preview["url"]).status_code == 200

    # 4. A portfolio with requested pages and theme differs meaningfully from the blog.
    assert app.chat(portfolio, PORTFOLIO).json()["status"] == "completed"
    assert files(client, portfolio) != files(client, blog)
    assert {"projects.html", "contact.html"} <= files(client, portfolio)
    css = text(client, portfolio, "style.css")
    assert "#112233" in css.lower()
    assert "Ada Lovelace" in text(client, portfolio, "index.html")

    # 5. After a restart everything is still there and nothing is regenerated.
    before = {pid: (state(client, pid), files(client, pid)) for pid in (blog, portfolio)}
    reborn = restart(tmp_path)
    for pid in (blog, portfolio):
        assert state(reborn, pid) == before[pid][0]
        assert files(reborn, pid) == before[pid][1]
        assert reborn.get("/api/preview", params={"project_id": pid}).json()["status"] == "static"
    assert [p["id"] for p in reborn.get("/api/projects").json()] == [blog, portfolio]


def test_unsupported_request_is_reported_not_turned_into_a_site(make_app):
    app = make_app()
    pid = app.project()

    response = app.chat(pid, "Create an online shop")

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "unsupported_request"
    assert "not supported" in error["message"]
    assert state(app.client, pid)["tasks"] == []
    assert files(app.client, pid) == set()


def test_a_controlled_failure_is_never_reported_as_success(make_app):
    bad = {"type": "write_file", "path": "../outside.html", "content": "<p>x</p>"}
    app = make_app(agent=ScriptedAgent(["first", "second"], {"first": [bad]}))
    pid = app.project()

    body = app.chat(pid).json()

    assert body["status"] == "failed"
    assert [t["status"] for t in body["tasks"]] == ["failed", "skipped"]
    entry = app.client.get("/api/logs", params={"project_id": pid}).json()["entries"][0]
    assert entry["status"] == "failed" and entry["stderr"]
    assert files(app.client, pid) == set()


def test_interrupted_work_is_not_left_looking_successful(make_app, tmp_path):
    """A task stuck `running` when the process died must not come back as succeeded."""
    app = make_app()
    pid = app.project()
    app.chat(pid, "Create a blog")
    app.services.projects._storage.create_task(pid, "step", "never finished")
    task = app.services.projects._storage.list_tasks(pid)[-1]
    app.services.projects._storage.update_task_status(task.id, "running")

    reborn = restart(tmp_path)

    last = state(reborn, pid)["tasks"][-1]
    assert last["prompt"] == "never finished"
    assert last["status"] != "succeeded"
    assert state(reborn, pid)["status"] != "completed"


def test_message_with_an_unknown_field_is_rejected_cleanly(make_app):
    app = make_app()
    pid = app.project()
    response = app.chat(pid, "Create a blog; colour: blue")
    assert response.status_code >= 400
    assert "Traceback" not in response.text
    assert state(app.client, pid)["tasks"] == []

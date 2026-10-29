"""The Sprint 1/2 fixed-plan flow, pinned to the fixed planner (Sprint 3 default: see test_site_generation).

The Sprint 1 target: Create a blog -> frontend -> API -> fake agent -> fake task -> DB -> task shown."""


from tests.integration.fakes import FixedPlanAgent


def test_health(make_app):
    app = make_app()
    assert app.client.get("/api/health").json() == {"status": "ok"}


def test_create_project_returns_session_and_makes_workspace(make_app):
    app = make_app()
    response = app.client.post("/api/projects", json={"name": "  My Blog  "})
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "My Blog"
    assert body["session_id"] >= 1
    assert app.project_dir(body["id"]).is_dir()


def test_projects_can_be_listed_and_fetched(make_app):
    app = make_app()
    first, second = app.project("A"), app.project("B")
    assert [p["id"] for p in app.client.get("/api/projects").json()] == [first, second]
    assert app.client.get("/api/projects/%d" % second).json()["name"] == "B"


def test_chat_with_mock_agent_creates_tasks_that_get_tasks_returns(make_app):
    app = make_app(agent=FixedPlanAgent())
    pid = app.project()

    chat = app.chat(pid, "Create a blog")

    assert chat.status_code == 200
    body = chat.json()
    assert body["project_id"] == pid
    assert body["status"] == "completed"
    assert body["pending_action"] is None
    assert [t["prompt"] for t in body["tasks"]] == ["create project", "create index.html"]
    assert {t["status"] for t in body["tasks"]} == {"succeeded"}
    assert body["message"]

    listed = app.client.get("/api/tasks", params={"project_id": pid}).json()
    assert listed["tasks"] == body["tasks"]
    assert listed["status"] == "completed"


def test_new_project_has_no_tasks_and_is_idle(make_app):
    app = make_app()
    pid = app.project()
    state = app.client.get("/api/tasks", params={"project_id": pid}).json()
    assert state["tasks"] == []
    assert state["status"] == "idle"


def test_tasks_accumulate_across_chat_requests(make_app):
    app = make_app(agent=FixedPlanAgent())
    pid = app.project()
    app.chat(pid, "first")
    second = app.chat(pid, "second").json()
    assert len(second["tasks"]) == 4


def test_unknown_project_is_404_everywhere(make_app):
    app = make_app()
    for response in (
        app.chat(99),
        app.client.get("/api/tasks", params={"project_id": 99}),
        app.client.get("/api/logs", params={"project_id": 99}),
        app.client.get("/api/files", params={"project_id": 99}),
        app.client.get("/api/preview", params={"project_id": 99}),
        app.client.get("/api/projects/99"),
    ):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "project_not_found"

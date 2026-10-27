"""Verify Bejan's actual module through the API, rather than a stand-in."""

import pytest

from backend.agent import Orchestrator, plan


def test_fixed_plan_is_fresh_and_independent_of_request():
    first = plan("Create a blog")
    first.append("changed by caller")
    assert plan("Create a shop") == ["create project", "create index.html"]


@pytest.mark.parametrize("message", ["", " ", "\n\t"])
def test_empty_request_is_rejected(message):
    with pytest.raises(ValueError):
        plan(message)


def test_non_string_request_is_rejected():
    with pytest.raises(TypeError):
        plan(None)


def test_fake_agent_requests_no_execution():
    agent = Orchestrator()
    assert agent.next_action({"prompt": "create index.html"}, None) is None
    assert agent.next_action({}, {"success": False, "stderr": "retry me"}) is None


def test_default_api_uses_agent_and_exposes_stored_tasks(make_app, monkeypatch):
    calls = []
    original = Orchestrator.plan

    def observed_plan(self, message):
        calls.append(message)
        return original(self, message)

    monkeypatch.setattr(Orchestrator, "plan", observed_plan)
    app = make_app(agent=Orchestrator())
    project_id = app.project("Blog")
    response = app.chat(project_id, "Create a blog")
    assert response.status_code == 200
    assert calls == ["Create a blog"]
    body = response.json()
    assert body["status"] == "completed"
    assert body["pending_action"] is None
    assert [t["prompt"] for t in body["tasks"]] == [
        "create project", "create index.html"
    ]
    assert all(t["status"] == "succeeded" for t in body["tasks"])
    stored = app.client.get("/api/tasks", params={"project_id": project_id})
    assert stored.json()["tasks"] == body["tasks"]
    logs = app.client.get("/api/logs", params={"project_id": project_id}).json()
    assert logs["entries"] == []
    assert list(app.project_dir(project_id).iterdir()) == []

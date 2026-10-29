"""Verify Bejan's actual module through the API, rather than a stand-in."""

import pytest

from backend.agent import Orchestrator, plan


@pytest.mark.parametrize("message", ["", " ", "\n\t"])
def test_empty_request_is_rejected(message):
    with pytest.raises(ValueError):
        plan(message)


def test_non_string_request_is_rejected():
    with pytest.raises(TypeError):
        plan(None)


def test_default_api_uses_the_real_agent_and_exposes_stored_tasks(make_app, monkeypatch):
    calls = []
    original = Orchestrator.plan

    def observed_plan(self, message):
        calls.append(message)
        return original(self, message)

    monkeypatch.setattr(Orchestrator, "plan", observed_plan)
    app = make_app()
    project_id = app.project("Blog")
    response = app.chat(project_id, "Create a blog")
    assert response.status_code == 200
    assert calls == ["Create a blog"]
    body = response.json()
    assert body["status"] == "completed"
    assert body["pending_action"] is None
    assert [t["prompt"].split(" (")[0] for t in body["tasks"]][0] == "Write index.html"
    assert all(t["status"] == "succeeded" for t in body["tasks"])
    stored = app.client.get("/api/tasks", params={"project_id": project_id})
    assert stored.json()["tasks"] == body["tasks"]
    logs = app.client.get("/api/logs", params={"project_id": project_id}).json()
    assert len(logs["entries"]) == len(body["tasks"])
    assert (app.project_dir(project_id) / "index.html").is_file()

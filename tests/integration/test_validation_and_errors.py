import logging

from tests.integration.fakes import ScriptedAgent


def error_of(response):
    return response.json()["error"]


def test_empty_and_blank_messages_are_rejected(make_app):
    app = make_app()
    pid = app.project()
    for message in ("", "    "):
        response = app.chat(pid, message)
        assert response.status_code == 422
        assert error_of(response)["code"] == "validation_error"


def test_unknown_fields_are_rejected(make_app):
    app = make_app()
    pid = app.project()
    response = app.client.post(
        "/api/chat", json={"project_id": pid, "message": "hi", "owner_id": "someone-else"}
    )
    assert response.status_code == 422
    assert "owner_id" in error_of(response)["details"][0]["field"]


def test_overlong_message_is_rejected(make_app):
    app = make_app()
    pid = app.project()
    assert app.chat(pid, "x" * 4001).status_code == 422
    assert app.chat(pid, "x" * 4000).status_code == 200


def test_bad_identifiers_are_rejected(make_app):
    app = make_app()
    assert app.client.post("/api/chat", json={"project_id": 0, "message": "hi"}).status_code == 422
    assert app.client.post("/api/chat", json={"project_id": "abc", "message": "hi"}).status_code == 422
    assert app.client.get("/api/tasks", params={"project_id": -1}).status_code == 422
    assert app.client.get("/api/logs", params={"project_id": 1, "limit": 501}).status_code == 422


def test_control_characters_in_input_are_rejected(make_app):
    app = make_app()
    assert app.client.post("/api/projects", json={"name": "bad\nname"}).status_code == 422
    pid = app.project()
    assert app.chat(pid, "bad\x00message").status_code == 422
    assert app.chat(pid, "multi\nline\nmessage is fine").status_code == 200


def test_validation_errors_do_not_echo_the_input(make_app):
    app = make_app()
    secret = "sk-this-must-not-come-back"
    response = app.client.post("/api/chat", json={"project_id": "abc", "message": secret})
    assert response.status_code == 422
    assert secret not in response.text


def test_every_response_carries_a_request_id_that_matches_the_error_body(make_app):
    app = make_app()
    response = app.client.get("/api/tasks", params={"project_id": 7})
    assert response.headers["X-Request-ID"] == error_of(response)["request_id"]
    assert app.client.get("/api/health").headers["X-Request-ID"]


def test_unknown_route_uses_the_error_envelope(make_app):
    app = make_app()
    response = app.client.get("/api/nope")
    assert response.status_code == 404
    assert error_of(response)["code"] == "not_found"


def test_oversized_body_is_refused_before_parsing(make_app):
    app = make_app(max_request_body_bytes=200)
    response = app.client.post("/api/chat", content=b"x" * 500, headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    assert error_of(response)["code"] == "request_too_large"


def test_unexpected_failure_is_a_generic_500_without_internals(make_app, caplog):
    app = make_app()

    def explode(project_id):
        raise RuntimeError("db password is hunter2")

    app.services.projects._storage.get_project = explode
    with caplog.at_level(logging.ERROR, logger="backend.api"):
        response = app.client.get("/api/projects/1", headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 500
    assert error_of(response)["code"] == "internal_error"
    assert response.headers["X-Request-ID"] == error_of(response)["request_id"]
    # The browser must be able to read the error, so CORS headers still apply.
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "hunter2" not in response.text and "RuntimeError" not in response.text
    assert "hunter2" in caplog.text  # the detail is kept server-side


def test_agent_failure_while_planning_is_a_502_and_not_a_traceback(make_app):
    app = make_app(agent=ScriptedAgent([], plan_error=ValueError("llm key invalid: abc123")))
    pid = app.project()
    response = app.chat(pid)
    assert response.status_code == 502
    assert error_of(response)["code"] == "agent_error"
    assert error_of(response)["retryable"] is True
    assert error_of(response)["project_id"] == pid
    assert "abc123" not in response.text
    # Nothing half-created.
    assert app.client.get("/api/tasks", params={"project_id": pid}).json()["tasks"] == []


def test_empty_or_malformed_plan_is_a_502(make_app):
    for bad_plan in ([], ["  ", ""], "create index.html"):
        agent = ScriptedAgent([], plan_result=bad_plan)
        app = make_app(agent=agent)
        pid = app.project()
        response = app.chat(pid)
        assert response.status_code == 502, bad_plan
        assert error_of(response)["code"] in ("agent_empty_plan", "agent_error")


def test_plan_is_capped_to_max_steps(make_app):
    app = make_app(agent=ScriptedAgent(["step %d" % i for i in range(50)]), max_plan_steps=5)
    pid = app.project()
    assert len(app.chat(pid).json()["tasks"]) == 5


def test_cors_allows_the_frontend_origin_only(make_app):
    app = make_app()
    allowed = app.client.options(
        "/api/chat",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    denied = app.client.options(
        "/api/chat",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in denied.headers

def key(value="abc-123"):
    return {"Idempotency-Key": value}


def test_same_key_and_payload_replays_without_creating_a_second_project(make_app):
    app = make_app()
    first = app.client.post("/api/projects", json={"name": "Blog"}, headers=key())
    second = app.client.post("/api/projects", json={"name": "Blog"}, headers=key())

    assert first.status_code == second.status_code == 201
    assert second.json() == first.json()
    assert second.headers["Idempotent-Replay"] == "true"
    assert "Idempotent-Replay" not in first.headers
    assert len(app.client.get("/api/projects").json()) == 1


def test_same_key_with_a_different_payload_is_a_conflict(make_app):
    app = make_app()
    app.client.post("/api/projects", json={"name": "Blog"}, headers=key())
    response = app.client.post("/api/projects", json={"name": "Other"}, headers=key())
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_conflict"
    assert len(app.client.get("/api/projects").json()) == 1


def test_chat_replay_does_not_run_the_agent_twice(make_app):
    app = make_app()
    pid = app.project()
    first = app.chat(pid, headers=key("chat-1"))
    second = app.chat(pid, headers=key("chat-1"))
    assert second.json() == first.json()
    assert len(app.client.get("/api/tasks", params={"project_id": pid}).json()["tasks"]) == len(
        first.json()["tasks"]
    )


def test_keys_are_scoped_per_endpoint(make_app):
    app = make_app()
    assert app.client.post("/api/projects", json={"name": "A"}, headers=key("k")).status_code == 201
    pid = app.project("B")
    assert app.chat(pid, headers=key("k")).status_code == 200


def test_a_failed_request_does_not_burn_the_key(make_app):
    app = make_app()
    missing = app.chat(1, headers=key("retry-me"))
    assert missing.status_code == 404
    pid = app.project()
    assert pid == 1
    assert app.chat(pid, headers=key("retry-me")).status_code == 200


def test_malformed_key_is_rejected(make_app):
    app = make_app()
    response = app.client.post("/api/projects", json={"name": "A"}, headers=key("has spaces!"))
    assert response.status_code == 422


def test_key_can_be_required(make_app):
    app = make_app(require_idempotency_key=True)
    response = app.client.post("/api/projects", json={"name": "A"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "idempotency_key_required"
    assert app.client.post("/api/projects", json={"name": "A"}, headers=key()).status_code == 201


def test_submissions_are_rate_limited_but_replays_and_reads_are_not(make_app):
    app = make_app(rate_limit_per_minute=3)
    pid = app.project()
    assert app.chat(pid, headers=key("a")).status_code == 200
    assert app.chat(pid, headers=key("b")).status_code == 200  # 3rd hit: project + 2 chats

    limited = app.chat(pid, headers=key("c"))
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"
    assert limited.json()["error"]["retryable"] is True
    assert int(limited.headers["Retry-After"]) >= 1

    assert app.chat(pid, headers=key("a")).status_code == 200  # replay is free
    assert app.client.get("/api/tasks", params={"project_id": pid}).status_code == 200

    # The 429'd request did not leave its key stuck: it can be retried.
    assert app.chat(pid, headers=key("c")).status_code == 429

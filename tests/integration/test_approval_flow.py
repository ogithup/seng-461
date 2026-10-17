import threading

from tests.integration.fakes import RecordingExecutor, ScriptedAgent, fail, ok, run


def one_step(actions, **executor_kwargs):
    agent = ScriptedAgent(["step"], {"step": actions})
    executor = RecordingExecutor(**executor_kwargs)
    return agent, executor


def tasks_of(app, pid):
    return app.client.get("/api/tasks", params={"project_id": pid}).json()


def logs_of(app, pid, **params):
    return app.client.get("/api/logs", params={"project_id": pid, **params}).json()


# --- Level 1: allowlisted commands run on their own --------------------------------


def test_allowlisted_command_runs_without_asking(make_app):
    agent, executor = one_step([run("echo hello")], allowed=["echo hello"])
    app = make_app(agent=agent, executor=executor)
    pid = app.project()

    body = app.chat(pid).json()

    assert body["status"] == "completed"
    assert body["pending_action"] is None
    assert [(c.command, c.approved, c.requires_approval) for c in executor.calls] == [
        ("echo hello", False, False)
    ]
    # Runs inside this project's workspace, with a timeout.
    assert executor.calls[0].working_directory == str(app.project_dir(pid).resolve())
    assert executor.calls[0].timeout == 60
    entry = logs_of(app, pid)["entries"][0]
    assert (entry["command"], entry["status"], entry["stdout"]) == ("echo hello", "succeeded", "ok")
    assert entry["duration_ms"] == 5


def test_agent_can_demand_approval_even_for_an_allowlisted_command(make_app):
    agent, executor = one_step([run("npm test", requires_approval=True)], allowed=["npm test"])
    app = make_app(agent=agent, executor=executor)
    pid = app.project()

    body = app.chat(pid).json()

    assert body["status"] == "waiting_for_approval"
    assert executor.calls == []


def test_allowlist_check_failure_fails_closed(make_app):
    agent, executor = one_step([run("echo hello")], allowlist_error=RuntimeError("down"))
    app = make_app(agent=agent, executor=executor)
    pid = app.project()

    assert app.chat(pid).json()["status"] == "waiting_for_approval"
    assert executor.calls == []


# --- Level 2: everything else waits for a human ------------------------------------


def waiting_app(make_app, steps=("step",), script=None, **executor_kwargs):
    script = script or {"step": [run("npm install", reason="install dependencies")]}
    agent = ScriptedAgent(steps, script)
    executor = RecordingExecutor(**executor_kwargs)
    app = make_app(agent=agent, executor=executor)
    pid = app.project()
    body = app.chat(pid).json()
    return app, pid, agent, executor, body


def test_unlisted_command_parks_the_task_until_a_human_decides(make_app):
    app, pid, agent, executor, body = waiting_app(make_app)

    assert body["status"] == "waiting_for_approval"
    assert body["tasks"][0]["status"] == "waiting_for_approval"
    pending = body["pending_action"]
    assert pending["command"] == "npm install"
    assert pending["reason"] == "install dependencies"
    assert len(pending["command_hash"]) == 64
    assert pending["expires_at"] > pending["created_at"]
    assert "npm install" in body["message"]
    assert executor.calls == []  # nothing ran

    assert tasks_of(app, pid)["pending_action"] == pending
    entry = logs_of(app, pid)["entries"][0]
    assert (entry["id"], entry["status"]) == (pending["id"], "pending_approval")


def test_new_chat_is_refused_while_an_approval_is_pending(make_app):
    app, pid, *_ = waiting_app(make_app)
    response = app.chat(pid, "something else")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "pending_action_exists"


def test_approving_runs_exactly_that_command_and_continues_the_plan(make_app):
    app, pid, agent, executor, body = waiting_app(
        make_app,
        steps=("install", "next"),
        script={"install": [run("npm install")]},
    )
    action_id = body["pending_action"]["id"]
    assert [t["status"] for t in body["tasks"]] == ["waiting_for_approval", "pending"]

    response = app.client.post("/api/actions/%d/approve" % action_id)

    assert response.status_code == 200
    result = response.json()
    assert result["decision"] == "approved"
    assert result["status"] == "completed"
    assert result["pending_action"] is None
    assert [t["status"] for t in result["tasks"]] == ["succeeded", "succeeded"]
    assert [(c.command, c.approved) for c in executor.calls] == [("npm install", True)]
    # The agent saw the command's result before deciding the task was finished.
    install_calls = [last for prompt, last in agent.calls if prompt == "install"]
    assert install_calls[0] is None and install_calls[1].success is True
    assert logs_of(app, pid)["entries"][0]["status"] == "succeeded"


def test_approving_twice_does_not_run_the_command_twice(make_app):
    app, pid, agent, executor, body = waiting_app(make_app)
    action_id = body["pending_action"]["id"]

    first = app.client.post("/api/actions/%d/approve" % action_id)
    second = app.client.post("/api/actions/%d/approve" % action_id)

    assert first.status_code == second.status_code == 200
    assert "already approved" in second.json()["message"]
    assert len(executor.calls) == 1


def test_approve_with_the_matching_hash_works_and_a_stale_hash_is_refused(make_app):
    app, pid, agent, executor, body = waiting_app(make_app)
    pending = body["pending_action"]

    stale = app.client.post(
        "/api/actions/%d/approve" % pending["id"], json={"command_hash": "0" * 64}
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "approval_mismatch"
    assert executor.calls == []
    assert tasks_of(app, pid)["status"] == "waiting_for_approval"

    good = app.client.post(
        "/api/actions/%d/approve" % pending["id"], json={"command_hash": pending["command_hash"]}
    )
    assert good.status_code == 200
    assert len(executor.calls) == 1


def test_malformed_hash_and_unknown_body_fields_are_rejected(make_app):
    app, pid, agent, executor, body = waiting_app(make_app)
    url = "/api/actions/%d/approve" % body["pending_action"]["id"]
    assert app.client.post(url, json={"command_hash": "nope"}).status_code == 422
    assert app.client.post(url, json={"command": "rm -rf /"}).status_code == 422
    assert executor.calls == []


def test_rejecting_cancels_the_task_and_the_rest_of_the_plan(make_app):
    app, pid, agent, executor, body = waiting_app(
        make_app, steps=("install", "next"), script={"install": [run("npm install")]}
    )
    action_id = body["pending_action"]["id"]

    response = app.client.post("/api/actions/%d/reject" % action_id)

    assert response.status_code == 200
    result = response.json()
    assert result["decision"] == "rejected"
    assert result["status"] == "cancelled"
    assert [t["status"] for t in result["tasks"]] == ["cancelled", "cancelled"]
    assert executor.calls == []
    assert logs_of(app, pid)["entries"][0]["status"] == "rejected"

    # Rejecting again is a harmless repeat; approving afterwards is a conflict.
    assert app.client.post("/api/actions/%d/reject" % action_id).status_code == 200
    late = app.client.post("/api/actions/%d/approve" % action_id)
    assert late.status_code == 409
    assert late.json()["error"]["code"] == "action_already_decided"
    assert executor.calls == []

    # The project is usable again.
    assert app.chat(pid).status_code == 200


def test_an_unanswered_approval_expires_and_can_no_longer_be_approved(make_app):
    app, pid, agent, executor, body = waiting_app(make_app)  # default TTL: 900 seconds
    action_id = body["pending_action"]["id"]

    app.clock.advance(seconds=899)
    assert tasks_of(app, pid)["pending_action"] is not None  # not yet
    app.clock.advance(seconds=2)
    response = app.client.post("/api/actions/%d/approve" % action_id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "action_expired"
    assert executor.calls == []
    state = tasks_of(app, pid)
    assert state["pending_action"] is None
    assert state["tasks"][0]["status"] == "cancelled"
    assert logs_of(app, pid)["entries"][0]["status"] == "expired"
    assert app.client.post("/api/actions/%d/approve" % action_id).status_code == 409


def test_an_expired_approval_does_not_block_the_project_forever(make_app):
    app, pid, agent, executor, body = waiting_app(make_app)
    app.clock.advance(hours=1)

    assert tasks_of(app, pid)["pending_action"] is None  # reading is enough to expire it
    agent.script["step"] = []
    assert app.chat(pid).status_code == 200


def test_unknown_action_is_404(make_app):
    app = make_app()
    for verb in ("approve", "reject"):
        response = app.client.post("/api/actions/42/%s" % verb)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "action_not_found"
    assert app.client.post("/api/actions/0/approve").status_code == 422


def test_a_failing_approved_command_lets_the_agent_repair(make_app):
    app, pid, agent, executor, body = waiting_app(
        make_app,
        script={"step": [run("npm install"), run("npm install --legacy-peer-deps")]},
        results=[fail("ERESOLVE")],
    )
    action_id = body["pending_action"]["id"]

    response = app.client.post("/api/actions/%d/approve" % action_id).json()

    # The agent's repair command is new, unlisted, so it waits for its own approval.
    assert response["status"] == "waiting_for_approval"
    assert response["pending_action"]["command"] == "npm install --legacy-peer-deps"
    assert response["pending_action"]["id"] != action_id
    assert agent.calls[-1][1].success is False and agent.calls[-1][1].stderr == "ERESOLVE"


# --- bounded loops ------------------------------------------------------------------


def test_repair_attempts_are_capped_and_later_steps_are_skipped(make_app):
    agent = ScriptedAgent(
        ["flaky", "after"], {"flaky": [run("npm test")] * 10, "after": [run("npm test")]}
    )
    executor = RecordingExecutor(allowed=["npm test"], results=[fail()] * 10)
    app = make_app(agent=agent, executor=executor)
    pid = app.project()

    body = app.chat(pid).json()

    assert len(executor.calls) == 3  # the first try plus 2 repair attempts
    assert [t["status"] for t in body["tasks"]] == ["failed", "skipped"]
    assert body["status"] == "failed"
    assert [e["status"] for e in logs_of(app, pid)["entries"]] == ["failed"] * 3


def test_actions_per_task_are_capped(make_app):
    agent = ScriptedAgent(["endless"], {"endless": [run("echo hello")] * 50})
    executor = RecordingExecutor(allowed=["echo hello"])
    app = make_app(agent=agent, executor=executor, max_actions_per_task=4)
    pid = app.project()

    body = app.chat(pid).json()

    assert len(executor.calls) == 4
    assert body["tasks"][0]["status"] == "failed"


def test_agent_giving_up_after_a_failure_fails_the_task(make_app):
    agent, executor = one_step([run("npm test")], allowed=["npm test"], results=[fail()])
    app = make_app(agent=agent, executor=executor)
    pid = app.project()

    body = app.chat(pid).json()

    assert body["tasks"][0]["status"] == "failed"


def test_malformed_agent_actions_fail_the_task_without_running_anything(make_app):
    bad_actions = [
        run("echo hi\nrm -rf /"),  # a second command smuggled in through a newline
        {"type": "write_file", "command": "x"},  # not a supported action type
        run("echo hi", sudo=True),  # unknown field
        run(""),
    ]
    for bad in bad_actions:
        agent, executor = one_step([bad], allowed=["echo hi"])
        app = make_app(agent=agent, executor=executor)
        pid = app.project()
        body = app.chat(pid).json()
        assert body["tasks"][0]["status"] == "failed", bad
        assert executor.calls == [], bad


def test_executor_crash_becomes_a_failed_execution_without_leaking_details(make_app):
    agent, executor = one_step(
        [run("echo hello")], allowed=["echo hello"], run_error=RuntimeError("secret path /etc/x")
    )
    app = make_app(agent=agent, executor=executor)
    pid = app.project()

    body = app.chat(pid).json()

    assert body["tasks"][0]["status"] == "failed"
    entry = logs_of(app, pid)["entries"][0]
    assert entry["status"] == "failed"
    assert "secret path" not in entry["stderr"]


def test_agent_crash_mid_task_fails_that_task(make_app):
    class Crashy(ScriptedAgent):
        def next_action(self, task, last_result):
            raise RuntimeError("model timeout")

    app = make_app(agent=Crashy(["a", "b"]), executor=RecordingExecutor())
    pid = app.project()
    body = app.chat(pid).json()
    assert [t["status"] for t in body["tasks"]] == ["failed", "skipped"]


def test_second_request_while_the_agent_is_busy_gets_a_retryable_409(make_app):
    started, release = threading.Event(), threading.Event()

    class Slow(ScriptedAgent):
        def plan(self, user_request):
            started.set()
            release.wait(timeout=10)
            return ["step"]

    app = make_app(agent=Slow([]), executor=RecordingExecutor())
    pid = app.project()
    first = {}
    worker = threading.Thread(target=lambda: first.update(response=app.chat(pid)))
    worker.start()
    try:
        assert started.wait(timeout=10)
        busy = app.chat(pid, "again")
        assert busy.status_code == 409
        assert busy.json()["error"]["code"] == "project_busy"
        assert busy.json()["error"]["retryable"] is True
    finally:
        release.set()
        worker.join(timeout=10)
    assert first["response"].status_code == 200


def test_other_projects_are_not_blocked_by_a_pending_approval(make_app):
    app, pid, agent, executor, body = waiting_app(make_app)
    other = app.project("Other")
    agent.script["step"] = []
    assert app.chat(other).json()["status"] == "completed"
    assert tasks_of(app, pid)["status"] == "waiting_for_approval"

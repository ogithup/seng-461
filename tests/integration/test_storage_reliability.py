"""Integration tests for restart recovery, durable idempotency, and project workspace isolation."""
import os
import pytest
from fastapi.testclient import TestClient

from backend.agent import Orchestrator
from backend.api.app import create_app
from backend.api.config import Settings
from backend.api.services.container import build_services


def restart_app(tmp_path, agent=None):
    """Re-instantiate a brand-new application on the same workspace and database path."""
    settings = Settings(
        workspace_root=tmp_path / "workspaces",
        database_path=tmp_path / "app.db",
        rate_limit_per_minute=0,
    )
    return TestClient(
        create_app(build_services(settings, agent=agent or Orchestrator())),
        raise_server_exceptions=False,
    )


# --- Restart-Recovery Tests -------------------------------------------------------------


def test_restart_recovery_preserves_history_logs_and_preview(make_app, tmp_path):
    """After backend restart:

    - Project record is intact
    - Tasks and completed statuses are preserved
    - Execution logs and command output are preserved
    - Workspace generated files and preview endpoint (/api/preview) remain accessible
    """
    settings = Settings(
        workspace_root=tmp_path / "workspaces",
        database_path=tmp_path / "app.db",
        rate_limit_per_minute=0,
    )
    client1 = TestClient(create_app(build_services(settings)), raise_server_exceptions=False)

    # 1. Create project and trigger chat
    p_resp = client1.post("/api/projects", json={"name": "Portfolio Website"}).json()
    pid = p_resp["id"]
    chat_resp = client1.post("/api/chat", json={"project_id": pid, "message": "portfolio site"}).json()

    assert chat_resp["status"] in ("completed", "idle")
    tasks_before = client1.get("/api/tasks", params={"project_id": pid}).json()
    logs_before = client1.get("/api/logs", params={"project_id": pid}).json()
    files_before = client1.get("/api/files", params={"project_id": pid}).json()
    preview_before = client1.get("/api/preview", params={"project_id": pid}).json()

    # Verify site files were generated
    assert len(files_before["files"]) > 0
    assert any(f["path"] == "index.html" for f in files_before["files"])
    assert preview_before["status"] == "static"
    index_content_before = client1.get("/api/preview/%d/" % pid).text

    # 2. Simulate complete process restart with new client on same DB & workspace
    client2 = restart_app(tmp_path)

    # 3. Verify project history and state
    p_after = client2.get("/api/projects/%d" % pid).json()
    assert p_after["id"] == pid
    assert p_after["name"] == "Portfolio Website"

    tasks_after = client2.get("/api/tasks", params={"project_id": pid}).json()
    assert tasks_after == tasks_before

    # 4. Verify completed task evidence / logs
    logs_after = client2.get("/api/logs", params={"project_id": pid}).json()
    assert len(logs_after["entries"]) == len(logs_before["entries"])
    assert [e["stdout"] for e in logs_after["entries"]] == [e["stdout"] for e in logs_before["entries"]]

    # 5. Verify website files and preview accessibility after restart
    files_after = client2.get("/api/files", params={"project_id": pid}).json()
    assert files_after == files_before

    preview_after = client2.get("/api/preview", params={"project_id": pid}).json()
    assert preview_after["status"] == "static"
    assert preview_after["url"] == "/api/preview/%d/" % pid
    index_content_after = client2.get("/api/preview/%d/" % pid).text
    assert index_content_after == index_content_before


# --- Durable Idempotency Tests (Across Restart) -----------------------------------------


def test_durable_idempotency_survives_restart_and_prevents_duplicate_execution(tmp_path):
    """An API request retried after a process restart returns the stored response

    with 'Idempotent-Replay' header without executing tasks or generating duplicate records.
    """
    settings = Settings(
        workspace_root=tmp_path / "workspaces",
        database_path=tmp_path / "app.db",
        rate_limit_per_minute=0,
    )
    client1 = TestClient(create_app(build_services(settings)), raise_server_exceptions=False)

    p_resp = client1.post("/api/projects", json={"name": "Blog Site"}, headers={"Idempotency-Key": "proj-key-1"})
    assert p_resp.status_code == 201
    pid = p_resp.json()["id"]

    # Initial chat execution with idempotency key
    first_chat = client1.post(
        "/api/chat",
        json={"project_id": pid, "message": "create blog"},
        headers={"Idempotency-Key": "chat-key-1"},
    )
    assert first_chat.status_code == 200
    assert "Idempotent-Replay" not in first_chat.headers
    first_body = first_chat.json()
    initial_tasks_count = len(first_body["tasks"])
    logs_count_before = len(client1.get("/api/logs", params={"project_id": pid}).json()["entries"])

    # Backend restart
    client2 = restart_app(tmp_path)

    # Retry exact same chat request with same key
    replay_chat = client2.post(
        "/api/chat",
        json={"project_id": pid, "message": "create blog"},
        headers={"Idempotency-Key": "chat-key-1"},
    )
    assert replay_chat.status_code == 200
    assert replay_chat.headers.get("Idempotent-Replay") == "true"
    assert replay_chat.json() == first_body

    # Verify no duplicate tasks or duplicate execution logs were added
    tasks_after = client2.get("/api/tasks", params={"project_id": pid}).json()["tasks"]
    assert len(tasks_after) == initial_tasks_count

    logs_after = client2.get("/api/logs", params={"project_id": pid}).json()["entries"]
    assert len(logs_after) == logs_count_before

    # Retry same key with a different message -> 409 conflict
    conflict_chat = client2.post(
        "/api/chat",
        json={"project_id": pid, "message": "different message"},
        headers={"Idempotency-Key": "chat-key-1"},
    )
    assert conflict_chat.status_code == 409
    assert conflict_chat.json()["error"]["code"] == "idempotency_conflict"


# --- Project Workspace Isolation Tests --------------------------------------------------


def test_project_workspace_isolation_and_path_traversal(make_app, tmp_path):
    """Ensure projects cannot read, write, or access files belonging to other projects."""
    app = make_app()
    pid1 = app.project("Project 1")
    pid2 = app.project("Project 2")

    # Write files in Project 1 and Project 2 workspaces
    dir1 = app.project_dir(pid1)
    dir2 = app.project_dir(pid2)
    dir1.mkdir(parents=True, exist_ok=True)
    dir2.mkdir(parents=True, exist_ok=True)

    (dir1 / "index.html").write_text("<h1>Project 1</h1>", encoding="utf-8")
    (dir2 / "secret.txt").write_text("p2-secret-data", encoding="utf-8")

    # 1. Project 1 attempts to read Project 2's file using directory traversal
    traversal_read = app.client.get(
        "/api/files/content", params={"project_id": pid1, "path": "../project_%d/secret.txt" % pid2}
    )
    assert traversal_read.status_code == 403
    assert "p2-secret-data" not in traversal_read.text

    # 2. Project 1 attempts absolute path to Project 2
    abs_path = str((dir2 / "secret.txt").resolve())
    abs_read = app.client.get(
        "/api/files/content", params={"project_id": pid1, "path": abs_path}
    )
    assert abs_read.status_code == 403
    assert "p2-secret-data" not in abs_read.text

    # 3. Project 1 attempts preview access to Project 2's file (both path collapse and encoded traversal)
    preview_escape = app.client.get("/api/preview/%d/../project_%d/secret.txt" % (pid1, pid2))
    assert preview_escape.status_code in (403, 404, 422)
    assert "p2-secret-data" not in preview_escape.text

    preview_escape_encoded = app.client.get("/api/preview/%d/..%%2Fproject_%d/secret.txt" % (pid1, pid2))
    assert preview_escape_encoded.status_code in (403, 404, 422)
    assert "p2-secret-data" not in preview_escape_encoded.text

    # 4. Symlink from Project 1 pointing to Project 2 is blocked and omitted from listings
    link = dir1 / "link_to_p2"
    try:
        os.symlink(str(dir2), str(link))
        symlink_read = app.client.get(
            "/api/files/content", params={"project_id": pid1, "path": "link_to_p2/secret.txt"}
        )
        assert symlink_read.status_code == 403
        assert "p2-secret-data" not in symlink_read.text

        listed_files = app.client.get("/api/files", params={"project_id": pid1}).json()["files"]
        assert not any("secret.txt" in f["path"] for f in listed_files)
    except (OSError, NotImplementedError):
        pass  # Symlink creation privilege not available on current Windows account

    # 5. Accessing nonexistent project returns 404
    nonexistent_read = app.client.get("/api/files", params={"project_id": 9999})
    assert nonexistent_read.status_code == 404
    assert nonexistent_read.json()["error"]["code"] == "project_not_found"

    # 6. Task and execution scoping isolation
    app.chat(pid1, "test")
    p1_tasks = app.client.get("/api/tasks", params={"project_id": pid1}).json()["tasks"]
    p2_tasks = app.client.get("/api/tasks", params={"project_id": pid2}).json()["tasks"]
    assert len(p1_tasks) > 0
    assert len(p2_tasks) == 0

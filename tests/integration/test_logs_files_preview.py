import os

import pytest

from backend.api.errors import ApiError
from tests.integration.fakes import RecordingExecutor, ScriptedAgent, ok, run


def write(app, pid, relative, content="hello"):
    path = app.project_dir(pid) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


# --- logs ----------------------------------------------------------------------------


def logging_app(make_app, count, **settings):
    agent = ScriptedAgent(["s"], {"s": [run("echo hello")] * count})
    executor = RecordingExecutor(allowed=["echo hello"], results=[ok("out %d" % i) for i in range(count)])
    app = make_app(agent=agent, executor=executor, **settings)
    pid = app.project()
    app.chat(pid)
    return app, pid


def test_logs_page_forward_with_a_cursor(make_app):
    app, pid = logging_app(make_app, 5)

    first = app.client.get("/api/logs", params={"project_id": pid, "limit": 2}).json()
    assert [e["stdout"] for e in first["entries"]] == ["out 0", "out 1"]

    second = app.client.get(
        "/api/logs", params={"project_id": pid, "limit": 10, "after_id": first["next_after_id"]}
    ).json()
    assert [e["stdout"] for e in second["entries"]] == ["out 2", "out 3", "out 4"]

    nothing_new = app.client.get(
        "/api/logs", params={"project_id": pid, "after_id": second["next_after_id"]}
    ).json()
    assert nothing_new["entries"] == []
    assert nothing_new["next_after_id"] == second["next_after_id"]


def test_log_output_is_truncated_and_flagged(make_app):
    agent = ScriptedAgent(["s"], {"s": [run("echo hello")]})
    executor = RecordingExecutor(allowed=["echo hello"], results=[ok("x" * 500)])
    app = make_app(agent=agent, executor=executor, max_log_output_chars=100)
    pid = app.project()
    app.chat(pid)

    entry = app.client.get("/api/logs", params={"project_id": pid}).json()["entries"][0]
    assert len(entry["stdout"]) == 100
    assert entry["output_truncated"] is True


# --- files ---------------------------------------------------------------------------


def test_files_are_listed_without_hidden_or_dependency_folders(make_app):
    app = make_app()
    pid = app.project()
    write(app, pid, "index.html", "<h1>hi</h1>")
    write(app, pid, "src/app.js", "x")
    write(app, pid, ".env", "SECRET=1")
    write(app, pid, ".git/config", "x")
    write(app, pid, "node_modules/pkg/index.js", "x")

    body = app.client.get("/api/files", params={"project_id": pid}).json()

    assert [(f["path"], f["size"]) for f in body["files"]] == [("index.html", 11), ("src/app.js", 1)]
    assert body["truncated"] is False


def test_file_list_is_capped(make_app):
    app = make_app(max_listed_files=2)
    pid = app.project()
    for name in "abc":
        write(app, pid, name + ".txt")
    body = app.client.get("/api/files", params={"project_id": pid}).json()
    assert len(body["files"]) == 2 and body["truncated"] is True


def test_file_content_is_returned(make_app):
    app = make_app()
    pid = app.project()
    write(app, pid, "src/app.js", "console.log('é')")
    body = app.client.get(
        "/api/files/content", params={"project_id": pid, "path": "src/app.js"}
    ).json()
    assert body == {"project_id": pid, "path": "src/app.js", "size": 17, "content": "console.log('é')"}


@pytest.mark.parametrize(
    "path",
    [
        "../secret.txt",
        "src/../../secret.txt",
        "..\\secret.txt",
        "/etc/passwd",
        "C:/Windows/win.ini",
        "C:\\Windows\\win.ini",
        ".env",
        "src/.hidden/x",
        "node_modules/x.js",
        "a\x00b",
    ],
)
def test_paths_outside_the_workspace_or_hidden_are_forbidden(make_app, path):
    app = make_app()
    pid = app.project()
    write(app, pid, ".env", "SECRET=1")
    (app.workspace / "secret.txt").write_text("top secret")

    with pytest.raises(ApiError) as caught:
        app.services.workspace.resolve(pid, path)
    assert caught.value.status_code == 403
    assert caught.value.code == "path_not_allowed"

    response = app.client.get("/api/files/content", params={"project_id": pid, "path": path})
    assert response.status_code == 403
    assert "top secret" not in response.text and "SECRET=1" not in response.text


def test_a_symlink_pointing_outside_the_workspace_is_forbidden(make_app):
    app = make_app()
    pid = app.project()
    outside = app.workspace / "outside.txt"
    outside.write_text("top secret")
    link = app.project_dir(pid) / "link.txt"
    try:
        os.symlink(str(outside), str(link))
    except (OSError, NotImplementedError):
        pytest.skip("this account cannot create symlinks")

    response = app.client.get("/api/files/content", params={"project_id": pid, "path": "link.txt"})
    assert response.status_code == 403
    assert "top secret" not in response.text
    listed = app.client.get("/api/files", params={"project_id": pid}).json()
    assert listed["files"] == []


@pytest.mark.skipif(os.name != "nt", reason="directory junctions exist only on Windows")
def test_a_directory_junction_pointing_outside_is_neither_listed_nor_readable(make_app):
    # Junctions need no privileges on Windows, and Python < 3.12 does not report them via
    # is_symlink(), so a naive os.walk would follow them out of the workspace.
    import subprocess

    app = make_app()
    pid = app.project()
    outside = app.workspace / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("top secret")
    junction = app.project_dir(pid) / "linked"
    made = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)], capture_output=True
    )
    if made.returncode != 0:
        pytest.skip("could not create a junction: %s" % made.stderr)

    listed = app.client.get("/api/files", params={"project_id": pid}).json()
    assert listed["files"] == []
    read = app.client.get(
        "/api/files/content", params={"project_id": pid, "path": "linked/secret.txt"}
    )
    assert read.status_code == 403
    assert "top secret" not in read.text


def test_missing_oversized_and_binary_files_have_their_own_errors(make_app):
    app = make_app(max_file_bytes=100)
    pid = app.project()
    write(app, pid, "big.txt", "x" * 101)
    write(app, pid, "image.bin", b"\xff\xfe\x00\x01")
    (app.project_dir(pid) / "dir").mkdir()

    def read(path):
        return app.client.get("/api/files/content", params={"project_id": pid, "path": path})

    assert (read("nope.txt").status_code, read("nope.txt").json()["error"]["code"]) == (404, "file_not_found")
    assert read("dir").status_code == 404
    assert (read("big.txt").status_code, read("big.txt").json()["error"]["code"]) == (413, "file_too_large")
    assert (read("image.bin").status_code, read("image.bin").json()["error"]["code"]) == (415, "unsupported_file_type")


# --- preview -------------------------------------------------------------------------


def test_preview_is_unavailable_until_the_project_has_an_index_html(make_app):
    app = make_app()
    pid = app.project()
    assert app.client.get("/api/preview", params={"project_id": pid}).json() == {
        "project_id": pid,
        "status": "unavailable",
        "url": None,
    }

    write(app, pid, "index.html", "<h1>hello</h1>")
    body = app.client.get("/api/preview", params={"project_id": pid}).json()
    assert body["status"] == "static"
    assert body["url"] == "/api/preview/%d/" % pid


def test_preview_is_served_sandboxed(make_app):
    app = make_app()
    pid = app.project()
    write(app, pid, "index.html", "<h1>hello</h1>")
    write(app, pid, "static/style.css", "h1{color:red}")

    page = app.client.get("/api/preview/%d/" % pid)
    assert page.status_code == 200
    assert page.text == "<h1>hello</h1>"
    assert page.headers["content-type"].startswith("text/html")
    assert page.headers["content-security-policy"] == "sandbox allow-scripts"
    assert page.headers["x-content-type-options"] == "nosniff"

    css = app.client.get("/api/preview/%d/static/style.css" % pid)
    assert css.headers["content-type"].startswith("text/css")


def test_preview_will_not_serve_hidden_missing_or_escaping_paths(make_app):
    app = make_app()
    pid = app.project()
    write(app, pid, "index.html", "x")
    write(app, pid, ".env", "SECRET=1")
    (app.workspace / "secret.txt").write_text("top secret")

    assert app.client.get("/api/preview/%d/.env" % pid).status_code == 403
    assert app.client.get("/api/preview/%d/missing.js" % pid).status_code == 404
    escape = app.client.get("/api/preview/%d/..%%2F..%%2Fsecret.txt" % pid)
    assert escape.status_code in (403, 404)
    assert "top secret" not in escape.text
    with pytest.raises(ApiError):
        app.services.workspace.preview_file(pid, "../secret.txt")

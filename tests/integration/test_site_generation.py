"""Sprint 3 target: a request becomes real files on disk, recorded from verified results."""
import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.config import Settings
from backend.api.services.container import build_services
from backend.integration.reference_generator import ReferenceSiteGenerator
from backend.integration.site_agent import SiteAgent
from tests.integration.fakes import ScriptedAgent


def files_of(app, pid):
    body = app.client.get("/api/files", params={"project_id": pid}).json()
    return {f["path"]: f["size"] for f in body["files"]}


def content_of(app, pid, path):
    response = app.client.get("/api/files/content", params={"project_id": pid, "path": path})
    assert response.status_code == 200, response.text
    return response.json()["content"]


def test_blog_request_generates_a_previewable_static_site(make_app):
    app = make_app()
    pid = app.project("Blog")

    body = app.chat(pid, "Create a blog called Travel Notes").json()

    assert body["status"] == "completed"
    assert {t["status"] for t in body["tasks"]} == {"succeeded"}
    assert [t["prompt"] for t in body["tasks"]][0].startswith("Write index.html")
    assert set(files_of(app, pid)) == {"index.html", "about.html", "style.css", "script.js"}
    assert "Travel Notes" in content_of(app, pid, "index.html")
    assert 'href="about.html"' in content_of(app, pid, "index.html")

    preview = app.client.get("/api/preview", params={"project_id": pid}).json()
    assert preview["status"] == "static"
    page = app.client.get(preview["url"])
    assert page.status_code == 200 and "Travel Notes" in page.text
    assert app.client.get("/api/preview/%d/style.css" % pid).status_code == 200


def test_every_task_is_backed_by_a_verified_execution_record(make_app):
    app = make_app()
    pid = app.project()
    tasks = app.chat(pid, "Create a blog").json()["tasks"]

    entries = app.client.get("/api/logs", params={"project_id": pid}).json()["entries"]

    assert len(entries) == len(tasks)
    assert {e["status"] for e in entries} == {"succeeded"}
    for entry in entries:
        assert entry["command"].startswith("write_file ")
        path = entry["command"].split(" ", 1)[1]
        assert entry["stdout"].startswith("wrote %s (" % path)
        assert (app.project_dir(pid) / path).is_file()


def test_blog_and_portfolio_requests_make_different_sites(make_app):
    app = make_app()
    blog, portfolio = app.project("B"), app.project("P")

    app.chat(blog, "Create a blog")
    app.chat(portfolio, "Build me a portfolio for Ada Lovelace")

    assert set(files_of(app, blog)) != set(files_of(app, portfolio))
    assert "projects.html" in files_of(app, portfolio)
    assert "Ada Lovelace" in content_of(app, portfolio, "index.html")
    assert "Ada Lovelace" not in content_of(app, blog, "index.html")


def test_generated_pages_are_responsive_and_link_to_real_files(make_app):
    app = make_app()
    pid = app.project()
    app.chat(pid, "Create a landing page for Acme")
    generator = ReferenceSiteGenerator()
    site = {path: content_of(app, pid, path) for path in files_of(app, pid)}
    assert generator.validate(site) == []
    assert "@media" in site["style.css"]


def test_projects_do_not_share_files(make_app):
    app = make_app()
    first, second = app.project("A"), app.project("B")
    app.chat(first, "Create a blog called Alpha")
    app.chat(second, "Create a blog called Beta")
    assert "Alpha" in content_of(app, first, "index.html")
    assert "Beta" in content_of(app, second, "index.html")
    assert "Alpha" not in content_of(app, second, "index.html")


def test_site_survives_a_backend_restart(make_app, tmp_path):
    app = make_app()
    pid = app.project()
    before = app.chat(pid, "Create a blog").json()["tasks"]

    settings = Settings(
        workspace_root=tmp_path / "workspaces",
        database_path=tmp_path / "test.db",
        rate_limit_per_minute=0,
    )
    reborn = TestClient(create_app(build_services(settings)), raise_server_exceptions=False)

    assert reborn.get("/api/tasks", params={"project_id": pid}).json()["tasks"] == before
    assert reborn.get("/api/preview", params={"project_id": pid}).json()["status"] == "static"
    assert "index.html" in {
        f["path"] for f in reborn.get("/api/files", params={"project_id": pid}).json()["files"]
    }


# --- Failures are reported as failures --------------------------------------------


def test_unsafe_path_from_the_agent_fails_the_task_and_writes_nothing(make_app, tmp_path):
    action = {"type": "write_file", "path": "../escape.html", "content": "<p>x</p>"}
    app = make_app(agent=ScriptedAgent(["bad"], {"bad": [action]}))
    pid = app.project()

    body = app.chat(pid).json()

    assert body["status"] == "failed"
    assert [t["status"] for t in body["tasks"]] == ["failed"]
    assert not (tmp_path / "workspaces" / "escape.html").exists()
    entry = app.client.get("/api/logs", params={"project_id": pid}).json()["entries"][0]
    assert entry["status"] == "failed" and "outside" in entry["stderr"]


@pytest.mark.parametrize(
    "path",
    ["/etc/passwd", "C:/x.html", "a/../../b.html", ".env", ".git/config.html", "run.exe", "noext"],
)
def test_executor_refuses_unsafe_or_disallowed_targets(make_app, path):
    action = {"type": "write_file", "path": path, "content": "x"}
    app = make_app(agent=ScriptedAgent(["bad"], {"bad": [action]}))
    pid = app.project()
    assert app.chat(pid).json()["tasks"][0]["status"] == "failed"
    assert files_of(app, pid) == {}


def test_oversized_file_is_refused(make_app):
    action = {"type": "write_file", "path": "big.html", "content": "x" * 300}
    app = make_app(agent=ScriptedAgent(["big"], {"big": [action]}), max_file_bytes=100)
    pid = app.project()
    assert app.chat(pid).json()["tasks"][0]["status"] == "failed"
    assert files_of(app, pid) == {}


def test_a_failed_write_skips_the_rest_of_the_plan(make_app):
    bad = {"type": "write_file", "path": "x.exe", "content": "x"}
    app = make_app(agent=ScriptedAgent(["first", "second"], {"first": [bad]}))
    pid = app.project()
    body = app.chat(pid).json()
    assert [t["status"] for t in body["tasks"]] == ["failed", "skipped"]
    assert body["status"] == "failed"


def test_shell_commands_stay_disabled_even_when_approved(make_app):
    from tests.integration.fakes import run

    app = make_app(agent=ScriptedAgent(["install"], {"install": [run("npm install")]}))
    pid = app.project()
    waiting = app.chat(pid).json()
    assert waiting["status"] == "waiting_for_approval"

    approved = app.client.post("/api/actions/%d/approve" % waiting["pending_action"]["id"]).json()

    entry = app.client.get("/api/logs", params={"project_id": pid}).json()["entries"][0]
    assert entry["status"] == "failed" and "disabled" in entry["stderr"]
    assert approved["tasks"][0]["status"] == "failed"


def test_an_executor_without_file_support_fails_instead_of_pretending(make_app):
    from tests.integration.fakes import RecordingExecutor

    action = {"type": "write_file", "path": "index.html", "content": "<p>x</p>"}
    app = make_app(agent=ScriptedAgent(["w"], {"w": [action]}), executor=RecordingExecutor())
    pid = app.project()
    assert app.chat(pid).json()["tasks"][0]["status"] == "failed"


def test_a_crashing_executor_write_fails_the_task(make_app):
    class Crashing:
        def is_allowed(self, command):
            return False

        def write_file(self, request):
            raise RuntimeError("disk on fire")

    action = {"type": "write_file", "path": "index.html", "content": "<p>x</p>"}
    app = make_app(agent=ScriptedAgent(["w"], {"w": [action]}), executor=Crashing())
    pid = app.project()
    assert app.chat(pid).json()["tasks"][0]["status"] == "failed"


# --- Agent and generator failures --------------------------------------------------


def test_invalid_generated_site_is_rejected_before_any_task_exists(make_app):
    class Broken(ReferenceSiteGenerator):
        def generate(self, spec):
            files = super().generate(spec)
            del files["style.css"]
            return files

    app = make_app(agent=SiteAgent(Broken()))
    pid = app.project()
    response = app.chat(pid, "Create a blog")
    assert response.status_code >= 400
    assert app.client.get("/api/tasks", params={"project_id": pid}).json()["tasks"] == []
    assert files_of(app, pid) == {}


def test_generator_errors_do_not_leak_details(make_app):
    class Exploding:
        def generate(self, spec):
            raise RuntimeError("secret-token-123")

        def validate(self, files):
            return []

    app = make_app(agent=SiteAgent(Exploding()))
    pid = app.project()
    response = app.chat(pid, "Create a blog")
    assert response.status_code >= 400
    assert "secret-token-123" not in response.text


def test_empty_message_is_rejected(make_app):
    app = make_app()
    pid = app.project()
    assert app.chat(pid, "   ").status_code == 422


def test_title_is_escaped_in_generated_html(make_app):
    app = make_app()
    pid = app.project()
    app.chat(pid, "Create a blog called <script>alert(1)</script>")
    assert "<script>alert" not in content_of(app, pid, "index.html")

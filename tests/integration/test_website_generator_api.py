"""End to end with Rana's generator plugged in through GENERATOR_IMPL (Settings.generator_impl)."""
from backend.generator import WebsiteGenerator

GENERATOR = "backend.generator:WebsiteGenerator"


def files_of(app, pid):
    body = app.client.get("/api/files", params={"project_id": pid}).json()
    return {f["path"] for f in body["files"]}


def content_of(app, pid, path):
    response = app.client.get("/api/files/content", params={"project_id": pid, "path": path})
    assert response.status_code == 200, response.text
    return response.json()["content"]


def test_blog_request_uses_the_website_generator(make_app):
    app = make_app(generator_impl=GENERATOR)
    pid = app.project("Blog")

    body = app.chat(pid, "Create a blog called Travel Notes").json()

    assert body["status"] == "completed"
    assert {t["status"] for t in body["tasks"]} == {"succeeded"}
    assert files_of(app, pid) == {"index.html", "about.html", "style.css", "script.js"}
    index = content_of(app, pid, "index.html")
    assert "Travel Notes" in index and "site-blog" in index

    preview = app.client.get("/api/preview", params={"project_id": pid}).json()
    assert preview["status"] == "static"
    assert "Travel Notes" in app.client.get(preview["url"]).text


def test_written_sites_pass_the_generator_validation(make_app):
    app = make_app(generator_impl=GENERATOR)
    generator = WebsiteGenerator()
    for message in ("Create a blog", "Build me a portfolio for Ada Lovelace", "Create a landing page for Acme"):
        pid = app.project(message[:20])
        assert app.chat(pid, message).json()["status"] == "completed"
        site = {path: content_of(app, pid, path) for path in files_of(app, pid)}
        assert generator.validate(site) == []

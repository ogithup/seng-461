"""Sprint 4 interpreter and stateless orchestration contract checks."""
import pytest

from backend.agent.interpreter import UnsupportedRequest, interpret
from backend.agent.orchestrator import Orchestrator
from backend.generator import normalize_spec


@pytest.mark.parametrize("message", ["Create a blog", "portfolio for Ada", "landing page"])
def test_interpreter_returns_deterministic_valid_spec(message):
    spec = interpret(message)
    assert spec == interpret(message) == normalize_spec(spec)


@pytest.mark.parametrize("message", ["build an online shop", "a portfolio with checkout", "e-commerce store"])
def test_unsupported_shop_is_not_reclassified(message):
    with pytest.raises(UnsupportedRequest) as exc:
        interpret(message)
    assert exc.value.code == "unsupported_request"
    assert exc.value.user_message


def test_injected_interpreter_spec_survives_execution_in_a_new_instance():
    spec = interpret("Create a blog")
    spec["pages"][0]["sections"][0]["heading"] = "Custom heading"
    tasks = Orchestrator(interpreter=lambda message: spec).plan("anything")
    action = Orchestrator().next_action({"prompt": tasks[0]}, None)
    assert "Custom heading" in action["content"]


def test_invalid_injected_spec_is_rejected_before_generation():
    with pytest.raises(ValueError):
        Orchestrator(interpreter=lambda message: {"site_type": "blog"}).plan("blog")


@pytest.mark.parametrize(
    ("message", "kind", "title"),
    [("Create a blog", "blog", "My Blog"),
     ("Build a portfolio for Ada", "portfolio", "Ada"),
     ("Create a landing page", "landing", "My Product")],
)
def test_site_types_titles_and_defaults(message, kind, title):
    spec = interpret(message)
    assert (spec["site_type"], spec["title"]) == (kind, title)
    assert spec["pages"][0]["slug"] == "index"
    assert spec["theme"]["primary"].startswith("#")


def test_explicit_fields_flow_through_real_generator_and_task_reconstruction():
    from backend.generator import WebsiteGenerator

    message = "Create a landing page for Acme; page: Pricing; section: Benefits; primary: #123456; accent: #abcdef; font: serif"
    spec = interpret(message)
    assert spec["title"] == "Acme"
    assert spec["theme"] == {"primary": "#123456", "accent": "#abcdef", "font": "serif"}
    assert any(page["slug"] == "pricing" for page in spec["pages"])
    assert any(section["heading"] == "Benefits" for section in spec["pages"][0]["sections"])
    generator = WebsiteGenerator()
    expected = generator.generate(spec)
    assert generator.validate(expected, spec) == []
    tasks = Orchestrator(generator).plan(message)
    assert all(len(task) <= 500 for task in tasks)
    actions = [Orchestrator(generator).next_action({"prompt": task}, None) for task in tasks]
    assert {action["path"]: action["content"] for action in actions} == expected


def test_legacy_prompt_still_produces_an_action():
    action = Orchestrator().next_action({"prompt": 'Write index.html (blog site "My Blog")'}, None)
    assert action["path"] == "index.html"


@pytest.mark.parametrize("message", ["", "  ", "blog; primary: red", "blog; section: ", "blog; pages: "])
def test_missing_and_invalid_input_is_rejected(message):
    with pytest.raises(ValueError):
        interpret(message)


def test_oversized_custom_spec_is_rejected_before_tasks_can_be_truncated():
    spec = interpret("blog")
    # Use a varying payload that cannot fit in a task prompt after compression.
    import random
    rng = random.Random(1)
    spec["pages"][0]["sections"][0]["body"] = "".join(chr(rng.randrange(33, 127)) for _ in range(1000))
    with pytest.raises(ValueError, match="task prompt limit"):
        Orchestrator(interpreter=lambda _: spec).plan("blog")


def test_custom_spec_survives_api_task_storage_and_execution(tmp_path):
    from fastapi.testclient import TestClient
    from backend.api.app import create_app
    from backend.api.config import Settings
    from backend.api.services.container import build_services

    settings = Settings(workspace_root=tmp_path / "workspaces", database_path=tmp_path / "test.db", rate_limit_per_minute=0)
    client = TestClient(create_app(build_services(settings)), raise_server_exceptions=False)
    project_id = client.post("/api/projects", json={"name": "Custom"}).json()["id"]
    response = client.post("/api/chat", json={"project_id": project_id, "message": "landing page for Acme; section: Benefits; primary: #123456"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    content = client.get("/api/files/content", params={"project_id": project_id, "path": "index.html"}).json()["content"]
    assert "Benefits" in content


def test_other_explicitly_unsupported_request():
    with pytest.raises(UnsupportedRequest) as exc:
        interpret("build a mobile app")
    assert "blogs" in exc.value.user_message


def test_existing_encoded_spec_payload_still_works():
    import base64
    import json

    spec = interpret("blog")
    spec["pages"][0]["sections"][0]["heading"] = "Earlier custom heading"
    payload = base64.urlsafe_b64encode(json.dumps(spec).encode()).decode().rstrip("=")
    prompt = 'Write index.html (blog site "My Blog") [spec:%s]' % payload
    action = Orchestrator().next_action({"prompt": prompt}, None)
    assert "Earlier custom heading" in action["content"]

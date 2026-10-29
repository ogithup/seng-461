from pathlib import Path

import pytest
from backend.api.schemas.contracts import AgentAction

from backend.agent.orchestrator import Orchestrator


class FakeGenerator:
    def __init__(self, files=None, problems=None):
        self.files = files or {
            "style.css": "body { color: black; }",
            "about.html": "<h1>About</h1>",
            "index.html": "<h1>Home</h1>",
        }
        self.problems = problems or []
        self.specs = []

    def generate(self, spec):
        self.specs.append(spec)
        return dict(self.files)

    def validate(self, files):
        return list(self.problems)


@pytest.mark.parametrize(
    ("user_request", "site_type", "title"),
    [
        ("Create a blog", "blog", "My Blog"),
        ("Build a portfolio for Ada Lovelace", "portfolio", "Ada Lovelace"),
        ("Make a landing page", "landing", "My Product"),
    ],
)
def test_plan_uses_request_details_and_returns_one_task_per_generated_file(
    user_request, site_type, title
):
    generator = FakeGenerator()
    agent = Orchestrator(generator)

    tasks = agent.plan(user_request)

    assert len(tasks) == len(generator.files)
    assert tasks[0] == 'Write index.html (%s site "%s")' % (site_type, title)
    assert [task.split(" (", 1)[0].removeprefix("Write ") for task in tasks] == [
        "index.html",
        "about.html",
        "style.css",
    ]
    assert all(('(%s site "%s")' % (site_type, title)) in task for task in tasks)
    assert generator.specs[0]["site_type"] == site_type
    assert generator.specs[0]["title"] == title
    assert generator.specs[0]["pages"]
    assert generator.specs[0]["theme"]["primary"].startswith("#")


def test_next_action_reconstructs_a_valid_write_file_action():
    generator = FakeGenerator()
    agent = Orchestrator(generator)
    task = {"prompt": 'Write index.html (blog site "Travel Notes")'}

    action = agent.next_action(task, None)

    validated = AgentAction.model_validate(action)
    assert validated.type == "write_file"
    assert validated.path == "index.html"
    assert validated.content == generator.files["index.html"]
    assert validated.reason
    assert generator.specs[0]["title"] == "Travel Notes"


@pytest.mark.parametrize(
    "last_result",
    [
        {"success": True, "stdout": "verified"},
        {"success": False, "stderr": "write failed"},
    ],
)
def test_next_action_returns_none_after_any_previous_result(last_result):
    generator = FakeGenerator()

    assert Orchestrator(generator).next_action(
        {"prompt": 'Write index.html (blog site "My Blog")'}, last_result
    ) is None
    assert generator.specs == []


@pytest.mark.parametrize(
    "task",
    [
        {},
        {"prompt": "create index.html"},
        {"prompt": 'Write missing.html (blog site "My Blog")'},
        {"prompt": 'Write index.html (shop site "My Shop")'},
    ],
)
def test_next_action_rejects_malformed_or_unsupported_tasks(task):
    with pytest.raises(ValueError):
        Orchestrator(FakeGenerator()).next_action(task, None)


def test_plan_rejects_generator_validation_problems():
    with pytest.raises(ValueError, match="generated site is invalid"):
        Orchestrator(FakeGenerator(problems=["missing index.html"])).plan("Create a blog")


def test_next_action_rejects_generator_validation_problems():
    with pytest.raises(ValueError, match="generated site is invalid"):
        Orchestrator(FakeGenerator(problems=["invalid links"])).next_action(
            {"prompt": 'Write index.html (blog site "My Blog")'}, None
        )


def test_plan_is_deterministic_and_does_not_cache_project_state():
    agent = Orchestrator(FakeGenerator())
    request = "Create a blog called Travel Notes"

    first = agent.plan(request)
    second = agent.plan(request)

    assert first == second


def test_default_reference_generator_creates_tasks_and_actions():
    agent = Orchestrator()

    tasks = agent.plan("Create a blog")
    action = agent.next_action({"prompt": tasks[0]}, None)

    assert tasks == [
        'Write index.html (blog site "My Blog")',
        'Write about.html (blog site "My Blog")',
        'Write script.js (blog site "My Blog")',
        'Write style.css (blog site "My Blog")',
    ]
    assert AgentAction.model_validate(action).path == "index.html"


def test_orchestrator_does_not_write_to_the_filesystem(monkeypatch):
    def fail_on_write(*args, **kwargs):
        raise AssertionError("orchestrator attempted a filesystem write")

    monkeypatch.setattr(Path, "write_text", fail_on_write)
    monkeypatch.setattr(Path, "write_bytes", fail_on_write)

    agent = Orchestrator(FakeGenerator())
    tasks = agent.plan("Create a blog")
    action = agent.next_action({"prompt": tasks[0]}, None)

    assert action["type"] == "write_file"

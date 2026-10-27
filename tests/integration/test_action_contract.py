"""AgentAction accepts run_command and write_file and rejects mixed or unsafe shapes."""
import pytest
from pydantic import ValidationError

from backend.api.schemas.contracts import AgentAction


def test_run_command_is_unchanged():
    action = AgentAction.model_validate({"type": "run_command", "command": "npm test"})
    assert (action.command, action.requires_approval, action.path) == ("npm test", False, None)


def test_write_file_carries_path_and_content_and_a_log_friendly_command():
    action = AgentAction.model_validate(
        {"type": "write_file", "path": "index.html", "content": "  <p>hi</p>\n", "reason": "home"}
    )
    assert action.command == "write_file index.html"
    assert action.content == "  <p>hi</p>\n"  # whitespace in files is preserved


@pytest.mark.parametrize(
    "raw",
    [
        {"type": "run_command"},
        {"type": "run_command", "command": "ls", "path": "a.html"},
        {"type": "write_file", "path": "a.html"},
        {"type": "write_file", "content": "x"},
        {"type": "write_file", "path": "a.html", "content": "x", "command": "ls"},
        {"type": "write_file", "path": "a\nb.html", "content": "x"},
        {"type": "write_file", "path": "a.html", "content": "x", "requires_approval": True},
        {"type": "delete_file", "path": "a.html"},
    ],
)
def test_invalid_actions_are_rejected(raw):
    with pytest.raises(ValidationError):
        AgentAction.model_validate(raw)

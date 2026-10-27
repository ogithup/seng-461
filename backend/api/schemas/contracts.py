"""The shared contracts between modules (docs/api-contracts.md, "Shared contracts").

Other modules do not have to import these classes: the API accepts any object or
dict that carries the same fields (`from_attributes=True`), so agent/execution/
storage stay decoupled from this package.
"""
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from backend.api.schemas.common import has_control_chars

MAX_COMMAND_LENGTH = 1000
MAX_PATH_LENGTH = 300
MAX_CONTENT_CHARS = 500_000


def _single_line_command(value: str) -> str:
    # A newline or NUL inside one "command" is how a second command sneaks past an allowlist.
    if has_control_chars(value):
        raise ValueError("command must be a single line without control characters")
    return value


class AgentAction(BaseModel):
    """Agent -> API: what the agent wants done. The agent never runs anything itself.

    Two kinds: `run_command` (needs `command`) and `write_file` (needs `path` and
    `content`). For a `write_file` action the API stores `command` as "write_file <path>".
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid", str_strip_whitespace=True)

    type: Literal["run_command", "write_file"]
    command: str = Field(default="", max_length=MAX_COMMAND_LENGTH)
    path: Optional[str] = Field(default=None, max_length=MAX_PATH_LENGTH)
    # Not stripped: whitespace in a file is part of the file.
    content: Optional[Annotated[str, StringConstraints(strip_whitespace=False, max_length=MAX_CONTENT_CHARS)]] = None
    requires_approval: bool = False
    # Why the agent needs this action; shown to the human when approval is required.
    reason: Optional[str] = Field(default=None, max_length=500)

    @field_validator("command")
    @classmethod
    def _command_is_single_line(cls, value: str) -> str:
        return _single_line_command(value)

    @model_validator(mode="after")
    def _fields_match_type(self) -> "AgentAction":
        if self.type == "run_command":
            if not self.command:
                raise ValueError("run_command needs a command")
            if self.path is not None or self.content is not None:
                raise ValueError("run_command does not take path or content")
        else:
            if not self.path or self.content is None:
                raise ValueError("write_file needs a path and content")
            if self.command:
                raise ValueError("write_file does not take a command")
            if has_control_chars(self.path):
                raise ValueError("path must not contain control characters")
            if self.requires_approval:
                # Content is not kept on a pending record, so there is nothing to approve later.
                raise ValueError("write_file never waits for approval; the executor bounds it")
            self.command = "write_file %s" % self.path
        return self


class WriteFileRequest(BaseModel):
    """API -> Executor: write one file inside the project workspace."""

    working_directory: str
    path: str = Field(min_length=1, max_length=MAX_PATH_LENGTH)
    content: str


class ExecutionRequest(BaseModel):
    """API -> Executor."""

    command: str = Field(min_length=1, max_length=MAX_COMMAND_LENGTH)
    working_directory: str
    timeout: int = Field(ge=1, le=600)
    # True when this command needed a human decision (agent flag or not on the allowlist).
    requires_approval: bool = False

    @field_validator("command")
    @classmethod
    def _command_is_single_line(cls, value: str) -> str:
        return _single_line_command(value)


class ExecutionResult(BaseModel):
    """Executor -> API (and API -> Agent as the result of its last action)."""

    model_config = ConfigDict(from_attributes=True)

    success: bool
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)

    @field_validator("stdout", "stderr", mode="before")
    @classmethod
    def _none_is_empty(cls, value: Any) -> Any:
        return "" if value is None else value

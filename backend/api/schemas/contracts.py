"""The shared contracts between modules (docs/api-contracts.md, "Shared contracts").

Other modules do not have to import these classes: the API accepts any object or
dict that carries the same fields (`from_attributes=True`), so agent/execution/
storage stay decoupled from this package.
"""
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.api.schemas.common import has_control_chars

MAX_COMMAND_LENGTH = 1000


def _single_line_command(value: str) -> str:
    # A newline or NUL inside one "command" is how a second command sneaks past an allowlist.
    if has_control_chars(value):
        raise ValueError("command must be a single line without control characters")
    return value


class AgentAction(BaseModel):
    """Agent -> API: what the agent wants done. The agent never runs anything itself."""

    model_config = ConfigDict(from_attributes=True, extra="forbid", str_strip_whitespace=True)

    type: Literal["run_command"]
    command: str = Field(min_length=1, max_length=MAX_COMMAND_LENGTH)
    requires_approval: bool = False
    # Why the agent needs this command; shown to the human when approval is required.
    reason: Optional[str] = Field(default=None, max_length=500)

    @field_validator("command")
    @classmethod
    def _command_is_single_line(cls, value: str) -> str:
        return _single_line_command(value)


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

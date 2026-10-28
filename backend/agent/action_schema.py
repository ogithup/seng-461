"""Agent action shapes matching the API contract without importing API internals."""

from typing import Literal, Optional, TypedDict, Union


class _RunCommandRequired(TypedDict):
    type: Literal["run_command"]
    command: str


class RunCommandAction(_RunCommandRequired, total=False):
    requires_approval: bool
    reason: Optional[str]


class _WriteFileRequired(TypedDict):
    type: Literal["write_file"]
    path: str
    content: str


class WriteFileAction(_WriteFileRequired, total=False):
    reason: Optional[str]


AgentAction = Union[RunCommandAction, WriteFileAction]

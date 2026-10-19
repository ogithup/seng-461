"""Agent output shape, matching the API contract without importing its internals.

No actions are emitted in Sprint 1. Future actions are data for the API and
executor; declaring an action never grants permission or runs a command.
"""

from typing import Literal, Optional, TypedDict


class _RequiredAction(TypedDict):
    type: Literal["run_command"]
    command: str


class AgentAction(_RequiredAction, total=False):
    requires_approval: bool
    reason: Optional[str]

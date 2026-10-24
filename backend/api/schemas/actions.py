from typing import Literal, Optional

from pydantic import Field

from backend.api.schemas.common import StrictModel
from backend.api.schemas.tasks import ProjectState


class ActionDecisionRequest(StrictModel):
    # `pending_action.command_hash` from the response the human was looking at. If the
    # pending command changed since, the decision is refused instead of applied.
    command_hash: Optional[str] = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class ActionDecisionResponse(ProjectState):
    action_id: int
    decision: Literal["approved", "rejected"]
    message: str

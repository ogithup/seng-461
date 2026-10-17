from typing import Optional

from fastapi import APIRouter, Body, Depends, Path

from backend.api.dependencies import get_services
from backend.api.schemas.actions import ActionDecisionRequest, ActionDecisionResponse
from backend.api.services.container import Services

router = APIRouter(tags=["actions"])


@router.post("/actions/{action_id}/approve", response_model=ActionDecisionResponse)
def approve_action(
    action_id: int = Path(ge=1),
    body: Optional[ActionDecisionRequest] = Body(default=None),
    services: Services = Depends(get_services),
):
    command_hash = body.command_hash if body else None
    return services.actions.decide(action_id, approve=True, command_hash=command_hash)


@router.post("/actions/{action_id}/reject", response_model=ActionDecisionResponse)
def reject_action(
    action_id: int = Path(ge=1),
    body: Optional[ActionDecisionRequest] = Body(default=None),
    services: Services = Depends(get_services),
):
    command_hash = body.command_hash if body else None
    return services.actions.decide(action_id, approve=False, command_hash=command_hash)

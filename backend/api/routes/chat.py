from typing import Optional

from fastapi import APIRouter, Depends

from backend.api.dependencies import get_idempotency_key, get_owner, get_services, submit
from backend.api.schemas.chat import ChatRequest, ChatResponse
from backend.api.services.container import Services

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    services: Services = Depends(get_services),
    owner: str = Depends(get_owner),
    key: Optional[str] = Depends(get_idempotency_key),
):
    return submit(
        services, owner, "chat", key, body, 200,
        lambda: services.chat.handle(body.project_id, body.message),
    )

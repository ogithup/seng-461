from fastapi import APIRouter, Depends, Query

from backend.api.dependencies import get_services
from backend.api.schemas.logs import LogsResponse
from backend.api.services.container import Services

router = APIRouter(tags=["logs"])


@router.get("/logs", response_model=LogsResponse)
def get_logs(
    project_id: int = Query(ge=1),
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    services: Services = Depends(get_services),
):
    return services.tasks.logs(project_id, after_id, limit)

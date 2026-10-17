from fastapi import APIRouter, Depends, Query

from backend.api.dependencies import get_services
from backend.api.schemas.tasks import ProjectState
from backend.api.services.container import Services

router = APIRouter(tags=["tasks"])


@router.get("/tasks", response_model=ProjectState)
def get_tasks(project_id: int = Query(ge=1), services: Services = Depends(get_services)):
    return services.tasks.state(project_id)

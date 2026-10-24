from typing import List, Optional

from fastapi import APIRouter, Depends

from backend.api.dependencies import get_idempotency_key, get_owner, get_services, submit
from backend.api.schemas.projects import ProjectCreate, ProjectCreateResponse, ProjectResponse
from backend.api.services.container import Services

router = APIRouter(tags=["projects"])


@router.post("/projects", response_model=ProjectCreateResponse, status_code=201)
def create_project(
    body: ProjectCreate,
    services: Services = Depends(get_services),
    owner: str = Depends(get_owner),
    key: Optional[str] = Depends(get_idempotency_key),
):
    return submit(services, owner, "projects", key, body, 201, lambda: services.projects.create(body.name))


@router.get("/projects", response_model=List[ProjectResponse])
def list_projects(services: Services = Depends(get_services)):
    return services.projects.list()


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: int, services: Services = Depends(get_services)):
    return services.projects.require(project_id)

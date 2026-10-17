from fastapi import APIRouter, Depends, Query

from backend.api.dependencies import get_services
from backend.api.schemas.files import FileContentResponse, FileListResponse
from backend.api.services.container import Services

router = APIRouter(tags=["files"])


@router.get("/files", response_model=FileListResponse)
def list_files(project_id: int = Query(ge=1), services: Services = Depends(get_services)):
    services.projects.require(project_id)
    files, truncated = services.workspace.list_files(project_id)
    return FileListResponse(project_id=project_id, files=files, truncated=truncated)


@router.get("/files/content", response_model=FileContentResponse)
def read_file(
    project_id: int = Query(ge=1),
    path: str = Query(min_length=1, max_length=500),
    services: Services = Depends(get_services),
):
    services.projects.require(project_id)
    relative, size, content = services.workspace.read_text(project_id, path)
    return FileContentResponse(project_id=project_id, path=relative, size=size, content=content)

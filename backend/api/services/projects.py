from typing import List

from backend.api.errors import not_found
from backend.api.schemas.common import OutputModel
from backend.api.schemas.projects import ProjectCreateResponse, ProjectResponse
from backend.api.services.ports import StoragePort
from backend.api.services.workspace import WorkspaceService


class _SessionOut(OutputModel):
    id: int


class ProjectService:
    """Projects and their sessions. Creating a project also creates its workspace folder."""

    def __init__(self, storage: StoragePort, workspace: WorkspaceService):
        self._storage = storage
        self._workspace = workspace

    def create(self, name: str) -> ProjectCreateResponse:
        project = ProjectResponse.model_validate(self._storage.create_project(name))
        self._workspace.ensure_project_dir(project.id)
        session = _SessionOut.model_validate(self._storage.create_session(project.id))
        return ProjectCreateResponse(**project.model_dump(), session_id=session.id)

    def list(self) -> List[ProjectResponse]:
        return [ProjectResponse.model_validate(p) for p in self._storage.list_projects()]

    def require(self, project_id: int) -> ProjectResponse:
        raw = self._storage.get_project(project_id)
        if raw is None:
            raise not_found("project_not_found", "No such project.", project_id)
        return ProjectResponse.model_validate(raw)

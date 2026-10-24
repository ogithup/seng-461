import mimetypes

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import FileResponse

from backend.api.dependencies import get_services
from backend.api.schemas.files import PreviewResponse
from backend.api.services.container import Services

router = APIRouter(tags=["preview"])

# Generated code is untrusted. `sandbox` gives the page an opaque origin, so scripts in
# it cannot read this API's responses or storage. Embed it in <iframe sandbox="allow-scripts">.
_PREVIEW_HEADERS = {
    "Content-Security-Policy": "sandbox allow-scripts",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
}


@router.get("/preview", response_model=PreviewResponse)
def get_preview(project_id: int = Query(ge=1), services: Services = Depends(get_services)):
    services.projects.require(project_id)
    if services.workspace.has_index_html(project_id):
        return PreviewResponse(
            project_id=project_id, status="static", url="/api/preview/%d/" % project_id
        )
    return PreviewResponse(project_id=project_id, status="unavailable")


@router.get("/preview/{project_id}/{file_path:path}", include_in_schema=False)
def serve_preview_file(
    *,
    project_id: int = Path(ge=1),
    file_path: str,
    services: Services = Depends(get_services),
):
    services.projects.require(project_id)
    target = services.workspace.preview_file(project_id, file_path)
    media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(str(target), media_type=media_type, headers=_PREVIEW_HEADERS)

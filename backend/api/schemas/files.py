from typing import List, Literal, Optional

from pydantic import BaseModel


class FileInfo(BaseModel):
    path: str
    size: int


class FileListResponse(BaseModel):
    project_id: int
    files: List[FileInfo]
    truncated: bool


class FileContentResponse(BaseModel):
    project_id: int
    path: str
    size: int
    content: str


class PreviewResponse(BaseModel):
    project_id: int
    # "static": the workspace has an index.html served by this API.
    status: Literal["unavailable", "static"]
    url: Optional[str] = None

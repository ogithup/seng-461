from datetime import datetime

from pydantic import Field, field_validator

from backend.api.schemas.common import OutputModel, StrictModel, has_control_chars

MAX_PROJECT_NAME_LENGTH = 100


class ProjectCreate(StrictModel):
    name: str = Field(min_length=1, max_length=MAX_PROJECT_NAME_LENGTH)

    @field_validator("name")
    @classmethod
    def _single_line(cls, value: str) -> str:
        if has_control_chars(value):
            raise ValueError("name must be a single line without control characters")
        return value


class ProjectResponse(OutputModel):
    id: int
    name: str
    created_at: datetime


class ProjectCreateResponse(ProjectResponse):
    session_id: int

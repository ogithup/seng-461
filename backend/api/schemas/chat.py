from pydantic import Field, field_validator

from backend.api.schemas.common import StrictModel, has_control_chars
from backend.api.schemas.tasks import ProjectState

MAX_MESSAGE_LENGTH = 4000


class ChatRequest(StrictModel):
    project_id: int = Field(ge=1)
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)

    @field_validator("message")
    @classmethod
    def _no_control_chars(cls, value: str) -> str:
        if has_control_chars(value, allow_whitespace=True):
            raise ValueError("message must not contain control characters")
        return value


class ChatResponse(ProjectState):
    message: str

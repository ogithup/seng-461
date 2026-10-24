from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Base for request bodies: unknown fields are rejected, strings are stripped."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OutputModel(BaseModel):
    """Base for records read from other modules (ORM-like objects or dicts)."""

    model_config = ConfigDict(from_attributes=True)


def has_control_chars(value: str, allow_whitespace: bool = False) -> bool:
    for ch in value:
        if allow_whitespace and ch in "\n\r\t":
            continue
        if ord(ch) < 32 or ord(ch) == 127:
            return True
    return False


class ErrorDetail(BaseModel):
    field: str
    message: str
    type: str


class ErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool = False
    project_id: Optional[int] = None
    request_id: Optional[str] = None
    details: Optional[List[ErrorDetail]] = None


class ErrorResponse(BaseModel):
    error: ErrorBody

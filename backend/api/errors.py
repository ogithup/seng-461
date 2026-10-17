"""One error envelope for every failure the API returns.

    {"error": {"code": "...", "message": "...", "retryable": false,
               "project_id": 1, "request_id": "...", "details": [...]}}

Status codes: 422 validation, 403 not allowed, 404 not found, 409 conflict,
413 too large, 429 throttled, 502 a downstream module failed, 500 anything
unexpected. Stack traces, provider secrets and echoed request input never leave
the server; they go to the log instead.
"""
import logging
from typing import Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.api.schemas.common import ErrorBody, ErrorDetail, ErrorResponse

logger = logging.getLogger("backend.api")


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        project_id: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable
        self.project_id = project_id
        self.headers = headers


def error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    request: Optional[Request] = None,
    retryable: bool = False,
    project_id: Optional[int] = None,
    details: Optional[List[ErrorDetail]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None) if request is not None else None
    if request_id:
        headers = {**(headers or {}), "X-Request-ID": request_id}
    body = ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            retryable=retryable,
            project_id=project_id,
            request_id=request_id,
            details=details,
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json", exclude_none=True),
        headers=headers,
    )


async def _handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
    return error_response(
        exc.status_code,
        exc.code,
        exc.message,
        request=request,
        retryable=exc.retryable,
        project_id=exc.project_id,
        headers=exc.headers,
    )


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Report where and why, never the offending input (it may be large or sensitive).
    details = [
        ErrorDetail(
            field=".".join(str(part) for part in err.get("loc", ())),
            message=str(err.get("msg", "invalid value")),
            type=str(err.get("type", "value_error")),
        )
        for err in exc.errors()
    ]
    return error_response(
        422, "validation_error", "Request validation failed.", request=request, details=details
    )


_HTTP_CODES = {404: "not_found", 405: "method_not_allowed"}


async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _HTTP_CODES.get(exc.status_code, "http_%d" % exc.status_code)
    message = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return error_response(exc.status_code, code, message, request=request)


async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled error request_id=%s path=%s",
        getattr(request.state, "request_id", None),
        request.url.path,
        exc_info=exc,
    )
    return error_response(
        500, "internal_error", "Something went wrong on the server.", request=request
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _handle_api_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    # app.py's middleware catches errors first so they still get CORS headers; this is the fallback.
    app.add_exception_handler(Exception, handle_unexpected)


def not_found(code: str, message: str, project_id: Optional[int] = None) -> ApiError:
    return ApiError(404, code, message, project_id=project_id)


def conflict(
    code: str, message: str, project_id: Optional[int] = None, retryable: bool = False
) -> ApiError:
    return ApiError(409, code, message, project_id=project_id, retryable=retryable)


def forbidden(code: str, message: str, project_id: Optional[int] = None) -> ApiError:
    return ApiError(403, code, message, project_id=project_id)

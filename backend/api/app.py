"""Application factory for the REST API (Oğuz's integration layer)."""
import uuid
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.api.config import Settings
from backend.api.errors import error_response, handle_unexpected, register_error_handlers
from backend.api.routes import actions, chat, files, health, logs, preview, projects, tasks
from backend.api.services.container import Services, build_services


def create_app(
    services: Optional[Services] = None, settings: Optional[Settings] = None
) -> FastAPI:
    """Build the app with the Sprint 1 agent and mock storage/execution by default.

    Pass `services=build_services(storage=..., agent=..., executor=...)` to run on the
    real modules.
    """
    if services is None:
        services = build_services(settings)
    settings = services.settings

    app = FastAPI(title="AI Website Agent API", version="0.1.0")
    app.state.services = services
    register_error_handlers(app)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id

        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > settings.max_request_body_bytes:
            response = error_response(
                413, "request_too_large", "Request body is too large.", request=request
            )
        else:
            try:
                response = await call_next(request)
            except Exception as exc:  # answer here so the 500 still passes through CORS
                response = await handle_unexpected(request, exc)
        response.headers["X-Request-ID"] = request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response

    # Added last so it is outermost: error responses get CORS headers too.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Idempotency-Key"],
        expose_headers=["X-Request-ID", "Idempotent-Replay", "Retry-After"],
    )

    for module in (health, projects, chat, tasks, actions, logs, files, preview):
        app.include_router(module.router, prefix="/api")
    return app

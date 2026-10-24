import hashlib
from typing import Any, Callable, Optional

from fastapi import Depends, Header, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.api.errors import ApiError
from backend.api.services.container import Services
from backend.api.services.guards import IdempotencyStore, StoredResponse


def get_services(request: Request) -> Services:
    return request.app.state.services


def get_owner() -> str:
    """Who is calling. There are no accounts in v1, so everyone is the local user.

    This is the single place to plug authentication in later: the owner scopes
    idempotency keys and rate limits, and is where project ownership checks go.
    """
    return "local"


def get_idempotency_key(
    services: Services = Depends(get_services),
    idempotency_key: Optional[str] = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:\-]+$",
    ),
) -> Optional[str]:
    if idempotency_key is None and services.settings.require_idempotency_key:
        raise ApiError(
            422, "idempotency_key_required", "This request needs an Idempotency-Key header."
        )
    return idempotency_key


def submit(
    services: Services,
    owner: str,
    scope: str,
    key: Optional[str],
    payload: BaseModel,
    status_code: int,
    work: Callable[[], Any],
) -> Any:
    """Run a state-changing request with rate limiting and optional idempotency.

    A replay (same key, same payload) returns the stored response without running `work`
    again and without counting against the rate limit.
    """

    def limited() -> Any:
        services.limiter.check(owner)
        return work()

    if key is None:
        return limited()

    store: IdempotencyStore = services.idempotency
    store_key = (owner, scope, key)
    fingerprint = hashlib.sha256(payload.model_dump_json().encode("utf-8")).hexdigest()

    replay = store.begin(store_key, fingerprint)
    if replay is not None:
        return JSONResponse(
            replay.body, status_code=replay.status_code, headers={"Idempotent-Replay": "true"}
        )
    try:
        result = limited()
    except BaseException:
        store.abort(store_key)
        raise
    body = jsonable_encoder(result)
    store.complete(store_key, StoredResponse(status_code, body))
    return JSONResponse(body, status_code=status_code)

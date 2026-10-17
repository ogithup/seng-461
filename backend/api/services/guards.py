"""Submission guards: idempotency keys and a rate limiter.

Both are in-memory, which is right for the single-process prototype. A multi-worker
deployment needs a shared store (the spec moves to PostgreSQL at that point).
"""
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Any, Callable, Deque, Dict, Hashable, Optional

from backend.api.errors import ApiError, conflict


@dataclass
class StoredResponse:
    status_code: int
    body: Any


@dataclass
class _Entry:
    fingerprint: str
    created: float
    response: Optional[StoredResponse] = None  # None while the first request is running


class IdempotencyStore:
    """Same key + same request -> the original response. Same key + different request -> 409."""

    def __init__(
        self,
        ttl_seconds: float = 24 * 3600,
        max_entries: int = 1000,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._ttl = ttl_seconds
        self._max = max_entries
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: "OrderedDict[Hashable, _Entry]" = OrderedDict()

    def begin(self, key: Hashable, fingerprint: str) -> Optional[StoredResponse]:
        """Claim the key. Returns the stored response when this is a replay."""
        with self._lock:
            self._evict()
            entry = self._entries.get(key)
            if entry is None:
                self._entries[key] = _Entry(fingerprint, self._clock())
                return None
            if entry.fingerprint != fingerprint:
                raise conflict(
                    "idempotency_conflict",
                    "This Idempotency-Key was already used with a different request.",
                )
            if entry.response is None:
                raise conflict(
                    "idempotency_in_progress",
                    "A request with this Idempotency-Key is still being processed.",
                    retryable=True,
                )
            return entry.response

    def complete(self, key: Hashable, response: StoredResponse) -> None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                entry.response = response

    def abort(self, key: Hashable) -> None:
        """The request failed; forget the key so the client can retry it."""
        with self._lock:
            self._entries.pop(key, None)

    def _evict(self) -> None:
        now = self._clock()
        for key in [k for k, e in self._entries.items() if now - e.created > self._ttl]:
            del self._entries[key]
        while len(self._entries) >= self._max:
            oldest = next(iter(self._entries))
            if self._entries[oldest].response is None:
                break  # never drop a request that is still running
            del self._entries[oldest]


class RateLimiter:
    """At most `limit` submissions per owner per `window_seconds`. limit=0 disables it."""

    def __init__(
        self,
        limit: int,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._hits: Dict[str, Deque[float]] = {}

    def check(self, owner: str) -> None:
        if self._limit <= 0:
            return
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(owner, deque())
            while hits and now - hits[0] >= self._window:
                hits.popleft()
            if len(hits) >= self._limit:
                retry_after = max(1, int(self._window - (now - hits[0])) + 1)
                raise ApiError(
                    429,
                    "rate_limited",
                    "Too many requests. Try again shortly.",
                    retryable=True,
                    headers={"Retry-After": str(retry_after)},
                )
            hits.append(now)

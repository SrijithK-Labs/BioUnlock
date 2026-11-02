"""A small in-process fixed-window rate limiter.

Suitable for a single-process development deployment and for tests. In a
multi-worker/multi-host production deployment, back this with Redis or a
reverse-proxy limiter; the interface stays the same.
"""

from __future__ import annotations

import threading
import time

from fastapi import HTTPException, Request, status


class RateLimiter:
    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        self._hits: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window: float) -> bool:
        if not self._enabled:
            return True
        now = time.monotonic()
        with self._lock:
            window_start, count = self._hits.get(key, (now, 0))
            if now - window_start >= window:
                window_start, count = now, 0
            count += 1
            self._hits[key] = (window_start, count)
            if len(self._hits) > 10000:  # opportunistic pruning
                self._prune(now, window)
            return count <= limit

    def _prune(self, now: float, window: float) -> None:
        stale = [k for k, (start, _) in self._hits.items() if now - start >= window * 4]
        for key in stale:
            self._hits.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def rate_limit(scope: str, limit: int, window: float = 60.0):
    """FastAPI dependency limiting requests per client IP."""

    def dependency(request: Request) -> None:
        limiter: RateLimiter = request.app.state.rate_limiter
        if not limiter.check(f"{scope}:{client_ip(request)}", limit, window):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please slow down and try again later.",
            )

    return dependency


def enforce_key_limit(request: Request, key: str, limit: int, window: float = 60.0) -> None:
    """Enforce a limit for an arbitrary key (e.g. an account id)."""
    limiter: RateLimiter = request.app.state.rate_limiter
    if not limiter.check(key, limit, window):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please slow down and try again later.",
        )

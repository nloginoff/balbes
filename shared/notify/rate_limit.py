"""Simple per-IP sliding-window rate limit for notify endpoint."""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status


class SlidingWindowRateLimiter:
    """Keep timestamps per key; drop entries older than window_seconds."""

    def __init__(self, max_requests: int, window_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, max_requests: int | None = None) -> None:
        limit = self.max_requests if max_requests is None else max_requests
        now = time.monotonic()
        cutoff = now - self.window_seconds
        arr = self._hits[key]
        arr[:] = [t for t in arr if t > cutoff]
        if len(arr) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
            )
        arr.append(now)


def client_ip(request: Request) -> str:
    """Prefer X-Forwarded-For first hop when behind reverse proxy."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"

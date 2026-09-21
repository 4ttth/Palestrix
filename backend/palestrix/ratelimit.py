"""Request rate limiting.

docs/public-api.md has always published a limit table — 600 requests/minute
general, 60/minute for launch and extend, 10/minute for flag submission —
and nothing implemented it. A documented control that does not exist is
worse than an absent one: the login endpoint took unlimited password
guesses while the contract said otherwise.

Buckets, coarsest last:

- ``auth``    credential endpoints (login, register, token, passkey verify).
              The brute-force surface, so the tightest.
- ``launch``  instance launch and extend: each one costs a real VM or
              container, so the limit protects the hypervisor, not the API.
- ``flag``    flag submission, on top of the per-challenge cooldown in
              compete.py — the cooldown paces one challenge, this paces the
              account across all of them.
- ``general`` everything else.

Identity is the API key, then the bearer token, then the peer address, so a
shared campus NAT does not put every student in one bucket once they are
signed in. Before sign-in there is only the address, which is the point.

Scope: per process, in memory. Several uvicorn workers therefore each allow
their own share, and the edge proxy (Caddy/Traefik in the runbooks) remains
the authoritative limiter for a deployment. This is the floor that holds
even when the API is reached directly.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

WINDOW_SECONDS = 60.0

# Path prefixes (under the API root) that fall into a tighter bucket than
# "general". Checked longest-first, so a more specific rule wins.
AUTH_PATHS = (
    "/auth/login",
    "/auth/register",
    "/auth/token",
    "/auth/password",
    "/auth/webauthn/login/verify",
    "/auth/webauthn/login/options",
)
LAUNCH_EXACT = "/instances"
LAUNCH_SUFFIXES = ("/extend",)
FLAG_SUFFIX = "/submit"


class _Window:
    """Fixed-cost sliding window: one deque of timestamps per bucket."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, now: float) -> int:
        """0 when the request may proceed, else seconds until it may."""
        cutoff = now - WINDOW_SECONDS
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= limit:
                return max(1, int(hits[0] + WINDOW_SECONDS - now) + 1)
            hits.append(now)
            return 0

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


_windows = _Window()


def reset() -> None:
    """Drop all counters. For tests, and for a deliberate operator reset."""
    _windows.clear()


def bucket_for(path: str, method: str, api_prefix: str) -> str:
    """Which limit applies to this request."""
    if not path.startswith(api_prefix):
        return "general"
    rest = path[len(api_prefix):]
    if any(rest.startswith(p) for p in AUTH_PATHS):
        return "auth"
    if method == "POST":
        if rest == LAUNCH_EXACT or any(rest.endswith(s) for s in LAUNCH_SUFFIXES):
            return "launch"
        if rest.startswith("/compete/challenges/") and rest.endswith(FLAG_SUFFIX):
            return "flag"
    return "general"


def _identity(request: Request) -> str:
    """Who is being limited. Hashed: the counter table must not become a
    place where credentials sit around in memory."""
    api_key = request.headers.get("x-api-key")
    if api_key:
        return "k:" + hashlib.blake2s(api_key.encode(), digest_size=16).hexdigest()
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1]
        return "t:" + hashlib.blake2s(token.encode(), digest_size=16).hexdigest()
    peer = request.client.host if request.client else "unknown"
    return "a:" + peer


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, limits: dict[str, int], api_prefix: str) -> None:
        super().__init__(app)
        self._limits = limits
        self._api_prefix = api_prefix

    async def dispatch(self, request: Request, call_next):
        bucket = bucket_for(request.url.path, request.method, self._api_prefix)
        limit = self._limits.get(bucket, 0)
        if limit <= 0:  # 0 disables that bucket
            return await call_next(request)

        key = f"{bucket}|{_identity(request)}"
        retry_after = _windows.check(key, limit, time.monotonic())
        if retry_after:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": {
                        "error": "rate_limited",
                        "bucket": bucket,
                        "limit": limit,
                        "window_seconds": int(WINDOW_SECONDS),
                        "retry_after": retry_after,
                    }
                },
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)

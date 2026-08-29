"""
Per-caller request limits.

One dependency per class of endpoint, because scoring, uploading and browsing
have very different costs and deserve different ceilings.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from api.config.settings import settings
from api.lib import ratelimit


def client_key(request: Request) -> str:
    """A stable key for rate limiting. The proxy header is used when present."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_limit(request: Request, limit: int, suffix: str = "") -> None:
    try:
        ratelimit.check(f"{client_key(request)}:{suffix}", limit)
    except ratelimit.RateLimited as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "message": "Too many requests. Please slow down.",
                "retry_after_seconds": exc.retry_after,
                "limit_per_minute": exc.limit,
            },
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc


def rate_limit_public(request: Request) -> None:
    _rate_limit(request, settings.rate_limit_public, "public")


def rate_limit_scoring(request: Request) -> None:
    _rate_limit(request, settings.rate_limit_scoring, "score")


def rate_limit_upload(request: Request) -> None:
    _rate_limit(request, settings.rate_limit_upload, "upload")

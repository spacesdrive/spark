"""
Headers every response carries, and how long the request took.

Applied as one middleware rather than per route, because a header that is only
sometimes present is the same as no header.
"""

from __future__ import annotations

import time

from fastapi import Request

from api.config.settings import settings


async def add_security_headers(request: Request, call_next):
    """Timing, plus the headers a browser should be told to apply."""
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Response-Time-ms"] = (
        f"{(time.perf_counter() - started) * 1000:.1f}"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response

"""
Turning failures into responses.

Two rules, and they are the reason this is not left to the framework defaults.
A response body always carries a ``message`` a person can act on. Stack traces
and server paths stay in the log.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

log = logging.getLogger("spark.api")


async def validation_handler(request: Request, exc: RequestValidationError):
    """
    Turn schema errors into sentences.

    ``amount: Input should be greater than or equal to 0`` is what the library
    says. What the user needs to read is which field is wrong and what would
    fix it.
    """
    fields = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", []) if p not in ("body", "query")]
        fields.append(
            {
                "field": ".".join(loc) or "request",
                "problem": err.get("msg", "That value is not valid."),
            }
        )
    return JSONResponse(
        status_code=getattr(
            status, "HTTP_422_UNPROCESSABLE_CONTENT", 422
        ),
        content={
            "detail": {
                "message": "Some of the values sent were not valid.",
                "reason": "validation_failed",
                "fields": fields,
            }
        },
    )


async def unhandled_handler(request: Request, exc: Exception):
    """Log the detail, tell the user something useful, leak nothing."""
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": {
                "message": "Spark could not process this request. The details "
                           "are in the server log.",
                "reason": "server_error",
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, validation_handler)
    app.add_exception_handler(Exception, unhandled_handler)

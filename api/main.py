"""
The Spark API.

    uvicorn api.main:app --reload

Everything under ``/api`` is served here. The dashboard is a separate Vite app
in development and static files behind a reverse proxy in production.

This module only assembles the application. The pieces live where their
responsibility does:

``api.routes``        which URL maps to which handler
``api.controllers``   the handlers
``api.services``      the work they call
``api.models``        the database tables
``api.validators``    the shapes that go in and come out
``api.middleware``    headers, origins and error shaping

Two design rules run through the whole thing:

Errors are readable. A response body always carries a ``message`` a person can
act on. Stack traces stay in the server log.

Nothing is invented. When a number, a model or a feature is not there, the API
says so with a reason code rather than filling in a placeholder.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.config.settings import settings
from api.database import init_db
from api.middleware import (
    add_security_headers,
    register_cors,
    register_exception_handlers,
)
from api.routes import ROUTERS
from api.services import engine as engine_state

log = logging.getLogger("spark.api")

DESCRIPTION = """
Spark scores payment transactions for fraud risk and groups accounts that look
like they are working together.

Two ways in:

* `/api/...` is what the dashboard uses. Most of it is open to guests.
* `/api/v1/...` is for your servers. Send your key as
  `Authorization: Bearer sk_test_...`.

Every number this API reports was measured. When something has not been
measured, or is not built, the response says so.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if settings.eager_model_load:
        # Loading takes a few seconds. Doing it here means the first user
        # request is fast, and /api/health reports the failure rather than the
        # first scoring request discovering it.
        engine_state.load()
        st = engine_state.status()
        if st["loaded"]:
            log.info("model loaded in %ss", st["load_seconds"])
        else:
            log.warning("model not loaded: %s", st["error"])
    yield


app = FastAPI(
    title="Spark",
    description=DESCRIPTION,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

register_cors(app)
app.middleware("http")(add_security_headers)
register_exception_handlers(app)

for router in ROUTERS:
    app.include_router(router, prefix="/api")


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "name": "Spark",
        "docs": "/api/docs",
        "health": "/api/health",
    }

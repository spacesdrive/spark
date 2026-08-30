"""
The URL table.

Every route in the application is registered here, in one list, so the whole
surface can be read without opening ten files. Each module in this package maps
paths onto the handlers in ``api.controllers``; the handlers themselves know
nothing about their own URLs.
"""

from fastapi import APIRouter

from api.routes import (
    auth,
    datasets,
    health,
    jobs,
    metrics,
    models,
    organizations,
    risk,
    training,
    webhooks,
)

#: Order matters only for how the generated documentation reads.
ROUTERS = [
    health.router,
    auth.router,
    models.router,
    risk.router,
    metrics.router,
    organizations.router,
    datasets.router,
    jobs.router,
    training.router,
    webhooks.router,
]

api_router = APIRouter()
for _router in ROUTERS:
    api_router.include_router(_router)

__all__ = ["ROUTERS", "api_router"]

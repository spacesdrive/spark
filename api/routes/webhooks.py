"""The webhook contract, and an honest refusal to pretend it works."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.controllers import webhooks as controller
from api.dependencies import require_csrf


router = APIRouter(tags=["webhooks"], dependencies=[Depends(require_csrf)])

router.add_api_route(
    "/webhooks/events",
    controller.webhook_events,
    methods=["GET"],
)
router.add_api_route(
    "/webhooks/endpoints",
    controller.list_endpoints,
    methods=["GET"],
)
router.add_api_route(
    "/webhooks/endpoints",
    controller.create_endpoint,
    methods=["POST"],
    status_code=501,
)

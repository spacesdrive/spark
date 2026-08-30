"""Health and public configuration."""

from __future__ import annotations

from fastapi import APIRouter

from api.controllers import health as controller


router = APIRouter(tags=["health"])

router.add_api_route(
    "/health",
    controller.health,
    methods=["GET"],
)
router.add_api_route(
    "/config",
    controller.public_config,
    methods=["GET"],
)

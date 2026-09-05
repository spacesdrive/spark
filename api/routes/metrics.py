"""What the selected model measured, for the dashboard."""

from __future__ import annotations

from fastapi import APIRouter

from api.controllers import metrics as controller


router = APIRouter(tags=["metrics"])

router.add_api_route(
    "/metrics/overview",
    controller.overview,
    methods=["GET"],
)
router.add_api_route(
    "/metrics/charts",
    controller.charts,
    methods=["GET"],
)
router.add_api_route(
    "/metrics/limitations",
    controller.limitations,
    methods=["GET"],
)
router.add_api_route(
    "/metrics/rings",
    controller.rings,
    methods=["GET"],
)

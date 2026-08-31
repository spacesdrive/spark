"""Listing models, and moving one into or out of production."""

from __future__ import annotations

from fastapi import APIRouter

from api.controllers import models as controller


router = APIRouter(tags=["models"])

router.add_api_route(
    "/models",
    controller.list_models,
    methods=["GET"],
)
router.add_api_route(
    "/models/{model_id}",
    controller.get_model,
    methods=["GET"],
)
router.add_api_route(
    "/models/{model_id}/activate",
    controller.activate_model,
    methods=["POST"],
)
router.add_api_route(
    "/models/{model_id}/deactivate",
    controller.deactivate_model,
    methods=["POST"],
)
router.add_api_route(
    "/models/{model_id}/promote",
    controller.promote_model,
    methods=["POST"],
)
router.add_api_route(
    "/models/{model_id}/reject",
    controller.reject_model,
    methods=["POST"],
)
router.add_api_route(
    "/organizations/{organization_id}/rollback",
    controller.rollback_production,
    methods=["POST"],
)
router.add_api_route(
    "/organizations/{organization_id}/model-comparison",
    controller.compare_models,
    methods=["GET"],
)

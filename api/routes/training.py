"""Starting and bounding a training run."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.controllers import training as controller
from api.dependencies import require_csrf


router = APIRouter(tags=["training"], dependencies=[Depends(require_csrf)])

router.add_api_route(
    "/training/limits",
    controller.training_limits,
    methods=["GET"],
)
router.add_api_route(
    "/training/jobs",
    controller.create_training_job,
    methods=["POST"],
    status_code=202,
)

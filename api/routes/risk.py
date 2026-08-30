"""Scoring one transaction."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.controllers import risk as controller
from api.dependencies import rate_limit_scoring
from api.validators import ScoreResponse


router = APIRouter(tags=["risk"])

router.add_api_route(
    "/risk/score",
    controller.score_transaction,
    methods=["POST"],
    response_model=ScoreResponse,
    dependencies=[Depends(rate_limit_scoring)],
)
router.add_api_route(
    "/v1/risk/score",
    controller.score_transaction_v1,
    methods=["POST"],
    response_model=ScoreResponse,
    tags=["public api"],
)
router.add_api_route(
    "/risk/thresholds",
    controller.thresholds,
    methods=["GET"],
)

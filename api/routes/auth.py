"""Signing in and out, and reporting who is signed in."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.controllers import auth as controller
from api.dependencies import rate_limit_public
from api.validators import MeResponse


router = APIRouter(prefix="/auth", tags=["auth"])

router.add_api_route(
    "/session",
    controller.create_session,
    methods=["POST"],
    dependencies=[Depends(rate_limit_public)],
)
router.add_api_route(
    "/logout",
    controller.logout,
    methods=["POST"],
)
router.add_api_route(
    "/me",
    controller.me,
    methods=["GET"],
    response_model=MeResponse,
)

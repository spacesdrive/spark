"""Workspaces, their API keys and their usage."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends

from api.controllers import organizations as controller
from api.dependencies import require_csrf
from api.validators import ApiKeyCreated, ApiKeyOut, OrganizationOut


router = APIRouter(tags=["organizations"], dependencies=[Depends(require_csrf)])

router.add_api_route(
    "/organizations",
    controller.list_organizations,
    methods=["GET"],
    response_model=List[OrganizationOut],
)
router.add_api_route(
    "/organizations",
    controller.create_organization,
    methods=["POST"],
    response_model=OrganizationOut,
    status_code=201,
)
router.add_api_route(
    "/organizations/{organization_id}",
    controller.get_organization,
    methods=["GET"],
)
router.add_api_route(
    "/organizations/{organization_id}/api-keys",
    controller.list_api_keys,
    methods=["GET"],
    response_model=List[ApiKeyOut],
)
router.add_api_route(
    "/organizations/{organization_id}/api-keys",
    controller.create_api_key,
    methods=["POST"],
    response_model=ApiKeyCreated,
    status_code=201,
)
router.add_api_route(
    "/api-keys/{key_id}/rotate",
    controller.rotate_api_key,
    methods=["POST"],
    response_model=ApiKeyCreated,
)
router.add_api_route(
    "/api-keys/{key_id}/revoke",
    controller.revoke_api_key,
    methods=["POST"],
    response_model=ApiKeyOut,
)
router.add_api_route(
    "/organizations/{organization_id}/usage",
    controller.usage,
    methods=["GET"],
)

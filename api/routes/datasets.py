"""Uploading, checking, scoring and deleting CSV files."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends

from api.controllers import datasets as controller
from api.dependencies import rate_limit_public, rate_limit_upload
from api.validators import DatasetOut


router = APIRouter(tags=["datasets"])

router.add_api_route(
    "/datasets/format",
    controller.dataset_format,
    methods=["GET"],
)
router.add_api_route(
    "/datasets/example",
    controller.example_dataset,
    methods=["GET"],
)
router.add_api_route(
    "/datasets/upload",
    controller.upload_dataset,
    methods=["POST"],
    response_model=DatasetOut,
    status_code=201,
    dependencies=[Depends(rate_limit_upload)],
)
router.add_api_route(
    "/datasets/{dataset_id}",
    controller.get_dataset,
    methods=["GET"],
    response_model=DatasetOut,
)
router.add_api_route(
    "/datasets/{dataset_id}/validate",
    controller.revalidate_dataset,
    methods=["POST"],
)
router.add_api_route(
    "/datasets/score",
    controller.score_dataset,
    methods=["POST"],
    dependencies=[Depends(rate_limit_public)],
)
router.add_api_route(
    "/datasets/{dataset_id}/preview",
    controller.preview_dataset,
    methods=["GET"],
)
router.add_api_route(
    "/datasets/{dataset_id}",
    controller.delete_dataset,
    methods=["DELETE"],
)
router.add_api_route(
    "/organizations/{organization_id}/datasets",
    controller.list_org_datasets,
    methods=["GET"],
    response_model=List[DatasetOut],
)

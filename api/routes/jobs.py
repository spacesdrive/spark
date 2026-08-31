"""Watching background work and collecting its result."""

from __future__ import annotations

from fastapi import APIRouter

from api.controllers import jobs as controller
from api.validators import JobOut


router = APIRouter(tags=["jobs"])

router.add_api_route(
    "/jobs/{job_id}",
    controller.get_job,
    methods=["GET"],
    response_model=JobOut,
)
router.add_api_route(
    "/jobs/{job_id}/result",
    controller.get_job_result,
    methods=["GET"],
)
router.add_api_route(
    "/jobs/{job_id}/download",
    controller.download_job_result,
    methods=["GET"],
)
router.add_api_route(
    "/jobs",
    controller.list_jobs,
    methods=["GET"],
)

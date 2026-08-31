"""
Job status, results and downloads.

A job is the only way long work is exposed. Its stage is whatever the work
actually reported, and a failed job carries the reason rather than pretending
it is still running.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from api.database import get_db
from api.dependencies import current_user_optional, job_or_404, membership_or_403
from api.models import Job, User
from api.services import jobs as job_util
from api.services.scoring import RESULT_COLUMNS
from api.utils.csvio import write_csv
from api.validators import JobOut


#: Rows are paged. Sending a hundred thousand scored transactions to a browser
#: to draw one chart would be silly; the summaries are computed on the server.
DEFAULT_PAGE = 100
MAX_PAGE = 500


def get_job(
    job_id: str,
    db: DbSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
) -> JobOut:
    """Where a job has got to."""
    job = job_or_404(db, job_id, user)
    return JobOut(**job_util.job_to_dict(job))


def get_job_result(
    job_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=DEFAULT_PAGE, ge=1, le=MAX_PAGE),
    db: DbSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
) -> dict:
    """
    The result of a finished job.

    Summaries and metrics come whole. The per-transaction rows are paged.
    """
    job = job_or_404(db, job_id, user)
    if job.status == "failed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "That job failed.", "reason": "job_failed",
                    "error": job.error},
        )
    if job.status != "succeeded":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "That job has not finished yet.",
                    "reason": "job_running", "stage": job.stage},
        )

    result = dict(job.result or {})
    rows = result.pop("rows", [])
    return {
        **result,
        "job": job_util.job_to_dict(job),
        "rows": rows[offset : offset + limit],
        "row_count": len(rows),
        "offset": offset,
        "limit": limit,
    }


def download_job_result(
    job_id: str,
    db: DbSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
) -> Response:
    """
    The scored rows as a CSV.

    Values that a spreadsheet would run as a formula are prefixed with an
    apostrophe, because these strings came from an uploaded file.
    """
    job = job_or_404(db, job_id, user)
    if job.status != "succeeded":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "That job has not finished yet.",
                    "reason": "job_running"},
        )
    rows = (job.result or {}).get("rows", [])
    body = write_csv(rows, RESULT_COLUMNS)
    return Response(
        content=body,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="spark-results-{job.id}.csv"'
        },
    )


def list_jobs(
    organization_id: Optional[str] = None,
    db: DbSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
) -> dict:
    """Jobs for one organization. Requires membership of it."""
    if not organization_id:
        return {"jobs": []}
    if user is None:
        raise HTTPException(
            status_code=401,
            detail={"message": "Sign in first.", "reason": "authentication_required"},
        )
    membership_or_403(db, organization_id, user)
    rows = db.execute(
        select(Job)
        .where(Job.organization_id == organization_id)
        .order_by(Job.created_at.desc())
        .limit(50)
    ).scalars().all()
    return {"jobs": [job_util.job_to_dict(j) for j in rows]}

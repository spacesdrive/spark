"""
Background jobs.

Scoring a large file takes longer than an HTTP request should. A job row is
created, a worker thread picks it up, and the frontend polls the job.

Progress is reported per stage. When a stage cannot say how far through it is,
the job reports the stage it is in and leaves the number alone. A bar that
climbs on a timer while the work has stalled is worse than no bar.
"""

from __future__ import annotations

import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Optional

from sqlalchemy import func, select

from api.database import SessionLocal
from api.models import Job
from api.utils.ids import new_id, utcnow
from api.config.settings import settings
from api.types.errors import JobLimitError
from api.utils.redaction import safe_error

#: One worker per allowed concurrent job. The models release the GIL inside
#: numpy, LightGBM and torch, so threads are enough and a process pool would
#: mean loading the models again in each worker.
_executor = ThreadPoolExecutor(
    max_workers=max(1, settings.max_concurrent_jobs), thread_name_prefix="spark-job"
)
_running: Dict[str, bool] = {}
_lock = threading.Lock()


def running_count(organization_id: Optional[str]) -> int:
    with SessionLocal() as db:
        stmt = select(func.count()).select_from(Job).where(
            Job.status.in_(("queued", "running"))
        )
        if organization_id:
            stmt = stmt.where(Job.organization_id == organization_id)
        return int(db.execute(stmt).scalar_one())


def jobs_today(organization_id: str) -> int:
    since = datetime.now(timezone.utc) - timedelta(days=1)
    with SessionLocal() as db:
        return int(
            db.execute(
                select(func.count())
                .select_from(Job)
                .where(Job.organization_id == organization_id)
                .where(Job.created_at >= since)
            ).scalar_one()
        )


def check_limits(organization_id: Optional[str]) -> None:
    """Refuse to queue work that would exceed a configured limit."""
    if running_count(None) >= settings.max_concurrent_jobs:
        raise JobLimitError(
            f"Spark is already running {settings.max_concurrent_jobs} jobs. "
            "Try again when one finishes."
        )
    if organization_id and jobs_today(organization_id) >= settings.max_jobs_per_org_per_day:
        raise JobLimitError(
            f"Your organization has started {settings.max_jobs_per_org_per_day} "
            "jobs in the last 24 hours, which is the limit."
        )


def create_job(
    kind: str,
    organization_id: Optional[str] = None,
    created_by: Optional[str] = None,
    dataset_id: Optional[str] = None,
    model_id: Optional[str] = None,
    params: Optional[dict] = None,
) -> Job:
    job = Job(
        id=new_id("job"),
        organization_id=organization_id,
        created_by=created_by,
        kind=kind,
        status="queued",
        stage="queued",
        progress=0.0,
        dataset_id=dataset_id,
        model_id=model_id,
        params=params or {},
        result={},
    )
    with SessionLocal() as db:
        db.add(job)
        db.commit()
        db.refresh(job)
    return job


def update_job(job_id: str, **fields) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        for k, v in fields.items():
            setattr(job, k, v)
        db.commit()


def get_job(job_id: str) -> Optional[Job]:
    with SessionLocal() as db:
        return db.get(Job, job_id)


def progress_reporter(job_id: str) -> Callable[[str, float], None]:
    """A callback the work can call to publish where it has got to."""

    def report(stage: str, progress: float) -> None:
        update_job(job_id, stage=stage, progress=float(max(0.0, min(1.0, progress))))

    return report


def submit(job_id: str, work: Callable[[Callable[[str, float], None]], dict]) -> None:
    """
    Run ``work`` on a worker thread and record what happened.

    ``work`` receives the progress callback and returns the result dictionary.
    Any exception is stored on the job and reported as a failure, never
    swallowed.
    """

    def runner() -> None:
        with _lock:
            _running[job_id] = True
        update_job(
            job_id, status="running", stage="preparing", started_at=utcnow()
        )
        try:
            result = work(progress_reporter(job_id))
            update_job(
                job_id,
                status="succeeded",
                stage="complete",
                progress=1.0,
                result=result,
                finished_at=utcnow(),
            )
        except Exception as exc:  # noqa: BLE001 - recorded, then re-raised nowhere
            update_job(
                job_id,
                status="failed",
                stage="failed",
                error=safe_error(exc),
                finished_at=utcnow(),
            )
            traceback.print_exc()
        finally:
            with _lock:
                _running.pop(job_id, None)

    _executor.submit(runner)


def job_to_dict(job: Job) -> dict:
    """Job state for the frontend. Never includes a filesystem path."""
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "stage": job.stage,
        "progress": round(float(job.progress), 4),
        "dataset_id": job.dataset_id,
        "model_id": job.model_id,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "elapsed_seconds": _elapsed(job),
        "has_result": bool(job.result),
    }


def _elapsed(job: Job) -> Optional[float]:
    if not job.started_at:
        return None
    end = job.finished_at or datetime.now(timezone.utc).replace(tzinfo=None)
    start = job.started_at
    return round((end - start).total_seconds(), 2)

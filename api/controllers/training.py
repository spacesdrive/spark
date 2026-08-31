"""
Custom model training.

Training runs the same pipeline as the built-in model, on the organization's
own transactions. It produces a candidate, never a production model: a person
has to look at the held-out numbers and approve it.

Every check here is real and runs before any work is queued. You must be signed
in, you must be allowed to train in this organization, the dataset must belong
to that organization, it must be marked as training data, it must carry labels,
and it must fall inside the row limits.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession

from api.config.settings import settings
from api.database import SessionLocal, get_db
from api.dependencies import current_user, dataset_or_404, membership_or_403
from api.models import ModelRecord, User
from api.services import jobs as job_util
from api.services import training as training_runner
from api.utils.ids import new_id


class TrainingRequest(BaseModel):
    organization_id: str
    dataset_id: str
    name: str = Field(..., min_length=1, max_length=120)
    base_model: str = Field(default="hybrid-v1")


def training_limits() -> dict:
    """
    The limits a training job runs under. The real configured values.

    This returns the shared limit set plus the training-only extras, rather
    than a hand-written subset. Listing fields by hand here once left the
    upload limit and the accepted formats out, which the dashboard needs to
    draw the upload area.
    """
    return {
        **settings.limits_public(),
        "max_model_bytes": settings.max_model_bytes,
        "requires_labels": True,
        "status": "available",
        "status_note": (
            "Training uses the same pipeline as the built-in model, on your "
            "own transactions. It produces a candidate model with held-out "
            "results, which you can compare and then approve. Nothing you "
            "train is used for scoring until you activate it."
        ),
    }


def create_training_job(
    payload: TrainingRequest,
    db: DbSession = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """
    Check a training request, then queue it.

    The checks below are the gate. Once a job is queued it will run, so
    anything that would make the result meaningless is refused here rather
    than discovered halfway through.
    """
    membership_or_403(db, payload.organization_id, user, roles={"owner", "admin"})
    dataset = dataset_or_404(db, payload.dataset_id, user, anon_ok=False)

    if dataset.organization_id != payload.organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "That dataset was not found.", "reason": "not_found"},
        )
    if dataset.kind != "training":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "That dataset was uploaded for testing, not for "
                           "training. Upload it again as training data so the "
                           "two are never mixed up.",
                "reason": "wrong_dataset_kind",
            },
        )
    if not dataset.has_labels:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Training needs labels. Add a column saying what "
                           "actually happened: 1 for fraud, 0 for normal.",
                "reason": "labels_required",
            },
        )
    if dataset.n_rows < settings.min_training_rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": f"That dataset has {dataset.n_rows:,} rows. Training "
                           f"needs at least {settings.min_training_rows:,} so "
                           f"there is enough left over to test the result "
                           f"honestly.",
                "reason": "dataset_too_small",
            },
        )
    if dataset.n_rows > settings.max_training_rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": f"That dataset has {dataset.n_rows:,} rows, above "
                           f"the {settings.max_training_rows:,} row limit.",
                "reason": "dataset_too_large",
            },
        )

    try:
        job_util.check_limits(payload.organization_id)
    except job_util.JobLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"message": str(exc), "reason": "job_limit"},
        ) from None

    model = ModelRecord(
        id=new_id("mdl"),
        organization_id=payload.organization_id,
        name=payload.name.strip(),
        version="pending",
        kind="custom",
        status="training",
        base_model=payload.base_model,
        dataset_id=dataset.id,
        created_by=user.id,
        is_active=False,
        metrics={},
    )
    db.add(model)
    db.commit()

    job = job_util.create_job(
        kind="training",
        organization_id=payload.organization_id,
        created_by=user.id,
        dataset_id=dataset.id,
        model_id=model.id,
        params={"name": model.name, "base_model": payload.base_model},
    )

    def work(report):
        try:
            return training_runner.train_custom_model(model.id, dataset.id, report)
        except Exception:
            # The job runner records the failure, but the model row is its own
            # record and would otherwise sit in "training" for ever.
            with SessionLocal() as inner:
                failed = inner.get(ModelRecord, model.id)
                if failed is not None:
                    failed.status = "failed"
                    inner.commit()
            raise

    job_util.submit(job.id, work)

    return {
        "job": job_util.job_to_dict(job),
        "model_id": model.id,
        "note": (
            "Training has started. It produces a candidate model with held-out "
            "results. Nothing changes for your live traffic until you activate "
            "it."
        ),
    }

"""
Uploading, checking and scoring a dataset.

The flow the dashboard walks through:

    upload  ->  validate  ->  map columns  ->  score  ->  results  ->  download

Scoring runs as a job, because a hundred thousand rows takes longer than a
request should. Every step reports what it actually did.
"""

from __future__ import annotations

from datetime import timedelta
from typing import List, Optional

from fastapi import (
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from api.config.settings import settings
from api.database import get_db
from api.dependencies import (
    current_user_optional,
    dataset_or_404,
    membership_or_403,
)
from api.models import DatasetRecord, User
from api.services import datasets as ds_util
from api.services import engine as engine_state
from api.services import jobs as job_util
from api.services.scoring import score_dataframe
from api.utils.filenames import sanitize_display_name
from api.utils.ids import new_id, utcnow
from api.validators import DatasetOut, ScoreDatasetRequest


def _out(rec: DatasetRecord) -> DatasetOut:
    return DatasetOut(
        id=rec.id,
        original_name=rec.original_name,
        kind=rec.kind,
        size_bytes=rec.size_bytes,
        n_rows=rec.n_rows,
        columns=rec.columns or [],
        has_labels=rec.has_labels,
        status=rec.status,
        created_at=rec.created_at.isoformat(),
        expires_at=rec.expires_at.isoformat() if rec.expires_at else None,
        validation=rec.validation or {},
    )


def dataset_format() -> dict:
    """
    What a dataset has to look like. One source of truth for the docs page.

    The column list is generated from the same table the validator uses, so
    the documentation cannot drift away from what the backend accepts.
    """
    return {
        "accepted_formats": ["csv"],
        "encoding": "UTF-8",
        "columns": ds_util.column_reference(),
        "limits": settings.limits_public(),
        "label_meaning": {
            "1": "Fraud, confirmed after the fact.",
            "0": "Normal, confirmed after the fact.",
            "2 or empty": "Outcome never confirmed. The row is still scored "
                          "and still counts towards history, but it is left "
                          "out of any accuracy measurement.",
        },
        "example_csv": (
            "transaction_id,timestamp,customer_id,merchant_id,amount,"
            "location,payment_type,label\n"
            "txn_0001,2026-03-01T10:04:00Z,cust_8813,merch_204,49.90,IN-KA,upi,0\n"
            "txn_0002,2026-03-01T10:04:06Z,cust_9921,merch_204,1.00,IN-KA,upi,1\n"
        ),
        "notes": [
            "Each row is one transaction.",
            "Timestamps are only used to put rows in order. The model counts "
            "velocity in transactions, not in seconds, so timestamps are "
            "converted to positions in a sequence.",
            "An uploaded file is scored using only its own history. The "
            "customers and merchants in it are not the ones the model was "
            "trained on, so early rows behave like first-time customers.",
            "Without a label column, Spark can score every row but cannot "
            "measure precision or recall.",
        ],
    }


def example_dataset() -> dict:
    """
    The dataset Spark itself was measured on, offered as a built-in example.

    It is offered so the dashboard can be tried without uploading anything. It
    is development data, not merchant traffic, and scoring it does not predict
    how the model behaves on a different business.
    """
    meta = engine_state.read_metadata()
    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"message": "No trained model is available.",
                    "reason": "model_unavailable"},
        )
    dataset = meta.get("dataset", {})
    return {
        "id": "spark-example",
        "name": "Spark Example Test Data",
        "description": (
            "The dataset used while building Spark. It is included so you can "
            "try the dashboard without uploading anything of your own."
        ),
        "caution": (
            "This is development data. Good results on it do not mean the "
            "model will do as well on your business data."
        ),
        "source": "S-FFSD, from the AI4Risk/antifraud research repository",
        "simulated": True,
        "rows": dataset.get("raw_stats", {}).get("n_rows"),
        "labeled": dataset.get("raw_stats", {}).get("n_labeled"),
        "splits": dataset.get("splits", []),
        "columns": ds_util.column_reference(),
    }


async def upload_dataset(
    file: UploadFile = File(...),
    kind: str = Form(default="test"),
    organization_id: Optional[str] = Form(default=None),
    db: DbSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
) -> DatasetOut:
    """
    Take a CSV, check it, and store it under a random name.

    Guests may upload a test dataset. Training datasets always belong to an
    organization, so they need an account.
    """
    if kind not in ("test", "training"):
        raise HTTPException(
            status_code=400,
            detail={"message": "A dataset is either 'test' or 'training'.",
                    "reason": "invalid_kind"},
        )
    if kind == "training":
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "message": "Training data belongs to an organization, so "
                               "you need an account to upload it.",
                    "reason": "authentication_required",
                },
            )
        if not organization_id:
            raise HTTPException(
                status_code=400,
                detail={"message": "Choose an organization for this training "
                                   "data.", "reason": "organization_required"},
            )
    if organization_id:
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"message": "Sign in first.",
                        "reason": "authentication_required"},
            )
        membership_or_403(db, organization_id, user)

    content = await file.read()
    try:
        ds_util.check_upload(file.filename or "", content)
    except ds_util.DatasetError as exc:
        raise HTTPException(status_code=400, detail=exc.as_dict()) from exc

    stored, path = ds_util.store_upload(content)
    max_rows = (
        settings.max_training_rows if kind == "training" else settings.max_test_rows
    )
    try:
        frame = ds_util.read_csv(path, max_rows=max_rows)
        result = ds_util.validate(frame)
    except ds_util.DatasetError as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=exc.as_dict()) from exc

    rec = DatasetRecord(
        id=new_id("ds"),
        organization_id=organization_id,
        uploaded_by=user.id if user else None,
        kind=kind,
        original_name=sanitize_display_name(file.filename or "upload.csv"),
        stored_name=stored,
        size_bytes=len(content),
        sha256=ds_util.sha256_of(content),
        n_rows=result.n_rows,
        columns=result.columns,
        has_labels=result.has_labels,
        status="ready" if result.ok else "needs_attention",
        validation=result.as_dict(),
        expires_at=utcnow() + timedelta(hours=settings.dataset_retention_hours),
    )
    db.add(rec)
    db.commit()
    return _out(rec)


def get_dataset(
    dataset_id: str,
    db: DbSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
) -> DatasetOut:
    """One dataset the caller is allowed to see."""
    return _out(dataset_or_404(db, dataset_id, user))


def revalidate_dataset(
    dataset_id: str,
    mapping: Optional[dict] = None,
    db: DbSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
) -> dict:
    """Re-check a dataset, optionally with the column mapping the user chose."""
    rec = dataset_or_404(db, dataset_id, user)
    path = ds_util.upload_path(rec.stored_name)
    if not path.exists():
        raise HTTPException(
            status_code=410,
            detail={"message": "That file has been deleted. Uploads are kept "
                               f"for {settings.dataset_retention_hours} hours.",
                    "reason": "expired"},
        )
    frame = ds_util.read_csv(path)
    result = ds_util.validate(frame, (mapping or {}).get("mapping"))
    rec.validation = result.as_dict()
    rec.has_labels = result.has_labels
    rec.status = "ready" if result.ok else "needs_attention"
    db.commit()
    return result.as_dict()


def score_dataset(
    payload: ScoreDatasetRequest,
    db: DbSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
) -> dict:
    """
    Queue scoring for an uploaded dataset.

    Returns a job. Poll ``/api/jobs/{id}`` for the stage it is in, and read the
    results from ``/api/jobs/{id}/result`` when it succeeds.
    """
    rec = dataset_or_404(db, payload.dataset_id, user)
    if rec.status != "ready":
        raise HTTPException(
            status_code=400,
            detail={
                "message": "That dataset still has problems that stop it being "
                           "scored.",
                "reason": "dataset_invalid",
                "issues": (rec.validation or {}).get("issues", []),
            },
        )
    engine = engine_state.get_engine()
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail={"message": "No model is loaded, so nothing can be scored.",
                    "reason": "model_unavailable"},
        )
    if payload.mode not in engine.metadata["thresholds"]:
        raise HTTPException(
            status_code=400,
            detail={"message": f"'{payload.mode}' is not a threshold setting.",
                    "reason": "invalid_mode"},
        )
    try:
        job_util.check_limits(rec.organization_id)
    except job_util.JobLimitError as exc:
        raise HTTPException(
            status_code=429, detail={"message": str(exc), "reason": "job_limit"}
        ) from exc

    path = ds_util.upload_path(rec.stored_name)
    if not path.exists():
        raise HTTPException(
            status_code=410,
            detail={"message": "That file has been deleted.", "reason": "expired"},
        )
    mapping = payload.mapping or (rec.validation or {}).get("mapping") or {}

    job = job_util.create_job(
        kind="score_dataset",
        organization_id=rec.organization_id,
        created_by=user.id if user else None,
        dataset_id=rec.id,
        model_id=payload.model_id,
        params={"mode": payload.mode},
    )

    def work(report):
        report("Reading the file", 0.05)
        frame = ds_util.read_csv(path)
        spark_frame = ds_util.to_spark_frame(frame, mapping)
        return score_dataframe(
            engine_state.get_engine(), spark_frame, mode=payload.mode,
            progress=report,
        )

    job_util.submit(job.id, work)
    return job_util.job_to_dict(job_util.get_job(job.id))


def preview_dataset(
    dataset_id: str,
    rows: int = 20,
    db: DbSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
) -> dict:
    """First few rows, so the user can see Spark read the file correctly."""
    rec = dataset_or_404(db, dataset_id, user)
    path = ds_util.upload_path(rec.stored_name)
    if not path.exists():
        raise HTTPException(
            status_code=410,
            detail={"message": "That file has been deleted.", "reason": "expired"},
        )
    frame = ds_util.read_csv(path)
    n = max(1, min(int(rows), 100))
    return {
        "columns": list(frame.columns),
        "rows": frame.head(n).to_dict(orient="records"),
        "total_rows": len(frame),
    }


def delete_dataset(
    dataset_id: str,
    db: DbSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
) -> dict:
    """Delete an upload now, rather than waiting for the retention window."""
    rec = dataset_or_404(db, dataset_id, user)
    ds_util.upload_path(rec.stored_name).unlink(missing_ok=True)
    rec.deleted_at = utcnow()
    rec.status = "deleted"
    db.commit()
    return {"deleted": True, "id": rec.id}


def list_org_datasets(
    organization_id: str,
    db: DbSession = Depends(get_db),
    user: User = Depends(current_user_optional),
) -> List[DatasetOut]:
    """Datasets belonging to one organization."""
    if user is None:
        raise HTTPException(
            status_code=401,
            detail={"message": "Sign in first.", "reason": "authentication_required"},
        )
    membership_or_403(db, organization_id, user)
    rows = db.execute(
        select(DatasetRecord)
        .where(DatasetRecord.organization_id == organization_id)
        .where(DatasetRecord.deleted_at.is_(None))
        .order_by(DatasetRecord.created_at.desc())
    ).scalars().all()
    return [_out(r) for r in rows]

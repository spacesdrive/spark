"""Long work that must not block an HTTP request."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from api.database.base import Base
from api.utils.ids import utcnow


class Job(Base):
    """
    Long work that must not block an HTTP request.

    ``stage`` is the honest unit here. When the underlying step cannot report a
    percentage, the API reports the stage it is in and leaves ``progress``
    where it was rather than inventing a number that creeps upward.
    """

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    created_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(30))  # score_dataset|train_model
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(60), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    dataset_id: Mapped[Optional[str]] = mapped_column(ForeignKey("datasets.id"))
    model_id: Mapped[Optional[str]] = mapped_column(String(64))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[Optional[str]] = mapped_column(Text)
    result_path: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

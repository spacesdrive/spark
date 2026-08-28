"""Uploaded CSVs."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from api.database.base import Base
from api.utils.ids import utcnow


class DatasetRecord(Base):
    """An uploaded CSV. The file on disk has a random name, never the user's."""

    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    uploaded_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(20), default="test")  # test|training
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(80))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    n_rows: Mapped[int] = mapped_column(Integer, default=0)
    columns: Mapped[dict] = mapped_column(JSON, default=list)
    has_labels: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="uploaded")
    validation: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

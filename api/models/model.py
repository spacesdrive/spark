"""Models the dashboard can select."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from api.database.base import Base
from api.utils.ids import utcnow


class ModelRecord(Base):
    """
    A model the dashboard can select.

    Built-in models have no organization and are visible to everyone. Custom
    models belong to the organization that trained them and to nobody else.
    """

    __tablename__ = "models"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    version: Mapped[str] = mapped_column(String(60))
    kind: Mapped[str] = mapped_column(String(20), default="builtin")  # builtin|custom
    status: Mapped[str] = mapped_column(String(20), default="ready")
    base_model: Mapped[Optional[str]] = mapped_column(String(64))
    dataset_id: Mapped[Optional[str]] = mapped_column(ForeignKey("datasets.id"))
    description: Mapped[Optional[str]] = mapped_column(Text)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    artifact_path: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    #: When this model was last promoted to production. Null means never.
    promoted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

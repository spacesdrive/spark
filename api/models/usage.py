"""One recorded API call."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from api.database.base import Base
from api.utils.ids import utcnow


class UsageEvent(Base):
    """One API call, for the usage page and for rate limiting evidence."""

    __tablename__ = "usage_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    api_key_id: Mapped[Optional[str]] = mapped_column(ForeignKey("api_keys.id"))
    mode: Mapped[str] = mapped_column(String(10), default="test")
    endpoint: Mapped[str] = mapped_column(String(120))
    status_code: Mapped[int] = mapped_column(Integer)
    decision: Mapped[Optional[str]] = mapped_column(String(20))
    risk_score: Mapped[Optional[float]] = mapped_column(Float)
    amount: Mapped[Optional[float]] = mapped_column(Float)
    latency_ms: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

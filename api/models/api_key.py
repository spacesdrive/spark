"""Keys a server calls the risk API with."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from api.database.base import Base
from api.utils.ids import utcnow


class ApiKey(Base):
    """
    An API key.

    Only a hash is stored. The full secret is returned once, at creation, and
    cannot be recovered afterwards. ``prefix`` and ``last4`` exist so the
    dashboard can show a recognisable masked form.
    """

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    mode: Mapped[str] = mapped_column(String(10))  # test|live
    prefix: Mapped[str] = mapped_column(String(20), index=True)
    last4: Mapped[str] = mapped_column(String(8))
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    rotated_from: Mapped[Optional[str]] = mapped_column(String(64))

    @property
    def masked(self) -> str:
        return f"{self.prefix}...{self.last4}"

    @property
    def active(self) -> bool:
        return self.revoked_at is None

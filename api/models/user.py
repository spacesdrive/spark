"""People, and their signed-in browser sessions."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.database.base import Base
from api.utils.ids import utcnow


class User(Base):
    """Someone who signed in. Identity itself lives in Supabase."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    supabase_user_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(200))
    avatar_url: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user")


class Session(Base):
    """A signed-in browser session. The cookie holds the id, never a token."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    user_agent: Mapped[Optional[str]] = mapped_column(String(400))

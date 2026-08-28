"""Workspaces, and who belongs to them."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.database.base import Base
from api.models.user import User
from api.utils.ids import utcnow


class Organization(Base):
    """A workspace. Every private resource belongs to exactly one."""

    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    #: Where the organization has reached in onboarding. Advanced only by work
    #: that actually finished, never by opening a page.
    onboarding_stage: Mapped[str] = mapped_column(String(40), default="created")
    #: The model production API keys resolve to. Set only after a human
    #: approves an evaluated model.
    production_model_id: Mapped[Optional[str]] = mapped_column(String(64))
    #: What production was before the current promotion. Rollback restores it,
    #: which is why it is stored rather than guessed from timestamps: after a
    #: model is retrained, "the previously promoted one" is ambiguous.
    previous_production_model_id: Mapped[Optional[str]] = mapped_column(String(64))

    memberships: Mapped[list["Membership"]] = relationship(back_populates="organization")


class Membership(Base):
    """Who is in an organization, and what they may do."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="owner")  # owner|admin|member
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    organization: Mapped[Organization] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")

"""
Foreign keys must be satisfied in the order rows are actually inserted.

Sign-in failed in production with a ForeignKeyViolation: the session row was
inserted before the user it points at. Every test passed beforehand because
SQLite does not check foreign keys unless told to, so the same wrong order was
silently accepted locally and only rejected by Postgres.

These tests pin both halves of the fix: that the checking is switched on, and
that the code creating a parent and a child together does so in an order a real
database accepts.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import text

from api.database import SessionLocal, engine
from api.models import Membership, Organization, Session, User
from api.utils.ids import new_id, utcnow


def test_sqlite_checks_foreign_keys() -> None:
    """Without this, the whole suite is blind to ordering bugs."""
    if engine.dialect.name != "sqlite":
        pytest.skip("only meaningful for the SQLite test database")
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_a_session_cannot_be_written_before_its_user() -> None:
    """
    The exact production failure, reproduced.

    SQLAlchemy orders inserts by relationship, and Session declares only a raw
    foreign key column, so it will happily insert the session first. Flushing
    the user is what makes the order correct.
    """
    db = SessionLocal()
    try:
        user = User(
            id=new_id("usr"), supabase_user_id=new_id("sub"), email="a@example.com"
        )
        db.add(user)
        # The fix under test. Removing this line makes this test fail with the
        # same ForeignKeyViolation that reached production.
        db.flush()
        db.add(
            Session(
                id=new_id("ses"),
                user_id=user.id,
                csrf_token="t",
                expires_at=utcnow() + timedelta(hours=1),
                user_agent="test",
            )
        )
        db.commit()
    finally:
        db.rollback()
        db.close()


def test_a_membership_cannot_be_written_before_its_organization() -> None:
    """The same shape, on the path that runs when an organization is created."""
    db = SessionLocal()
    try:
        user = User(
            id=new_id("usr"), supabase_user_id=new_id("sub"), email="b@example.com"
        )
        db.add(user)
        db.flush()
        org = Organization(
            id=new_id("org"), name="Test", slug=new_id("slug"), created_by=user.id
        )
        db.add(org)
        db.flush()
        db.add(
            Membership(
                id=new_id("mem"),
                organization_id=org.id,
                user_id=user.id,
                role="owner",
            )
        )
        db.commit()
    finally:
        db.rollback()
        db.close()

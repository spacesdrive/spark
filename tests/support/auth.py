"""
Signing a test user in, without going near Supabase.

Tests create the user and the session row directly and then present the same
signed cookie the real sign-in flow would set, so everything after
authentication is exercised for real.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from api.config.settings import settings
from api.database import SessionLocal
from api.lib.sessions import sign_session_id
from api.models import Session, User
from api.utils.ids import new_id, utcnow


def make_user(email: str) -> User:
    """A signed-in user, created directly. Supabase is not called in tests."""
    with SessionLocal() as db:
        user = User(
            id=new_id("usr"),
            supabase_user_id=new_id("sb"),
            email=email,
            display_name=email.split("@")[0],
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


def sign_in(client: TestClient, user: User) -> dict:
    """Create a session row and return the cookies and CSRF header for it."""
    with SessionLocal() as db:
        csrf = "csrf-" + new_id("t")[-12:]
        sess = Session(
            id=new_id("ses"),
            user_id=user.id,
            csrf_token=csrf,
            expires_at=utcnow() + timedelta(hours=1),
        )
        db.add(sess)
        db.commit()
        signed = sign_session_id(sess.id)
    client.cookies.set(settings.session_cookie_name, signed)
    client.cookies.set(settings.csrf_cookie_name, csrf)
    return {"X-CSRF-Token": csrf}


def sign_out(client: TestClient) -> None:
    client.cookies.clear()

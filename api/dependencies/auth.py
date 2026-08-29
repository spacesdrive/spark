"""
Who is calling.

Three answers, and they never mix: a signed-in person with a session cookie, a
server with an API key, or a guest. Guests are a valid caller, so the optional
form never raises.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from api.config.settings import settings
from api.database.session import get_db
from api.lib import api_keys, sessions
from api.models import ApiKey, Organization, Session, User
from api.types.auth import ApiCaller
from api.utils.ids import utcnow

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


#: How stale "last seen" is allowed to get. Five minutes is far finer than any
#: question the value is used to answer.
LAST_SEEN_INTERVAL_SECONDS = 300


def _older_than(moment: Optional[datetime], seconds: int) -> bool:
    """
    Whether a stored timestamp is older than ``seconds`` ago.

    The column has no timezone, so values read back are naive while utcnow() is
    aware, and subtracting one from the other raises. Everything Spark stores is
    UTC, so the naive value is labelled as such before comparing.
    """
    if moment is None:
        return True
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - moment).total_seconds() > seconds


def current_user_optional(
    request: Request, db: DbSession = Depends(get_db)
) -> Optional[User]:
    """The signed-in user, or None. Never raises: guests are a valid caller."""
    raw = request.cookies.get(settings.session_cookie_name)
    if not raw:
        return None
    session_id = sessions.verify_session_cookie(raw)
    if not session_id:
        return None
    sess = db.get(Session, session_id)
    if sess is None or sess.revoked:
        return None
    if sess.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        return None
    user = db.get(User, sess.user_id)
    if user is None:
        return None
    request.state.session = sess

    # "Last seen" only needs to be roughly right, and writing it on every
    # request means a database write per request. That was nearly free against
    # a local SQLite file; against a PostgreSQL instance in another region it
    # is a round trip on the critical path of every authenticated call. Writing
    # it at most once every few minutes gives the same information.
    if _older_than(user.last_seen_at, LAST_SEEN_INTERVAL_SECONDS):
        user.last_seen_at = utcnow()
        db.commit()
    return user


def current_user(user: Optional[User] = Depends(current_user_optional)) -> User:
    """The signed-in user. Refuses guests."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "message": "Sign in to use this.",
                "reason": "authentication_required",
            },
        )
    return user


def require_csrf(request: Request, db: DbSession = Depends(get_db)) -> None:
    """
    Check the CSRF token on state-changing requests made with a cookie.

    The session cookie is SameSite, which stops most cross-site posts on its
    own. This is the second lock: the request must also echo a token that only
    a page on our own origin can read.
    """
    if request.method in SAFE_METHODS:
        return
    if not request.cookies.get(settings.session_cookie_name):
        return  # API-key callers do not use cookies and cannot be CSRF'd
    header = request.headers.get("x-csrf-token")
    cookie = request.cookies.get(settings.csrf_cookie_name)
    if not sessions.csrf_ok(header, cookie):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "This request could not be verified. Reload the page "
                           "and try again.",
                "reason": "csrf_failed",
            },
        )


def api_key_caller(
    request: Request, db: DbSession = Depends(get_db)
) -> Optional[ApiCaller]:
    """Resolve an ``Authorization: Bearer sk_...`` header to an organization."""
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    secret = header[7:].strip()
    if api_keys.key_mode(secret) is None:
        return None

    key = db.execute(
        select(ApiKey).where(ApiKey.key_hash == api_keys.hash_api_key(secret))
    ).scalar_one_or_none()
    if key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "That API key is not valid.",
                    "reason": "invalid_api_key"},
        )
    if key.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "That API key has been revoked.",
                    "reason": "revoked_api_key"},
        )
    org = db.get(Organization, key.organization_id)
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "That API key is not valid.",
                    "reason": "invalid_api_key"},
        )
    # Same reasoning as "last seen" above: this is a write on the critical path
    # of every scored transaction, and the value only needs to be approximate.
    if _older_than(key.last_used_at, LAST_SEEN_INTERVAL_SECONDS):
        key.last_used_at = utcnow()
        db.commit()
    return ApiCaller(key, org)


def require_api_key(caller: Optional[ApiCaller] = Depends(api_key_caller)) -> ApiCaller:
    if caller is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "message": "Send your API key as: Authorization: Bearer "
                           "sk_test_...",
                "reason": "authentication_required",
            },
        )
    return caller

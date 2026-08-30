"""
Sign in, sign out, and who am I.

Google sign-in runs entirely in Supabase. The browser finishes that flow and
hands the resulting access token here once. This endpoint verifies it, creates
a server-side session, and replies with an HttpOnly cookie. From then on the
dashboard authenticates with the cookie, so no token sits in localStorage where
a script could read it.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from api.config.settings import settings
from api.database import get_db
from api.dependencies import current_user_optional
from api.lib import sessions
from api.models import Membership, Organization, Session, User
from api.services import supabase
from api.types.auth import AuthError
from api.utils.ids import new_id, utcnow
from api.validators import MeResponse, SessionRequest


def _set_cookies(response: Response, session_id: str, csrf_token: str) -> None:
    common = {
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
        "path": "/",
        "max_age": settings.session_ttl_hours * 3600,
    }
    if settings.cookie_domain:
        common["domain"] = settings.cookie_domain
    # The session cookie is HttpOnly so page scripts cannot read it. The CSRF
    # cookie deliberately is not: the page has to read it to echo it back.
    response.set_cookie(
        settings.session_cookie_name,
        sessions.sign_session_id(session_id),
        httponly=True,
        **common,
    )
    response.set_cookie(
        settings.csrf_cookie_name, csrf_token, httponly=False, **common
    )


def _clear_cookies(response: Response) -> None:
    kw = {"path": "/"}
    if settings.cookie_domain:
        kw["domain"] = settings.cookie_domain
    response.delete_cookie(settings.session_cookie_name, **kw)
    response.delete_cookie(settings.csrf_cookie_name, **kw)


def _org_payload(db: DbSession, user: User) -> list:
    rows = db.execute(
        select(Membership, Organization)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(Membership.user_id == user.id)
    ).all()
    return [
        {
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "role": m.role,
            "onboarding_stage": org.onboarding_stage,
            "production_model_id": org.production_model_id,
            "created_at": org.created_at.isoformat(),
        }
        for m, org in rows
    ]


async def create_session(
    payload: SessionRequest,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
) -> dict:
    """Turn a verified Supabase token into a session cookie."""
    if not settings.auth_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": "Sign-in is not configured on this server.",
                "reason": "auth_not_configured",
            },
        )
    try:
        identity = supabase.verify_supabase_token(payload.access_token)
    except AuthError as exc:
        # A legacy project can still be verified by asking Supabase directly.
        try:
            identity = await supabase.fetch_supabase_user(payload.access_token)
        except AuthError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"message": str(exc), "reason": "invalid_token"},
            ) from exc

    user = db.execute(
        select(User).where(User.supabase_user_id == identity.user_id)
    ).scalar_one_or_none()
    if user is None:
        user = User(
            id=new_id("usr"),
            supabase_user_id=identity.user_id,
            email=identity.email,
            display_name=identity.display_name,
            avatar_url=identity.avatar_url,
        )
        db.add(user)
    else:
        user.email = identity.email or user.email
        user.display_name = identity.display_name or user.display_name
        user.avatar_url = identity.avatar_url or user.avatar_url
        user.last_seen_at = utcnow()

    # The session row points at this user, and SQLAlchemy orders inserts by
    # relationship, not by the raw foreign key column. Session declares no
    # relationship to User, so without this flush the ORM is free to insert the
    # session first and Postgres rejects it. SQLite silently allowed it, which
    # is why this only ever failed in production.
    db.flush()

    csrf_token = sessions.new_csrf_token()
    sess = Session(
        id=new_id("ses"),
        user_id=user.id,
        csrf_token=csrf_token,
        expires_at=utcnow() + timedelta(hours=settings.session_ttl_hours),
        user_agent=(request.headers.get("user-agent") or "")[:400],
    )
    db.add(sess)
    db.commit()

    _set_cookies(response, sess.id, csrf_token)
    return {
        "authenticated": True,
        "user": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "avatar_url": user.avatar_url,
        },
        "organizations": _org_payload(db, user),
        "csrf_token": csrf_token,
    }


def logout(
    response: Response,
    request: Request,
    db: DbSession = Depends(get_db),
    user: User | None = Depends(current_user_optional),
) -> dict:
    """End the session on the server, then clear the cookies."""
    raw = request.cookies.get(settings.session_cookie_name)
    if raw:
        session_id = sessions.verify_session_cookie(raw)
        if session_id:
            sess = db.get(Session, session_id)
            if sess is not None:
                sess.revoked = True
                db.commit()
    _clear_cookies(response)
    return {"authenticated": False}


def me(
    request: Request,
    db: DbSession = Depends(get_db),
    user: User | None = Depends(current_user_optional),
) -> MeResponse:
    """Who the caller is. Guests get ``authenticated: false``, not an error."""
    if user is None:
        return MeResponse(authenticated=False)
    sess = getattr(request.state, "session", None)
    return MeResponse(
        authenticated=True,
        user={
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "avatar_url": user.avatar_url,
            "created_at": user.created_at.isoformat(),
        },
        organizations=_org_payload(db, user),
        csrf_token=sess.csrf_token if sess else None,
    )

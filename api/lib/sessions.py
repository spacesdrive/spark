"""
Session cookies and CSRF tokens.

The cookie carries a session id and a signature, never a token, so a forged
cookie is rejected before anything touches the database.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from typing import Optional

from api.config.settings import settings


def new_csrf_token() -> str:
    return secrets.token_urlsafe(24)


def sign_session_id(session_id: str) -> str:
    """Session id plus a signature, so a forged cookie is rejected early."""
    mac = hmac.new(
        settings.session_secret.encode(), session_id.encode(), hashlib.sha256
    ).digest()
    return f"{session_id}.{base64.urlsafe_b64encode(mac).decode().rstrip('=')}"


def verify_session_cookie(value: str) -> Optional[str]:
    """Return the session id if the signature is good, otherwise None."""
    if not value or "." not in value or not settings.session_secret:
        return None
    session_id, _, sig = value.rpartition(".")
    expected = sign_session_id(session_id).rpartition(".")[2]
    return session_id if hmac.compare_digest(sig, expected) else None


def csrf_ok(header_value: Optional[str], cookie_value: Optional[str]) -> bool:
    """Double submit: the header must equal the readable CSRF cookie."""
    if not header_value or not cookie_value:
        return False
    return hmac.compare_digest(header_value, cookie_value)

"""
Verifying the tokens Supabase issues.

Sign-in itself is delegated to Supabase, which runs the Google OAuth flow.
This module only checks the token that came back, and never trusts one without
a verified signature.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import httpx
import jwt
from jwt import PyJWKClient

from api.config.settings import settings
from api.types.auth import AuthError, SupabaseIdentity


class _JwksCache:
    """
    Supabase caches its JWKS response for ten minutes at the edge, so caching
    it here for the same length keeps key rotation working without fetching
    the key set on every sign-in.
    """

    def __init__(self, ttl_seconds: int = 600):
        self.ttl = ttl_seconds
        self._client: Optional[PyJWKClient] = None
        self._fetched_at = 0.0

    def client(self) -> PyJWKClient:
        now = time.time()
        if self._client is None or now - self._fetched_at > self.ttl:
            self._client = PyJWKClient(settings.supabase_jwks_url, cache_keys=True)
            self._fetched_at = now
        return self._client


_jwks = _JwksCache()


def verify_supabase_token(token: str) -> SupabaseIdentity:
    """
    Check a Supabase access token and pull the identity out of it.

    Newer projects sign with ES256 or RS256 and publish the public keys, so
    verification happens locally against the JWKS endpoint. Projects still on
    the legacy shared secret sign with HS256, which needs
    ``SUPABASE_JWT_SECRET``. Both are supported; nothing is trusted without a
    verified signature.
    """
    if not settings.supabase_url:
        raise AuthError("Sign-in is not configured on this server.")

    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise AuthError("That sign-in token could not be read.") from exc

    alg = header.get("alg", "")
    options = {"verify_aud": False}
    try:
        if alg == "HS256":
            if not settings.supabase_jwt_secret:
                raise AuthError(
                    "This project signs tokens with a shared secret, so "
                    "SUPABASE_JWT_SECRET must be set on the server."
                )
            claims = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                issuer=settings.supabase_issuer,
                options=options,
            )
        else:
            signing_key = _jwks.client().get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256", "RS256", "EdDSA"],
                issuer=settings.supabase_issuer,
                options=options,
            )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Your sign-in has expired. Please sign in again.") from exc
    except jwt.InvalidIssuerError as exc:
        raise AuthError("That token was issued by a different project.") from exc
    except AuthError:
        raise
    except Exception as exc:  # noqa: BLE001 - any verification failure is a refusal
        raise AuthError("That sign-in token is not valid.") from exc

    return _identity_from_claims(claims)


def _identity_from_claims(claims: Dict[str, Any]) -> SupabaseIdentity:
    user_id = claims.get("sub")
    if not user_id:
        raise AuthError("That token has no user id.")
    meta = claims.get("user_metadata") or {}
    email = claims.get("email") or meta.get("email") or ""
    return SupabaseIdentity(
        user_id=str(user_id),
        email=str(email),
        display_name=meta.get("full_name") or meta.get("name"),
        avatar_url=meta.get("avatar_url") or meta.get("picture"),
    )


async def fetch_supabase_user(token: str) -> SupabaseIdentity:
    """
    Ask Supabase who a token belongs to.

    Used as a fallback when local verification cannot be done, for example on
    a legacy project where the server was not given the JWT secret. It costs a
    network round trip, which is why it is not the default path.
    """
    url = f"{settings.supabase_url.rstrip('/')}/auth/v1/user"
    headers = {"Authorization": f"Bearer {token}", "apikey": settings.supabase_anon_key}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=headers)
    if resp.status_code != 200:
        raise AuthError("That sign-in token is not valid.")
    body = resp.json()
    meta = body.get("user_metadata") or {}
    return SupabaseIdentity(
        user_id=str(body["id"]),
        email=str(body.get("email") or ""),
        display_name=meta.get("full_name") or meta.get("name"),
        avatar_url=meta.get("avatar_url") or meta.get("picture"),
    )

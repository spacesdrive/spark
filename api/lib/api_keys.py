"""
Making and checking API keys.

Only a hash is ever stored, so a database dump does not hand over working keys.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Optional, Tuple

from api.config.settings import settings

#: Prefix on every key, so a leaked string is recognisable in a log or a repo
#: scan. Test and live keys are visibly different.
KEY_PREFIXES = {"test": "sk_test", "live": "sk_live"}


def generate_api_key(mode: str) -> Tuple[str, str, str, str]:
    """
    Make a new key.

    Returns ``(secret, prefix, last4, key_hash)``. The secret is shown to the
    user once and then thrown away by the server.
    """
    if mode not in KEY_PREFIXES:
        raise ValueError(f"unknown key mode {mode!r}")
    prefix = KEY_PREFIXES[mode]
    body = secrets.token_urlsafe(32)
    secret = f"{prefix}_{body}"
    return secret, prefix, secret[-4:], hash_api_key(secret)


def hash_api_key(secret: str) -> str:
    """
    Hash a key for storage.

    Keys are 32 bytes of system randomness, so there is nothing to guess and a
    slow password hash would only add latency to every request. The session
    secret is mixed in so a stolen database alone is not enough.
    """
    return hmac.new(
        (settings.session_secret or "spark-dev-secret").encode(),
        secret.encode(),
        hashlib.sha256,
    ).hexdigest()


def key_mode(secret: str) -> Optional[str]:
    for mode, prefix in KEY_PREFIXES.items():
        if secret.startswith(prefix + "_"):
            return mode
    return None

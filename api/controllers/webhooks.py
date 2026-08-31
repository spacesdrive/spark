"""
Webhooks.

Not built. Spark cannot deliver events to your server yet, and this module
does not pretend otherwise: every write refuses with 501 and the word
upcoming, and the listing endpoint returns an empty list alongside the reason
it is empty.

What is real here is the event catalogue. Those names are the events Spark
would emit, taken from things the system already does, so an integration
written against this list will not have to be renamed later.

The signing scheme is documented and implemented as a pure function, so you
can write and test your verification code today against
``sign_payload``. Nothing sends a request yet.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.dependencies import current_user
from api.models import User


#: Events Spark would send. Each maps to something the system already does.
EVENTS = [
    {
        "type": "risk.assessed",
        "when": "A transaction was scored through the API.",
        "status": "upcoming",
    },
    {
        "type": "training.completed",
        "when": "A custom model finished training.",
        "status": "upcoming",
        "blocked_by": "Custom training is not built yet.",
    },
    {
        "type": "model.promoted",
        "when": "A candidate model became the production model.",
        "status": "upcoming",
        "blocked_by": "The model registry is not built yet.",
    },
    {
        "type": "model.rolled_back",
        "when": "A production model was replaced by its predecessor.",
        "status": "upcoming",
        "blocked_by": "The model registry is not built yet.",
    },
]

UPCOMING_NOTE = (
    "Webhooks will let Spark send risk and model events straight to your "
    "application, so you do not have to poll for them. They are not built "
    "yet, so nothing is delivered and no endpoint can be registered."
)


def sign_payload(secret: str, body: str, timestamp: int | None = None) -> str:
    """
    Produce the signature Spark would send in the ``Spark-Signature`` header.

    The timestamp is inside the signed material, so a captured request cannot
    be replayed later against a verifier that checks how old it is.

    Format: ``t=<unix seconds>,v1=<hex hmac sha256 of "<t>.<body>">``
    """
    ts = int(time.time()) if timestamp is None else int(timestamp)
    mac = hmac.new(secret.encode(), f"{ts}.{body}".encode(), hashlib.sha256)
    return f"t={ts},v1={mac.hexdigest()}"


def verify_signature(
    secret: str, body: str, header: str, tolerance_seconds: int = 300
) -> bool:
    """
    Check a signature the way your server should.

    Compared with ``compare_digest`` so the check does not leak, byte by byte,
    how much of a forged signature was correct.
    """
    parts = dict(
        piece.split("=", 1) for piece in header.split(",") if "=" in piece
    )
    ts, sent = parts.get("t"), parts.get("v1")
    if not ts or not sent:
        return False
    # A forged header can carry anything at all in the timestamp. Rejecting it
    # is correct; raising inside the caller's request handler is not.
    try:
        age = abs(time.time() - int(ts))
    except ValueError:
        return False
    if age > tolerance_seconds:
        return False
    expected = hmac.new(
        secret.encode(), f"{ts}.{body}".encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, sent)


class WebhookEndpointCreate(BaseModel):
    organization_id: str
    url: str = Field(..., max_length=500)
    events: list[str] = Field(default_factory=list)


def webhook_events() -> dict:
    """The catalogue of events, and the honest status of each."""
    return {
        "events": EVENTS,
        "status": "upcoming",
        "status_note": UPCOMING_NOTE,
        "signature_header": "Spark-Signature",
        "signature_format": "t=<unix seconds>,v1=<hex hmac sha256 of '<t>.<body>'>",
    }


def list_endpoints() -> dict:
    """
    Always refuses, because there is nothing to list.

    Returning an empty array with 200 would read as "you have no endpoints
    configured", which is a different and misleading statement.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"message": UPCOMING_NOTE, "reason": "upcoming"},
    )


def create_endpoint(
    payload: WebhookEndpointCreate,
    user: User = Depends(current_user),
) -> dict:
    """Refuses. Registering an endpoint that will never fire is worse than no
    endpoint at all, because it looks configured."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"message": UPCOMING_NOTE, "reason": "upcoming"},
    )

"""
Organizations and their API keys.

An organization is the ownership boundary. Datasets, models, jobs, keys and
usage all belong to one, and every route here checks membership on the server
before returning anything.
"""

from __future__ import annotations

import re
from typing import List, Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from api.database import get_db
from api.dependencies import current_user, membership_or_403, org_or_404
from api.lib import api_keys
from api.models import ApiKey, Membership, Organization, UsageEvent, User
from api.utils.ids import new_id, utcnow
from api.validators import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    OrganizationCreate,
    OrganizationOut,
)


#: Onboarding steps, in order. An organization only advances when the work for
#: a step actually completed.
ONBOARDING_STAGES = [
    "created",
    "data_connected",
    "data_validated",
    "model_trained",
    "model_evaluated",
    "model_approved",
    "key_issued",
    "live",
]


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (slug or "org")[:60]


def _org_out(org: Organization, role: str) -> OrganizationOut:
    return OrganizationOut(
        id=org.id,
        name=org.name,
        slug=org.slug,
        role=role,
        onboarding_stage=org.onboarding_stage,
        production_model_id=org.production_model_id,
        created_at=org.created_at.isoformat(),
    )


def _key_out(k: ApiKey) -> ApiKeyOut:
    return ApiKeyOut(
        id=k.id,
        name=k.name,
        mode=k.mode,
        masked=k.masked,
        active=k.active,
        created_at=k.created_at.isoformat(),
        last_used_at=k.last_used_at.isoformat() if k.last_used_at else None,
        revoked_at=k.revoked_at.isoformat() if k.revoked_at else None,
    )


def list_organizations(
    db: DbSession = Depends(get_db), user: User = Depends(current_user)
) -> List[OrganizationOut]:
    """Organizations the caller belongs to. Never anyone else's."""
    rows = db.execute(
        select(Membership, Organization)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(Membership.user_id == user.id)
        .order_by(Organization.created_at.asc())
    ).all()
    return [_org_out(org, m.role) for m, org in rows]


def create_organization(
    payload: OrganizationCreate,
    db: DbSession = Depends(get_db),
    user: User = Depends(current_user),
) -> OrganizationOut:
    """Create a workspace. The caller becomes its owner."""
    base = _slugify(payload.name)
    slug = base
    n = 1
    while db.execute(
        select(Organization).where(Organization.slug == slug)
    ).scalar_one_or_none():
        n += 1
        slug = f"{base}-{n}"

    org = Organization(
        id=new_id("org"), name=payload.name.strip(), slug=slug, created_by=user.id
    )
    db.add(org)
    # Same ordering rule as the session insert in auth.py: the parent row has
    # to exist before a child references it.
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
    return _org_out(org, "owner")


def get_organization(
    organization_id: str,
    db: DbSession = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """One organization, with where it has reached in onboarding."""
    m = membership_or_403(db, organization_id, user)
    org = org_or_404(db, organization_id, user)
    members = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == organization_id)
    ).all()
    return {
        **_org_out(org, m.role).model_dump(),
        "members": [
            {
                "user_id": u.id,
                "email": u.email,
                "display_name": u.display_name,
                "avatar_url": u.avatar_url,
                "role": mm.role,
            }
            for mm, u in members
        ],
        "onboarding": {
            "stages": ONBOARDING_STAGES,
            "current": org.onboarding_stage,
            "current_index": ONBOARDING_STAGES.index(org.onboarding_stage)
            if org.onboarding_stage in ONBOARDING_STAGES
            else 0,
        },
    }


# API keys


def list_api_keys(
    organization_id: str,
    db: DbSession = Depends(get_db),
    user: User = Depends(current_user),
) -> List[ApiKeyOut]:
    """Keys for this organization, always masked. The secret is never re-sent."""
    membership_or_403(db, organization_id, user)
    rows = db.execute(
        select(ApiKey)
        .where(ApiKey.organization_id == organization_id)
        .order_by(ApiKey.created_at.desc())
    ).scalars().all()
    return [_key_out(k) for k in rows]


def create_api_key(
    organization_id: str,
    payload: ApiKeyCreate,
    db: DbSession = Depends(get_db),
    user: User = Depends(current_user),
) -> ApiKeyCreated:
    """
    Issue a new key.

    The secret is generated, hashed, and the hash is stored. This response is
    the only time the full key exists outside the caller's hands.
    """
    membership_or_403(db, organization_id, user, roles={"owner", "admin"})
    org = db.get(Organization, organization_id)

    if payload.mode == "live" and not org.production_model_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "A production key needs an approved production "
                           "model. Train one, review its held-out results, and "
                           "approve it first.",
                "reason": "no_production_model",
            },
        )

    secret, prefix, last4, key_hash = api_keys.generate_api_key(payload.mode)
    key = ApiKey(
        id=new_id("key"),
        organization_id=organization_id,
        name=payload.name.strip(),
        mode=payload.mode,
        prefix=prefix,
        last4=last4,
        key_hash=key_hash,
        created_by=user.id,
    )
    db.add(key)
    if org.onboarding_stage in ("model_approved",):
        org.onboarding_stage = "key_issued"
    db.commit()

    return ApiKeyCreated(**_key_out(key).model_dump(), secret=secret)


def rotate_api_key(
    key_id: str,
    db: DbSession = Depends(get_db),
    user: User = Depends(current_user),
) -> ApiKeyCreated:
    """Replace a key with a new secret. The old one stops working immediately."""
    old = db.get(ApiKey, key_id)
    if old is None:
        raise HTTPException(
            status_code=404,
            detail={"message": "That key was not found.", "reason": "not_found"},
        )
    membership_or_403(db, old.organization_id, user, roles={"owner", "admin"})

    secret, prefix, last4, key_hash = api_keys.generate_api_key(old.mode)
    new_key = ApiKey(
        id=new_id("key"),
        organization_id=old.organization_id,
        name=old.name,
        mode=old.mode,
        prefix=prefix,
        last4=last4,
        key_hash=key_hash,
        created_by=user.id,
        rotated_from=old.id,
    )
    old.revoked_at = utcnow()
    db.add(new_key)
    db.commit()
    return ApiKeyCreated(**_key_out(new_key).model_dump(), secret=secret)


def revoke_api_key(
    key_id: str,
    db: DbSession = Depends(get_db),
    user: User = Depends(current_user),
) -> ApiKeyOut:
    """Turn a key off. This cannot be undone."""
    key = db.get(ApiKey, key_id)
    if key is None:
        raise HTTPException(
            status_code=404,
            detail={"message": "That key was not found.", "reason": "not_found"},
        )
    membership_or_403(db, key.organization_id, user, roles={"owner", "admin"})
    if key.revoked_at is None:
        key.revoked_at = utcnow()
        db.commit()
    return _key_out(key)


# usage


def usage(
    organization_id: str,
    mode: Optional[str] = None,
    model_id: Optional[str] = None,
    db: DbSession = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """
    Real API usage for this organization.

    Counts come from recorded requests. An organization that has sent nothing
    sees zeros and a prompt, not an invented demo number.

    Passing ``model_id`` narrows this to the requests that model actually
    scored, so a page showing one model does not report another model's
    traffic beside its results. Requests recorded before the model was tracked
    match no model and are reported separately as unattributed.
    """
    membership_or_403(db, organization_id, user)

    stmt = select(UsageEvent).where(UsageEvent.organization_id == organization_id)
    if mode:
        stmt = stmt.where(UsageEvent.mode == mode)
    if model_id:
        stmt = stmt.where(UsageEvent.model_id == model_id)
    events = db.execute(stmt.order_by(UsageEvent.created_at.desc()).limit(500)).scalars().all()

    counts = {"APPROVE": 0, "REVIEW": 0, "BLOCK": 0}
    prevented = 0.0
    for e in events:
        if e.decision in counts:
            counts[e.decision] += 1
        # Only blocked transactions can be said to have prevented anything, and
        # only their own amount. Review is not counted: it is a human decision
        # that has not happened yet.
        if e.decision == "BLOCK" and e.amount:
            prevented += float(e.amount)

    total_stmt = select(func.count()).select_from(UsageEvent).where(
        UsageEvent.organization_id == organization_id
    )
    if model_id:
        total_stmt = total_stmt.where(UsageEvent.model_id == model_id)
    total = db.execute(total_stmt).scalar_one()

    # Requests from before the model was recorded. Reported so the page can say
    # why a total it shows elsewhere is larger than the one shown here.
    unattributed = db.execute(
        select(func.count()).select_from(UsageEvent)
        .where(UsageEvent.organization_id == organization_id)
        .where(UsageEvent.model_id.is_(None))
    ).scalar_one()

    return {
        "total_requests": int(total),
        "unattributed_requests": int(unattributed),
        "model_id": model_id,
        "window_requests": len(events),
        "decisions": counts,
        "high_risk": counts["BLOCK"] + counts["REVIEW"],
        "blocked_amount": round(prevented, 2),
        "blocked_amount_note": (
            "The total value of transactions Spark blocked. It is what those "
            "transactions were worth, not a measured saving: whether each one "
            "was really fraud is only known once the outcome comes back."
        ),
        "recent": [
            {
                "id": e.id,
                "endpoint": e.endpoint,
                "mode": e.mode,
                "decision": e.decision,
                "risk_score": e.risk_score,
                "amount": e.amount,
                "latency_ms": e.latency_ms,
                "status_code": e.status_code,
                "created_at": e.created_at.isoformat(),
            }
            for e in events[:50]
        ],
    }

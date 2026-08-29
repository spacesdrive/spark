"""
Fetching something by an id the caller supplied.

The rule this module exists to enforce: an id in a URL proves nothing. Every
lookup of a private resource checks that the caller belongs to the organization
owning it. The frontend hiding a button is a convenience, never a control.

A missing resource and a forbidden one both answer 404, so these cannot be used
to discover which ids exist.
"""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from api.models import (
    DatasetRecord,
    Job,
    Membership,
    ModelRecord,
    Organization,
    User,
)


def membership_or_403(
    db: DbSession, organization_id: str, user: User, roles: Optional[set] = None
) -> Membership:
    """
    The caller's membership of an organization, or a refusal.

    A missing membership and a missing organization both return 404, so this
    cannot be used to discover which organization ids exist.
    """
    m = db.execute(
        select(Membership)
        .where(Membership.organization_id == organization_id)
        .where(Membership.user_id == user.id)
    ).scalar_one_or_none()
    if m is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "That organization was not found.",
                    "reason": "not_found"},
        )
    if roles and m.role not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "You do not have permission to do that in this "
                           "organization.",
                "reason": "forbidden",
            },
        )
    return m


def org_or_404(db: DbSession, organization_id: str, user: User) -> Organization:
    membership_or_403(db, organization_id, user)
    org = db.get(Organization, organization_id)
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "That organization was not found.",
                    "reason": "not_found"},
        )
    return org


def dataset_or_404(db: DbSession, dataset_id: str, user: Optional[User],
                   anon_ok: bool = True) -> DatasetRecord:
    """
    Fetch a dataset the caller is allowed to see.

    A dataset with no organization was uploaded by a guest. It is reachable
    only by its own unguessable id, and it is deleted on the retention
    schedule.
    """
    ds = db.get(DatasetRecord, dataset_id)
    if ds is None or ds.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "That dataset was not found. It may have expired.",
                    "reason": "not_found"},
        )
    if ds.organization_id is None:
        if anon_ok:
            return ds
        raise HTTPException(status_code=404, detail={"message": "Not found."})
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Sign in to use this dataset.",
                    "reason": "authentication_required"},
        )
    membership_or_403(db, ds.organization_id, user)
    return ds


def job_or_404(db: DbSession, job_id: str, user: Optional[User]) -> Job:
    """Fetch a job the caller owns."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "That job was not found.", "reason": "not_found"},
        )
    if job.organization_id is None:
        return job
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Sign in to see this job.",
                    "reason": "authentication_required"},
        )
    membership_or_403(db, job.organization_id, user)
    return job


def model_or_404(db: DbSession, model_id: str, user: Optional[User]) -> ModelRecord:
    """Fetch a model the caller is allowed to see."""
    m = db.get(ModelRecord, model_id)
    if m is None or m.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "That model was not found.", "reason": "not_found"},
        )
    if m.organization_id is None:
        return m
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "That model was not found.", "reason": "not_found"},
        )
    membership_or_403(db, m.organization_id, user)
    return m

"""Workspaces and their API keys."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class OrganizationCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)


class OrganizationOut(BaseModel):
    id: str
    name: str
    slug: str
    role: str
    onboarding_stage: str
    production_model_id: Optional[str] = None
    created_at: str


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    mode: str = Field(default="test", pattern="^(test|live)$")


class ApiKeyOut(BaseModel):
    id: str
    name: str
    mode: str
    masked: str
    active: bool
    created_at: str
    last_used_at: Optional[str] = None
    revoked_at: Optional[str] = None


class ApiKeyCreated(ApiKeyOut):
    """Returned once, at creation. The secret is not stored and never reappears."""

    secret: str
    warning: str = (
        "Copy this key now. It is stored only as a hash, so it cannot be shown "
        "again."
    )

"""Signing in, and reporting who is signed in."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from api.validators.organization import OrganizationOut


class SessionRequest(BaseModel):
    """Exchange a Supabase access token for a server session cookie."""

    access_token: str = Field(..., min_length=10)


class MeResponse(BaseModel):
    authenticated: bool
    user: Optional[Dict[str, Any]] = None
    organizations: List[OrganizationOut] = []
    csrf_token: Optional[str] = None

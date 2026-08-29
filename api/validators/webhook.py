"""Registering a webhook endpoint."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WebhookEndpointCreate(BaseModel):
    organization_id: str
    url: str = Field(..., max_length=500)
    events: list[str] = Field(default_factory=list)

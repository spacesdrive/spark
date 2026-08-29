"""Starting a training run."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TrainingRequest(BaseModel):
    organization_id: str
    dataset_id: str
    name: str = Field(..., min_length=1, max_length=120)
    base_model: str = Field(default="hybrid-v1")

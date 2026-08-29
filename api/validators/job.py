"""Background job status."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class JobOut(BaseModel):
    id: str
    kind: str
    status: str
    stage: str
    progress: float
    dataset_id: Optional[str] = None
    model_id: Optional[str] = None
    error: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    elapsed_seconds: Optional[float] = None
    has_result: bool = False

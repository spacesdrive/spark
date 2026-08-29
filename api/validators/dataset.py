"""Uploaded CSVs and the request to score one."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ColumnMapping(BaseModel):
    mapping: Dict[str, str] = Field(default_factory=dict)


class DatasetOut(BaseModel):
    id: str
    original_name: str
    kind: str
    size_bytes: int
    n_rows: int
    columns: List[str]
    has_labels: bool
    status: str
    created_at: str
    expires_at: Optional[str] = None
    validation: Dict[str, Any] = {}


class ScoreDatasetRequest(BaseModel):
    dataset_id: str
    mode: str = "balanced"
    model_id: str = "hybrid-v1"
    mapping: Optional[Dict[str, str]] = None

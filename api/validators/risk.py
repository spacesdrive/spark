"""Scoring one transaction: what goes in and what comes back."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from api.validators.common import MAX_ID_LEN


class TransactionRequest(BaseModel):
    """One transaction to score."""

    transaction_id: Optional[str] = Field(
        default=None, max_length=MAX_ID_LEN,
        description="Your reference for this transaction. Generated if omitted.",
    )
    amount: float = Field(..., ge=0, le=1e12, description="Transaction amount.")
    customer_id: str = Field(
        ..., min_length=1, max_length=MAX_ID_LEN,
        description="Who paid. Used for history and velocity.",
    )
    merchant_id: str = Field(
        ..., min_length=1, max_length=MAX_ID_LEN,
        description="Who was paid. Used for fan-in and ring signals.",
    )
    location: Optional[str] = Field(
        default=None, max_length=MAX_ID_LEN,
        description="Where it happened. One of the four graph links.",
    )
    payment_type: Optional[str] = Field(
        default=None, max_length=MAX_ID_LEN,
        description="Payment channel or instrument class.",
    )
    mode: str = Field(
        default="balanced",
        description="Which threshold setting to apply: balanced, "
                    "high_precision or high_recall.",
    )
    explain: bool = Field(default=True, description="Include the explanation.")

    @field_validator("customer_id", "merchant_id", "location", "payment_type",
                     "transaction_id")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v


class Reason(BaseModel):
    text: str
    direction: str
    contribution: float
    feature: str


class GraphLink(BaseModel):
    transaction_id: str
    time: int
    amount: float
    source: str
    target: str
    relation: str
    outcome: Optional[str] = None


class ProcessingStage(BaseModel):
    name: str
    ms: float


class ScoreResponse(BaseModel):
    transaction_id: str
    amount: float
    customer_id: str
    merchant_id: str
    location: str
    payment_type: str

    risk_score: float
    risk_band: str
    decision: str
    mode: str
    model_id: str
    model_version: str
    path: str

    review_threshold: float
    block_threshold: float

    channel_scores: Dict[str, float]
    channel_attribution: Dict[str, float]
    reasons: List[Reason]
    entity_risk: Dict[str, float]
    entity_history: Dict[str, Dict[str, Any]]
    graph_evidence: Dict[str, List[GraphLink]]
    related_ring: Optional[Dict[str, Any]] = None
    stages: List[ProcessingStage]
    latency_ms: float
    notes: List[str] = []

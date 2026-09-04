"""
Typed views over the API's JSON.

Every field here exists in ``api/validators``. Unknown keys are kept in
``raw`` rather than dropped, so a newer server does not silently lose data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class Reason:
    """One human readable driver of the score."""

    text: str
    direction: str          # "increases" or "decreases"
    contribution: float
    feature: str

    @classmethod
    def from_json(cls, d: Dict[str, Any]) -> "Reason":
        return cls(
            text=d.get("text", ""),
            direction=d.get("direction", ""),
            contribution=float(d.get("contribution", 0.0)),
            feature=d.get("feature", ""),
        )


@dataclass(frozen=True)
class ScoreResult:
    """
    The outcome of scoring one transaction.

    ``risk_score`` is a calibrated score in the range 0 to 1, but it is not a
    probability of fraud for your traffic unless your data resembles the data
    the model was fitted on. Compare it against ``review_threshold`` and
    ``block_threshold`` rather than reading it as a percentage.
    """

    transaction_id: str
    amount: float
    customer_id: str
    merchant_id: str
    risk_score: float
    risk_band: str          # LOW | MEDIUM | HIGH
    decision: str           # APPROVE | REVIEW | BLOCK
    mode: str
    model_id: str
    model_version: str
    path: str               # MODEL | COLD_START
    review_threshold: float
    block_threshold: float
    latency_ms: float
    reasons: List[Reason] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def is_blocked(self) -> bool:
        return self.decision == "BLOCK"

    @property
    def needs_review(self) -> bool:
        return self.decision == "REVIEW"

    @property
    def scored_without_history(self) -> bool:
        """True when nothing was known about any party to the transaction.

        Spark raises these to a floor score, so a BLOCK here means unknown,
        not necessarily risky.
        """
        return self.path == "COLD_START"

    @classmethod
    def from_json(cls, d: Dict[str, Any]) -> "ScoreResult":
        return cls(
            transaction_id=d.get("transaction_id", ""),
            amount=float(d.get("amount", 0.0)),
            customer_id=d.get("customer_id", ""),
            merchant_id=d.get("merchant_id", ""),
            risk_score=float(d.get("risk_score", 0.0)),
            risk_band=d.get("risk_band", ""),
            decision=d.get("decision", ""),
            mode=d.get("mode", ""),
            model_id=d.get("model_id", ""),
            model_version=d.get("model_version", ""),
            path=d.get("path", ""),
            review_threshold=float(d.get("review_threshold", 0.0)),
            block_threshold=float(d.get("block_threshold", 0.0)),
            latency_ms=float(d.get("latency_ms", 0.0)),
            reasons=[Reason.from_json(r) for r in d.get("reasons", [])],
            notes=list(d.get("notes", [])),
            raw=d,
        )

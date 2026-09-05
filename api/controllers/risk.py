"""
Scoring one transaction.

Two doors into the same engine:

``POST /api/risk/score``
    The dashboard. Open to guests, rate limited, uses the built-in model.

``POST /api/v1/risk/score``
    Servers, authenticated with an API key. Records usage against the
    organization and resolves the model the organization has approved.

Both call the same scorer, so what a developer sees in the sandbox is what
their server gets.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DbSession

from api.database import get_db
from api.dependencies import require_api_key
from api.models import ModelRecord, UsageEvent
from api.services import engine as engine_state
from api.types.auth import ApiCaller
from api.utils.ids import new_id
from api.validators import ScoreResponse, TransactionRequest
from ml.serving.online import TransactionInput


#: Stated on every response so nobody has to guess what a missing field did.
FIELD_NOTES = {
    "location": "No location was given, so it was recorded as 'unknown'. The "
                "location link in the graph carries nothing for this "
                "transaction.",
    "payment_type": "No payment channel was given, so it was recorded as "
                    "'unknown'. The channel link in the graph carries nothing "
                    "for this transaction.",
}


def _require_engine():
    scorer = engine_state.get_scorer()
    if scorer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": "No model is loaded, so nothing can be scored yet.",
                "reason": "model_unavailable",
                "detail": engine_state.status().get("error"),
            },
        )
    return scorer


def _resolve_scorer(artifact_path: Optional[str]):
    """
    The scorer for the model the caller actually asked for.

    Without this, ``model_id`` would be nothing but a label on the response
    while every request was scored by the built-in model, and activating a
    custom model would appear to work while changing nothing. A model that
    cannot be loaded is an error, never a silent fallback to a different one.
    """
    if not artifact_path:
        return _require_engine()

    entry = engine_state.load_custom(artifact_path)
    if entry.get("scorer") is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": "That model could not be loaded, so nothing was "
                           "scored with it.",
                "reason": "model_unavailable",
            },
        )
    return entry["scorer"]


def _score(
    payload: TransactionRequest,
    model_id: str = "hybrid-v1",
    artifact_path: Optional[str] = None,
) -> ScoreResponse:
    scorer = _resolve_scorer(artifact_path)
    engine = scorer.engine

    if payload.mode not in engine.metadata["thresholds"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": f"'{payload.mode}' is not a threshold setting.",
                "reason": "invalid_mode",
                "allowed": sorted(engine.metadata["thresholds"]),
            },
        )

    notes = [FIELD_NOTES[f] for f in ("location", "payment_type")
             if not getattr(payload, f)]

    txn = TransactionInput(
        transaction_id=payload.transaction_id or f"api_{new_id('t')[-12:]}",
        amount=float(payload.amount),
        source=payload.customer_id,
        target=payload.merchant_id,
        location=payload.location or "unknown",
        payment_type=payload.payment_type or "unknown",
    )
    result = scorer.score(txn, mode=payload.mode, explain=payload.explain)

    op = engine.metadata["thresholds"][payload.mode]
    return ScoreResponse(
        transaction_id=result.transaction_id,
        amount=result.amount,
        customer_id=result.source,
        merchant_id=result.target,
        location=result.location,
        payment_type=result.payment_type,
        risk_score=round(result.risk_score, 6),
        risk_band=result.risk_band,
        decision=result.decision,
        mode=result.mode,
        model_id=model_id,
        model_version=result.model_version,
        path=result.path,
        review_threshold=float(op["review_threshold"]),
        block_threshold=float(op["block_threshold"]),
        channel_scores={k: round(v, 6) for k, v in result.channel_scores.items()},
        channel_attribution={
            k: round(v, 6) for k, v in result.channel_attribution.items()
        },
        reasons=result.reasons,
        entity_risk=result.entity_risk,
        entity_history=result.entity_history,
        graph_evidence=result.graph_evidence,
        related_ring=result.related_ring,
        stages=result.stages,
        latency_ms=round(result.latency_ms, 2),
        notes=notes,
    )


def score_transaction(payload: TransactionRequest) -> ScoreResponse:
    """Score one transaction with the built-in model. No account needed."""
    return _score(payload)


def score_transaction_v1(
    payload: TransactionRequest,
    request: Request,
    caller: ApiCaller = Depends(require_api_key),
    db: DbSession = Depends(get_db),
) -> ScoreResponse:
    """
    Score one transaction using an API key.

    A test key never touches production state. A live key resolves to the
    model the organization approved for production; until one is approved,
    the built-in model is used and the response says so through
    ``model_id``.
    """
    org = caller.organization

    # A test key always resolves to the built-in model, so sandbox traffic can
    # never be scored by, or depend on, whatever is in production.
    model_id = "hybrid-v1"
    artifact_path = None
    if not caller.is_test and org.production_model_id:
        production = db.get(ModelRecord, org.production_model_id)
        if production is not None and production.artifact_path:
            model_id = production.id
            artifact_path = production.artifact_path

    result = _score(payload, model_id=model_id, artifact_path=artifact_path)

    db.add(
        UsageEvent(
            id=new_id("use"),
            organization_id=org.id,
            api_key_id=caller.key.id,
            mode=caller.mode,
            endpoint="/api/v1/risk/score",
            status_code=200,
            model_id=model_id,
            decision=result.decision,
            risk_score=result.risk_score,
            amount=result.amount,
            latency_ms=result.latency_ms,
        )
    )
    db.commit()
    return result


def thresholds() -> dict:
    """
    The three threshold settings, and whether each one still works on the
    held-out test window.

    ``high_precision`` is reported as not transferring here. Its threshold was
    chosen correctly on validation, but the score distribution moved between
    validation and test, so almost nothing in the later window reaches it. That
    is shown rather than hidden.
    """
    meta = engine_state.read_metadata()
    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"message": "No trained model is available.",
                    "reason": "model_unavailable"},
        )
    evaluation = engine_state.read_evaluation() or {}
    by_mode = {
        row["mode"]: row for row in evaluation.get("operating_points_test", [])
    }
    out = []
    for name, op in meta.get("thresholds", {}).items():
        measured = by_mode.get(name, {})
        out.append(
            {
                "mode": name,
                "review_threshold": op["review_threshold"],
                "block_threshold": op["block_threshold"],
                "selected_on": op["selected_on"],
                "rationale": op["rationale"],
                "test_precision": measured.get("precision"),
                "test_recall": measured.get("recall"),
                "test_f1": measured.get("f1"),
                "test_alerts": measured.get("n_predicted_positive"),
                "transfers_to_test": measured.get("transfers"),
            }
        )
    return {"thresholds": out}

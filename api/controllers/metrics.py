"""
The numbers the dashboard shows.

Every value here is read from the evaluation report the pipeline wrote. Nothing
is computed on the fly and nothing has a fallback value, because a fallback
would be a made-up metric wearing a real label. When the evaluation has not
been run, these endpoints say so.

Each block carries the split it came from, so a reader always knows whether a
number describes validation data or the held-out test.
"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session as DbSession

from api.database import get_db
from api.dependencies import current_user_optional, model_or_404
from api.models import User
from api.services import engine as engine_state
from api.services.training import model_dir


#: Plain-language definitions, sent with the numbers so the dashboard never
#: shows a term it has not explained.
GLOSSARY = {
    "precision": "Of the transactions Spark flagged, how many were really "
                 "fraud. Higher means fewer annoyed real customers.",
    "recall": "Of all the fraud, how much Spark caught. Higher means less "
              "money lost.",
    "f1": "One number balancing precision and recall.",
    "pr_auc": "How well the model sorts fraud above normal traffic when fraud "
              "is rare. Higher is better.",
    "roc_auc": "How well the model separates fraud from normal overall. "
               "Easier to score well on than PR-AUC.",
    "brier": "How close the predicted probabilities are to what actually "
             "happened. Lower is better.",
    "fpr": "How often a normal transaction was wrongly flagged.",
    "fnr": "How often real fraud was missed.",
    "psi": "How much the score distribution moved between two periods. Below "
           "0.10 is stable, above 0.25 means it really moved.",
    "expected_cost": "What the mistakes would cost in money, using the "
                     "configured cost model.",
    "lift": "How much better than picking at random.",
}


def _is_builtin(model_id: str) -> bool:
    return any(m["id"] == model_id for m in engine_state.builtin_models())


def _custom_evaluation(model_id: str, db: DbSession, user: Optional[User]) -> Optional[dict]:
    """
    The evaluation a custom model wrote when it was trained.

    Returns None when the id is not a custom model this caller owns, so the
    caller falls back to the built-in report. Ownership is checked here rather
    than by the route, because these endpoints are open to guests and only the
    custom branch needs an account.
    """
    record = model_or_404(db, model_id, user)
    if record.kind != "custom":
        return None
    path = model_dir(record.id) / "reports" / "evaluation.json"
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": f"{record.name} has no stored evaluation, so there "
                           "are no measured results to show for it.",
                "reason": "evaluation_missing",
            },
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _evaluation_or_503(
    model_id: Optional[str] = None,
    db: Optional[DbSession] = None,
    user: Optional[User] = None,
) -> dict:
    """
    The evaluation report for the selected model.

    A built-in id, or no id at all, reads the pipeline's own report. A custom
    id reads the report that model wrote during its own held-out evaluation.
    """
    # A built-in model is not a database row, so it must not be looked up as
    # one. Doing that answered 404 for the model the dashboard selects by
    # default.
    if model_id and db is not None and not _is_builtin(model_id):
        custom = _custom_evaluation(model_id, db, user)
        if custom is not None:
            return custom

    report = engine_state.read_evaluation()
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": "The held-out evaluation has not been run yet, so "
                           "there are no measured results to show.",
                "reason": "evaluation_missing",
                "fix": "Run: python -m spark.models.evaluate",
            },
        )
    return report


def overview(
    model_id: Optional[str] = Query(default=None),
    db: DbSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
) -> dict:
    """Headline numbers for the overview page, each labelled with its split."""
    report = _evaluation_or_503(model_id, db, user)
    # Latency and the trained-at stamp are measured for the built-in model.
    # A custom model has no latency run of its own, so rather than quote the
    # built-in figures under its name, they are left out.
    builtin = not model_id or _is_builtin(model_id)
    latency = engine_state.read_latency() if builtin else None
    meta = (engine_state.read_metadata() or {}) if builtin else {}

    balanced = next(
        (r for r in report.get("operating_points_test", []) if r["mode"] == "balanced"),
        None,
    )
    by_split = {r["split"]: r for r in report.get("ranking_by_split", [])}
    test = by_split.get("test", {})
    rings = report.get("rings", {}).get("test", {})
    drift = report.get("score_drift", {})

    cards = []

    def card(key: str, label: str, value: Optional[float], source: str,
             fmt: str = "ratio", helptext: Optional[str] = None) -> None:
        if value is None:
            return
        cards.append(
            {
                "key": key,
                "label": label,
                "value": value,
                "format": fmt,
                "source": source,
                "help": helptext or GLOSSARY.get(key, ""),
            }
        )

    if balanced:
        card("precision", "Precision", balanced.get("precision"), "held-out test")
        card("recall", "Recall", balanced.get("recall"), "held-out test")
        card("f1", "F1", balanced.get("f1"), "held-out test")
        card("fpr", "False positive rate", balanced.get("fpr"), "held-out test")
        card("fnr", "False negative rate", balanced.get("fnr"), "held-out test")
    card("pr_auc", "PR-AUC", test.get("pr_auc"), "held-out test")
    card("roc_auc", "ROC-AUC", test.get("roc_auc"), "held-out test")
    card("test_transactions", "Test transactions", test.get("n"),
         "held-out test", "count",
         "Labelled transactions in the held-out window the numbers are "
         "measured on.")
    card("ring_precision", "Abuse-ring precision", rings.get("precision"),
         "held-out test", "ratio",
         "Of the transactions inside alerted rings, how many were really "
         "fraud. Ring detection reads no labels.")
    card("ring_recall", "Abuse-ring recall", rings.get("recall_of_test_fraud"),
         "held-out test", "ratio",
         "Of all the fraud in the test window, how much sat inside an alerted "
         "ring.")
    if latency:
        card("p50_latency", "p50 latency",
             latency.get("per_transaction", {}).get("p50_ms"),
             "measured on one CPU", "ms",
             "Half of scoring calls finish faster than this.")
        card("p95_latency", "p95 latency",
             latency.get("per_transaction", {}).get("p95_ms"),
             "measured on one CPU", "ms",
             "19 out of 20 scoring calls finish faster than this.")

    return {
        "model_version": report.get("model_version", meta.get("model_version")),
        "cards": cards,
        "splits": report.get("ranking_by_split", []),
        "channels": report.get("ranking_by_channel", []),
        "operating_points": report.get("operating_points_test", []),
        "drift": drift,
        "cost": {
            "expected_cost": (balanced or {}).get("expected_cost"),
            "prevented_loss": (balanced or {}).get("prevented_loss"),
            "residual_loss": (balanced or {}).get("residual_loss"),
            "baseline_loss_no_system": (balanced or {}).get("baseline_loss_no_system"),
            "net_benefit": (balanced or {}).get("net_benefit"),
            "cost_per_1k": (balanced or {}).get("cost_per_1k"),
        },
        "glossary": GLOSSARY,
        "measured_on": "The held-out test split. It is read once, after every "
                       "weight and threshold is frozen on validation data.",
    }


def charts(
    model_id: Optional[str] = Query(default=None),
    db: DbSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
) -> dict:
    """
    Chart-shaped views of the same measured numbers.

    The radar chart is built only from things that were actually measured. It
    has no axis for anything the project has not put a number on.
    """
    report = _evaluation_or_503(model_id, db, user)
    latency = engine_state.read_latency() if (not model_id or _is_builtin(model_id)) else None

    balanced = next(
        (r for r in report.get("operating_points_test", []) if r["mode"] == "balanced"),
        {},
    )
    test = next(
        (r for r in report.get("ranking_by_split", []) if r["split"] == "test"), {}
    )
    rings = report.get("rings", {}).get("test", {})

    decisions = [
        {"decision": "APPROVE", "count": balanced.get("n_approve", 0)},
        {"decision": "REVIEW", "count": balanced.get("n_review", 0)},
        {"decision": "BLOCK", "count": balanced.get("n_block", 0)},
    ]

    performance = [
        {"metric": "Precision", "value": balanced.get("precision")},
        {"metric": "Recall", "value": balanced.get("recall")},
        {"metric": "F1", "value": balanced.get("f1")},
        {"metric": "PR-AUC", "value": test.get("pr_auc")},
        {"metric": "ROC-AUC", "value": test.get("roc_auc")},
    ]

    radar = [
        {
            "axis": "Fraud detection",
            "value": test.get("pr_auc"),
            "measured": "Held-out test PR-AUC.",
        },
        {
            "axis": "Ring detection",
            "value": rings.get("precision"),
            "measured": "Precision of alerted rings on the held-out test.",
        },
        {
            "axis": "Recall",
            "value": balanced.get("recall"),
            "measured": "Recall at the balanced threshold.",
        },
        {
            "axis": "Precision",
            "value": balanced.get("precision"),
            "measured": "Precision at the balanced threshold.",
        },
    ]
    radar = [r for r in radar if r["value"] is not None]

    channel_rows = report.get("ranking_by_channel", [])
    return {
        "decision_distribution": decisions,
        "model_performance": [p for p in performance if p["value"] is not None],
        "channel_performance": channel_rows,
        "calibration": report.get("calibration_test", []),
        "cost_sweep": report.get("cost_sweep_test", []),
        "stress_slices": report.get("stress_slices_test", []),
        "radar": radar,
        "radar_note": (
            "Only axes with a measured number are shown. Explainability and "
            "speed have no comparable 0 to 1 score, so they are reported as "
            "their own numbers instead of invented ones."
        ),
        "latency": latency,
    }


def limitations(
    model_id: Optional[str] = Query(default=None),
    db: DbSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
) -> dict:
    """
    What the measured numbers do not cover.

    These are load-bearing caveats, not disclaimers. They come from the
    evaluation report, so they cannot drift away from the results.
    """
    report = _evaluation_or_503(model_id, db, user)
    drift = report.get("score_drift", {})
    slices = {s["slice"]: s for s in report.get("stress_slices_test", [])}
    hp = next(
        (r for r in report.get("operating_points_test", [])
         if r["mode"] == "high_precision"),
        {},
    )
    cold = slices.get("cold_entities", {})
    warm = slices.get("warm_entities", {})

    def r(value, digits: int = 4) -> str:
        """Round for display. A raw float in a sentence reads like a bug."""
        return "not measured" if value is None else f"{float(value):.{digits}f}"

    items = [
        {
            "title": "The dataset is simulated",
            "detail": "Results describe the file the models were trained on, "
                      "not real payment traffic. The method and the way it is "
                      "tested are what carry over.",
        },
        {
            "title": "The score distribution shifted",
            "detail": f"PSI between validation and the held-out test is "
                      f"{r(drift.get('psi'), 3)}, which counts as a real shift. "
                      f"In live use the calibration would need refreshing.",
            "value": drift.get("psi"),
        },
        {
            "title": "The high precision setting does not carry over",
            "detail": "Its threshold was chosen correctly on validation, but "
                      f"almost nothing in the test window reaches it: it fires "
                      f"on {hp.get('n_predicted_positive', 0):,} of "
                      f"{hp.get('tp', 0) + hp.get('fp', 0) + hp.get('tn', 0) + hp.get('fn', 0):,} "
                      f"transactions. The evaluation reports this as a failure "
                      f"rather than quoting precision on an almost empty set.",
        },
        {
            "title": "New merchants are harder",
            "detail": f"PR-AUC drops to {r(cold.get('pr_auc'))} on entities the "
                      f"system had barely seen, against {r(warm.get('pr_auc'))} "
                      f"on familiar ones. History features cannot help where "
                      f"there is no history.",
        },
        {
            "title": "No device or IP data",
            "detail": "The source dataset has no device fingerprint and no IP "
                      "address, so two of the strongest real ring signals are "
                      "missing. Spark does not invent them.",
        },
        {
            "title": "Graph results move slightly between retrains",
            "detail": "The graph model uses CPU floating point maths that is "
                      "not perfectly repeatable, so retraining moves the "
                      "numbers by about 0.001.",
        },
        {
            "title": "Time is a position, not a clock",
            "detail": "In the training data, time is a position in a sequence. "
                      "Velocity therefore means transactions elapsed, not "
                      "seconds elapsed. Uploaded timestamps are converted the "
                      "same way.",
        },
    ]
    return {"limitations": items}


def rings(
    model_id: Optional[str] = Query(default=None),
    db: DbSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
) -> dict:
    """Detected abuse rings and how well they scored on the held-out test."""
    report = _evaluation_or_503(model_id, db, user)
    ring_block = report.get("rings", {})
    return {
        "n_candidate_rings": ring_block.get("n_candidate_rings"),
        "threshold_selected_on_validation": ring_block.get(
            "threshold_selected_on_validation"
        ),
        "validation_sweep": ring_block.get("validation_sweep", []),
        "test": ring_block.get("test", {}),
        "top_rings": ring_block.get("top_rings", []),
        "how_it_works": (
            "Ring detection reads no fraud labels. It groups transactions that "
            "share a merchant, a payment channel and a location inside a time "
            "window, then scores each group on how many separate accounts it "
            "uses, how tightly packed it is in time, and how similar the "
            "amounts are. Precision is only checked against the real labels "
            "afterwards."
        ),
    }

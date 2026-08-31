"""
Score a whole uploaded dataset with the trained models.

The pipeline is the same one training used: causal features, then the
backward-in-time graph, then the four channels, then the fusion weights and
the calibrator. Nothing is refitted. The models, weights, calibrator and
thresholds all come from the artifacts on disk.

One property worth being explicit about, because it changes how the numbers
should be read: an uploaded file is scored using only its own history. The
customers and merchants in it are not the ones the model was trained on, so
every entity starts with no past. Early rows in a small file are therefore
scored much like a first-time customer would be.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from ml.calibration.fuse import CHANNELS
from ml.config import CONFIG
from ml.evaluation.metrics import (
    binary_metrics,
    decide,
    expected_cost,
    ranking_metrics,
)
from ml.evaluation.drift import classify, population_stability_index
from ml.features.causal import build_causal_features
from ml.graph.build import build_relation_graph, neighbour_risk_features
from ml.serving.online import risk_band

ProgressFn = Callable[[str, float], None]


def _noop(stage: str, progress: float) -> None:
    return None


def score_dataframe(
    engine,
    df: pd.DataFrame,
    mode: str = "balanced",
    progress: Optional[ProgressFn] = None,
) -> Dict[str, object]:
    """
    Score a prepared frame and return per-row results plus summaries.

    ``df`` must already carry the pipeline's column names, which is what
    ``api.datasets.to_spark_frame`` produces.
    """
    report = progress or _noop
    cfg = CONFIG

    op = engine.metadata["thresholds"].get(mode)
    if op is None:
        raise ValueError(f"unknown mode {mode!r}")
    review_t = float(op["review_threshold"])
    block_t = float(op["block_threshold"])

    work = df.reset_index(drop=True)

    report("Building features", 0.10)
    bundle = build_causal_features(work, cfg=cfg, train_mask=None, verbose=False)

    report("Linking related transactions", 0.35)
    graph = build_relation_graph(work, cfg=cfg, verbose=False)
    y = np.where(work["Labels"].to_numpy() == 1, 1, 0).astype(int)
    labeled = work["Labels"].to_numpy() != 2
    gfeat = neighbour_risk_features(
        graph, y, labeled, lag=cfg.features.label_lag_steps, verbose=False
    )

    report("Running the tabular model", 0.50)
    p_tab = engine.tabular.predict_proba(bundle.base)

    report("Running the graph model", 0.62)
    x_graph = pd.concat(
        [
            bundle.base.reset_index(drop=True),
            bundle.risk.reset_index(drop=True),
            gfeat.reset_index(drop=True),
        ],
        axis=1,
    )
    p_graph = engine.graph_model.predict_proba(x_graph, graph.normalised())

    report("Scoring behaviour and velocity", 0.74)
    unsup = engine.channels.score(bundle.base)

    report("Combining and calibrating", 0.82)
    channel_scores = {
        "tabular": p_tab,
        "graph": p_graph,
        "behavioral": unsup["behavioral"],
        "velocity": unsup["velocity"],
    }
    risk = engine.fusion.predict(channel_scores)

    cold = (
        (bundle.base["Source_txn_count"].to_numpy() < 3)
        & (bundle.base["Target_txn_count"].to_numpy() < 3)
        & (bundle.base["Type_txn_count"].to_numpy() < 3)
    )
    risk = np.where(cold, np.maximum(risk, engine.cold_floor), risk)
    decisions = decide(risk, review_t, block_t)

    report("Building results", 0.90)
    rows: List[dict] = []
    ids = work["transaction_id"].astype(str).to_numpy()
    amounts = work["Amount"].to_numpy(dtype=float)
    for i in range(len(work)):
        rows.append(
            {
                "transaction_id": ids[i],
                "amount": float(amounts[i]),
                "customer_id": str(work["Source"].iloc[i]),
                "merchant_id": str(work["Target"].iloc[i]),
                "risk_score": round(float(risk[i]), 6),
                "risk_band": risk_band(float(risk[i]), review_t, block_t),
                "decision": str(decisions[i]),
                "path": "COLD_START" if bool(cold[i]) else "MODEL",
                "model_version": engine.metadata["model_version"],
                **{
                    f"score_{c}": round(float(channel_scores[c][i]), 6)
                    for c in CHANNELS
                },
                "label": (
                    int(y[i]) if bool(labeled[i]) else None
                ),
            }
        )

    summary = _summarise(risk, decisions, review_t, block_t)
    fit = _data_fit(engine, risk, work, bundle.base, block_t)
    evaluation = None
    if labeled.any():
        evaluation = _evaluate(
            y[labeled], risk[labeled], amounts[labeled], review_t, block_t
        )

    report("Done", 1.0)
    return {
        "mode": mode,
        "review_threshold": review_t,
        "block_threshold": block_t,
        "model_version": engine.metadata["model_version"],
        "n_rows": len(work),
        "n_labeled": int(labeled.sum()),
        "rows": rows,
        "summary": summary,
        "evaluation": evaluation,
        "fit": fit,
        "graph": {
            "nodes": graph.n_nodes,
            "edges": graph.total_edges,
            "by_relation": graph.edge_counts,
        },
    }


def _data_fit(engine, risk: np.ndarray, work: pd.DataFrame,
              base: pd.DataFrame, block_threshold: float) -> dict:
    """
    How far this dataset sits from what the model was trained on.

    PSI compares the risk scores produced here with the scores the model
    produced on its own training window. A large value means the traffic looks
    different, so the calibration fitted back then will not be right for it.

    This is a warning about fit, not an accuracy estimate. PSI says nothing
    about whether the predictions are correct, and it is not converted into a
    confidence number anywhere.
    """
    reference_path = Path(engine.artifact_dir) / "fused_scores.npy"
    psi: Optional[float] = None
    status = "unknown"
    if reference_path.exists() and len(risk) >= 50:
        reference = np.load(reference_path)
        psi = float(population_stability_index(reference, risk))
        status = classify(psi)

    # A file too small for the graph to find anything is a real limitation and
    # is reported as one, rather than being scored silently.
    n = len(work)
    distinct_customers = int(work["Source"].nunique())
    distinct_merchants = int(work["Target"].nunique())
    cold_share = float(
        (
            (base["Source_txn_count"].to_numpy() < 3)
            & (base["Target_txn_count"].to_numpy() < 3)
        ).mean()
    )
    has_location = work["Location"].nunique() > 1
    has_channel = work["Type"].nunique() > 1

    limits = []
    if n < 500:
        limits.append(
            f"Only {n:,} rows. History and relationship features need more "
            f"traffic before they say much."
        )
    if cold_share > 0.5:
        limits.append(
            f"{cold_share:.0%} of rows involve a customer and merchant with "
            f"almost no history in this file, so those scores lean on the "
            f"conservative cold-start floor."
        )
    if not has_location:
        limits.append(
            "Every row has the same location, so the location link in the "
            "graph carries nothing."
        )
    if not has_channel:
        limits.append(
            "Every row has the same payment channel, so the channel link in "
            "the graph carries nothing."
        )

    # The cold-start floor is the fraud rate the model was trained on. When
    # that floor sits above the block threshold, a transaction with no history
    # is blocked purely for having no history. That is a deliberate choice, but
    # it changes how a result should be read, so it is said out loud.
    cold_floor = float(engine.cold_floor)
    if cold_share > 0 and cold_floor >= block_threshold:
        n_cold = int(
            (
                (base["Source_txn_count"].to_numpy() < 3)
                & (base["Target_txn_count"].to_numpy() < 3)
                & (base["Type_txn_count"].to_numpy() < 3)
            ).sum()
        )
        if n_cold:
            limits.append(
                f"{n_cold:,} rows had no history at all for the customer, the "
                f"merchant and the channel. Spark raises those to a minimum "
                f"score of {cold_floor:.4f}, which is above the block threshold "
                f"of {block_threshold:.4f}, so they were blocked for being "
                f"unknown rather than for looking risky."
            )

    if limits:
        verdict = "limited"
    elif status == "SHIFTED":
        verdict = "shifted"
    elif status in ("STABLE", "MONITOR"):
        verdict = "good"
    else:
        verdict = "unknown"

    explanations = {
        "good": "This data looks broadly like what the model was trained on.",
        "shifted": "This data looks substantially different from what the "
                   "model was trained on. Treat the scores as a rough ranking "
                   "rather than calibrated probabilities.",
        "limited": "There is not enough here for the relationship features to "
                   "do much. The scores are still real, but they are working "
                   "with less information than the model expects.",
        "unknown": "There is not enough data to compare distributions.",
    }
    return {
        "verdict": verdict,
        "explanation": explanations[verdict],
        "psi": None if psi is None else round(psi, 4),
        "psi_status": status,
        "psi_note": "PSI compares two score distributions. Below 0.10 is "
                    "stable, 0.10 to 0.25 is worth watching, above 0.25 means "
                    "it moved. It does not measure accuracy.",
        "rows": n,
        "distinct_customers": distinct_customers,
        "distinct_merchants": distinct_merchants,
        "cold_share": round(cold_share, 4),
        "limitations": limits,
    }


def _summarise(
    risk: np.ndarray, decisions: np.ndarray, review_t: float, block_t: float
) -> dict:
    """Distributions the dashboard charts, computed once on the server."""
    n = len(risk)
    bands = {
        "LOW": int((risk < review_t).sum()),
        "MEDIUM": int(((risk >= review_t) & (risk < block_t)).sum()),
        "HIGH": int((risk >= block_t).sum()),
    }
    counts = {d: int((decisions == d).sum()) for d in ("APPROVE", "REVIEW", "BLOCK")}
    # Twenty buckets is enough shape for a chart and small enough to send.
    hist, edges = np.histogram(risk, bins=20, range=(0.0, 1.0))
    return {
        "n": n,
        "risk_bands": bands,
        "decisions": counts,
        "mean_risk": float(risk.mean()) if n else 0.0,
        "median_risk": float(np.median(risk)) if n else 0.0,
        "histogram": [
            {
                "bucket": f"{edges[i]:.2f}",
                "from": float(edges[i]),
                "to": float(edges[i + 1]),
                "count": int(hist[i]),
            }
            for i in range(len(hist))
        ],
    }


def _evaluate(
    y: np.ndarray,
    risk: np.ndarray,
    amounts: np.ndarray,
    review_t: float,
    block_t: float,
) -> dict:
    """Real metrics, only ever called when real labels were supplied."""
    rank = ranking_metrics(y, risk)
    binary = binary_metrics(y, risk, block_t)
    cost = expected_cost(y, risk, amounts, review_t, block_t, CONFIG.cost)
    return {
        "n": int(len(y)),
        "n_fraud": int(y.sum()),
        "base_rate": float(y.mean()) if len(y) else 0.0,
        "pr_auc": _finite(rank.pr_auc),
        "roc_auc": _finite(rank.roc_auc),
        "brier": _finite(rank.brier),
        "precision": binary.precision,
        "recall": binary.recall,
        "f1": binary.f1,
        "fpr": binary.fpr,
        "fnr": binary.fnr,
        "confusion": {
            "tp": binary.tp,
            "fp": binary.fp,
            "tn": binary.tn,
            "fn": binary.fn,
        },
        "cost": {
            "expected_cost": cost.expected_cost,
            "cost_per_1k": cost.cost_per_1k,
            "prevented_loss": cost.prevented_loss,
            "residual_loss": cost.residual_loss,
            "baseline_loss_no_system": cost.baseline_loss_no_system,
            "net_benefit": cost.net_benefit,
        },
    }


def _finite(v: float) -> Optional[float]:
    """NaN means undefined, and the API should say so rather than send NaN."""
    return None if v is None or not np.isfinite(v) else float(v)


#: Columns in the downloadable results file, in order.
RESULT_COLUMNS = [
    "transaction_id",
    "amount",
    "customer_id",
    "merchant_id",
    "risk_score",
    "risk_band",
    "decision",
    "path",
    "model_version",
    "score_tabular",
    "score_graph",
    "score_behavioral",
    "score_velocity",
    "label",
]

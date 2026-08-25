"""
Metrics and the cost model.

Two different questions, kept separate on purpose:

- Ranking metrics ask how well the model sorts transactions.
- Expected cost asks what running it would actually cost in money.

A change can improve one and hurt the other. A fraud system is only useful if
the money number improves.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)

from ml.config import CONFIG, CostConfig

APPROVE, REVIEW, BLOCK = "APPROVE", "REVIEW", "BLOCK"


# Ranking metrics


@dataclass
class RankingMetrics:
    n: int
    n_positive: int
    base_rate: float
    pr_auc: float
    roc_auc: float
    brier: float

    def as_dict(self) -> dict:
        return asdict(self)


def ranking_metrics(y: np.ndarray, scores: np.ndarray) -> RankingMetrics:
    """Threshold-free quality of the score ordering."""
    y = np.asarray(y).astype(int)
    scores = np.asarray(scores, dtype=float)
    n_pos = int(y.sum())
    if n_pos == 0 or n_pos == len(y):
        # Undefined rather than silently zero: a split with one class present
        # cannot produce a meaningful AUC and pretending otherwise misleads.
        return RankingMetrics(len(y), n_pos, float(n_pos / max(len(y), 1)),
                              float("nan"), float("nan"), float("nan"))
    return RankingMetrics(
        n=len(y),
        n_positive=n_pos,
        base_rate=float(y.mean()),
        pr_auc=float(average_precision_score(y, scores)),
        roc_auc=float(roc_auc_score(y, scores)),
        brier=float(brier_score_loss(y, np.clip(scores, 0, 1))),
    )


# Binary (block / allow) metrics


@dataclass
class BinaryMetrics:
    threshold: float
    tp: int
    fp: int
    tn: int
    fn: int
    precision: float
    recall: float
    f1: float
    fpr: float
    fnr: float
    alert_rate: float
    n_predicted_positive: int

    def as_dict(self) -> dict:
        return asdict(self)


def binary_metrics(y: np.ndarray, scores: np.ndarray, threshold: float) -> BinaryMetrics:
    """Confusion matrix and its derived rates at one cut point."""
    y = np.asarray(y).astype(int)
    pred = (np.asarray(scores, dtype=float) >= threshold).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return BinaryMetrics(
        threshold=float(threshold),
        tp=tp, fp=fp, tn=tn, fn=fn,
        precision=float(precision),
        recall=float(recall),
        f1=float(f1),
        fpr=float(fp / (fp + tn)) if (fp + tn) else 0.0,
        fnr=float(fn / (fn + tp)) if (fn + tp) else 0.0,
        alert_rate=float((tp + fp) / len(y)) if len(y) else 0.0,
        n_predicted_positive=int(tp + fp),
    )


# Three-way decisions and cost


def decide(scores: np.ndarray, review_threshold: float, block_threshold: float) -> np.ndarray:
    """Map scores to APPROVE / REVIEW / BLOCK."""
    if review_threshold > block_threshold:
        raise ValueError(
            f"review_threshold ({review_threshold}) must not exceed "
            f"block_threshold ({block_threshold})"
        )
    scores = np.asarray(scores, dtype=float)
    out = np.full(len(scores), APPROVE, dtype=object)
    out[scores >= review_threshold] = REVIEW
    out[scores >= block_threshold] = BLOCK
    return out


@dataclass
class CostBreakdown:
    """What a given operating point would cost the merchant."""

    review_threshold: float
    block_threshold: float

    n: int
    n_approve: int
    n_review: int
    n_block: int

    # Outcomes on the approve path (fraud here is a straight loss)
    approved_fraud: int
    approved_fraud_amount: float

    # Outcomes on the block path
    blocked_fraud: int
    blocked_legit: int
    blocked_fraud_amount: float
    blocked_legit_amount: float

    # Outcomes on the review path
    reviewed_fraud: int
    reviewed_legit: int
    reviewed_fraud_amount: float

    false_positive_cost: float
    false_negative_cost: float
    review_cost: float
    expected_cost: float
    cost_per_1k: float

    prevented_loss: float
    residual_loss: float
    baseline_loss_no_system: float
    net_benefit: float

    def as_dict(self) -> dict:
        return asdict(self)


def expected_cost(
    y: np.ndarray,
    scores: np.ndarray,
    amounts: np.ndarray,
    review_threshold: float,
    block_threshold: float,
    cost: CostConfig = CONFIG.cost,
) -> CostBreakdown:
    """
    Cost of running the system at one operating point.

    The accounting is deliberately explicit about the three paths, because
    lumping REVIEW in with BLOCK is the most common way these numbers get
    flattered. Reviewing is cheaper than declining but it is not free, and it
    catches only ``review_catch_rate`` of the fraud sent to it. The rest is
    released and lost exactly as if it had been approved.

    ``baseline_loss_no_system`` is what the merchant loses with no model at
    all: every fraudulent transaction succeeds. ``net_benefit`` is that number
    minus the total cost of running the system, so a negative value means the
    system is worse than doing nothing, which a threshold sweep should be
    able to say out loud.
    """
    y = np.asarray(y).astype(int)
    scores = np.asarray(scores, dtype=float)
    amounts = np.asarray(amounts, dtype=float)

    dec = decide(scores, review_threshold, block_threshold)
    is_fraud = y == 1
    is_legit = ~is_fraud
    m_appr, m_rev, m_blk = dec == APPROVE, dec == REVIEW, dec == BLOCK

    def _loss(mask) -> float:
        """Monetary loss from fraud that got through, under the chosen model."""
        if cost.amount_weighted:
            return float(
                (amounts[mask] * cost.false_negative_amount_frac).sum()
                + cost.false_negative_fixed_cost * int(mask.sum())
            )
        return float(cost.false_negative_fixed_cost * int(mask.sum()))

    appr_fraud = m_appr & is_fraud
    rev_fraud = m_rev & is_fraud
    blk_fraud = m_blk & is_fraud
    blk_legit = m_blk & is_legit
    rev_legit = m_rev & is_legit

    # Fraud approved outright is fully lost. Fraud routed to review is lost
    # only for the share the analyst misses.
    fn_cost = _loss(appr_fraud) + (1.0 - cost.review_catch_rate) * _loss(rev_fraud)
    fp_cost = float(cost.false_positive_cost * int(blk_legit.sum()))
    rev_cost = float(cost.manual_review_cost * int(m_rev.sum()))
    total = fn_cost + fp_cost + rev_cost

    baseline = _loss(is_fraud)
    prevented = baseline - fn_cost

    n = len(y)
    return CostBreakdown(
        review_threshold=float(review_threshold),
        block_threshold=float(block_threshold),
        n=n,
        n_approve=int(m_appr.sum()),
        n_review=int(m_rev.sum()),
        n_block=int(m_blk.sum()),
        approved_fraud=int(appr_fraud.sum()),
        approved_fraud_amount=float(amounts[appr_fraud].sum()),
        blocked_fraud=int(blk_fraud.sum()),
        blocked_legit=int(blk_legit.sum()),
        blocked_fraud_amount=float(amounts[blk_fraud].sum()),
        blocked_legit_amount=float(amounts[blk_legit].sum()),
        reviewed_fraud=int(rev_fraud.sum()),
        reviewed_legit=int(rev_legit.sum()),
        reviewed_fraud_amount=float(amounts[rev_fraud].sum()),
        false_positive_cost=fp_cost,
        false_negative_cost=fn_cost,
        review_cost=rev_cost,
        expected_cost=total,
        cost_per_1k=float(total / n * 1000) if n else 0.0,
        prevented_loss=float(prevented),
        residual_loss=float(fn_cost),
        baseline_loss_no_system=float(baseline),
        net_benefit=float(baseline - total),
    )


# Threshold sweeps


def cost_sweep(
    y: np.ndarray,
    scores: np.ndarray,
    amounts: np.ndarray,
    cost: CostConfig = CONFIG.cost,
    n_points: int = 100,
    review_band_frac: float = 0.55,
) -> pd.DataFrame:
    """
    Expected cost across the range of block thresholds.

    The review threshold is tied to the block threshold by ``review_band_frac``
    so the sweep stays one-dimensional and readable. ``choose_thresholds``
    searches both dimensions.
    """
    qs = np.unique(np.quantile(scores, np.linspace(0.50, 0.9995, n_points)))
    rows = []
    for blk in qs:
        rev = blk * review_band_frac
        cb = expected_cost(y, scores, amounts, rev, blk, cost)
        bm = binary_metrics(y, scores, blk)
        rows.append(
            {
                "block_threshold": float(blk),
                "review_threshold": float(rev),
                "precision": bm.precision,
                "recall": bm.recall,
                "f1": bm.f1,
                "fpr": bm.fpr,
                "n_block": cb.n_block,
                "n_review": cb.n_review,
                "expected_cost": cb.expected_cost,
                "cost_per_1k": cb.cost_per_1k,
                "prevented_loss": cb.prevented_loss,
                "net_benefit": cb.net_benefit,
            }
        )
    return pd.DataFrame(rows)


@dataclass
class OperatingPoint:
    name: str
    review_threshold: float
    block_threshold: float
    selected_on: str
    rationale: str

    def as_dict(self) -> dict:
        return asdict(self)


def choose_thresholds(
    y: np.ndarray,
    scores: np.ndarray,
    amounts: np.ndarray,
    cost: CostConfig = CONFIG.cost,
    high_precision_target: float = 0.90,
    high_recall_target: float = 0.80,
    review_band_frac: float = 0.55,
    n_points: int = 200,
    min_alert_rate: float = 0.02,
    min_alerts: int = 100,
) -> Dict[str, OperatingPoint]:
    """
    Pick three operating points on the split this is called with.

    This must only ever be called on validation data. Choosing a threshold by
    looking at the test set converts a held-out estimate into a fitted one, and
    the number stops meaning what the reader thinks it means.

    * ``balanced`` minimises expected cost. This is the point a merchant
      would actually run if they trust the cost model.
    * ``high_precision`` is the cheapest point that still reaches the target
      precision, for merchants who will not tolerate false declines.
    * ``high_recall`` is the cheapest point that still reaches the target
      recall, for merchants under active attack.

    ``min_alert_rate`` and ``min_alerts`` rule out degenerate corners. Without
    them the high-precision search returns a threshold sitting in the extreme
    tail of the validation score distribution. Measured here, one that fired
    on 45 validation transactions and on nothing at all in the following
    period. Perfect precision on an empty set is not an operating point. A
    threshold must be supported by enough validation traffic, in both relative
    and absolute terms, for its precision estimate to mean anything.
    """
    grid = np.unique(np.quantile(scores, np.linspace(0.50, 0.9995, n_points)))
    rows = []
    for blk in grid:
        rev = float(blk * review_band_frac)
        bm = binary_metrics(y, scores, blk)
        cb = expected_cost(y, scores, amounts, rev, blk, cost)
        rows.append(
            (float(blk), rev, bm.precision, bm.recall, cb.expected_cost, bm.alert_rate)
        )
    tab = pd.DataFrame(
        rows,
        columns=["blk", "rev", "precision", "recall", "expected_cost", "alert_rate"],
    )
    # Points that flag almost nothing are excluded from *targeted* selection
    # below; the cost-minimising point is still free to pick any of them.
    floor = max(min_alert_rate, min_alerts / max(len(y), 1))
    viable = tab[tab["alert_rate"] >= floor]
    if viable.empty:
        viable = tab

    out: Dict[str, OperatingPoint] = {}

    best = tab.loc[tab["expected_cost"].idxmin()]
    out["balanced"] = OperatingPoint(
        name="balanced",
        review_threshold=float(best["rev"]),
        block_threshold=float(best["blk"]),
        selected_on="validation",
        rationale="minimises expected cost under the configured cost model",
    )

    hp = viable[viable["precision"] >= high_precision_target]
    if len(hp):
        pick = hp.loc[hp["expected_cost"].idxmin()]
        rationale = (
            f"cheapest point with precision >= {high_precision_target:.2f} "
            f"and at least {min_alerts} alerts on validation"
        )
    else:
        pick = viable.loc[viable["precision"].idxmax()]
        rationale = (
            f"precision target {high_precision_target:.2f} unreachable on "
            f"validation with at least {min_alerts} alerts; using the best "
            f"supported point (precision {pick['precision']:.4f})"
        )
    out["high_precision"] = OperatingPoint(
        "high_precision", float(pick["rev"]), float(pick["blk"]), "validation", rationale
    )

    hr = viable[viable["recall"] >= high_recall_target]
    if len(hr):
        pick = hr.loc[hr["expected_cost"].idxmin()]
        rationale = f"cheapest point with recall >= {high_recall_target:.2f}"
    else:
        pick = viable.loc[viable["recall"].idxmax()]
        rationale = (
            f"recall target {high_recall_target:.2f} unreachable on validation; "
            f"using max-recall point ({pick['recall']:.4f})"
        )
    out["high_recall"] = OperatingPoint(
        "high_recall", float(pick["rev"]), float(pick["blk"]), "validation", rationale
    )
    return out



"""
Check whether the score distribution has moved.

PSI (Population Stability Index) compares two sets of scores. Traffic changes,
attacks start and stop, and a calibration fitted last month stops being right.
PSI is a cheap early warning.

Standard reading:

    below 0.10   stable
    0.10 to 0.25 watch it
    above 0.25   it moved, recalibrate
"""

from __future__ import annotations

from typing import Dict

import numpy as np

STABLE, MONITOR, SHIFTED = "STABLE", "MONITOR", "SHIFTED"


def population_stability_index(
    reference: np.ndarray, current: np.ndarray, n_bins: int = 10
) -> float:
    """
    PSI between two samples.

    Bin edges come from the *reference* quantiles, not from a fixed grid, so
    the metric stays meaningful for scores that concentrate in a narrow band.
    Empty bins are floored rather than dropped, which keeps the sum finite
    without silently understating a shift.
    """
    reference = np.asarray(reference, dtype=float)
    current = np.asarray(current, dtype=float)
    if len(reference) == 0 or len(current) == 0:
        return float("nan")

    edges = np.unique(np.quantile(reference, np.linspace(0, 1, n_bins + 1)))
    if len(edges) < 3:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf

    ref_pct = np.histogram(reference, edges)[0] / len(reference)
    cur_pct = np.histogram(current, edges)[0] / len(current)

    eps = 1e-6
    ref_pct = np.where(ref_pct == 0, eps, ref_pct)
    cur_pct = np.where(cur_pct == 0, eps, cur_pct)
    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def classify(psi: float) -> str:
    if np.isnan(psi):
        return MONITOR
    if psi < 0.10:
        return STABLE
    if psi < 0.25:
        return MONITOR
    return SHIFTED


def drift_report(
    reference: np.ndarray,
    current: np.ndarray,
    reference_name: str = "validation",
    current_name: str = "test",
) -> Dict[str, object]:
    """PSI plus the distribution facts an operator would want alongside it."""
    psi = population_stability_index(reference, current)
    status = classify(psi)
    messages = {
        STABLE: "score distribution is stable; calibration should hold",
        MONITOR: "score distribution has moved; watch calibration",
        SHIFTED: (
            "score distribution has shifted a lot. The calibrator fitted "
            f"on {reference_name} will understate risk on {current_name}, so "
            "recalibration is indicated before the thresholds are trusted"
        ),
    }
    return {
        "reference": reference_name,
        "current": current_name,
        "psi": round(psi, 4),
        "status": status,
        "implication": messages[status],
        "reference_mean": round(float(np.mean(reference)), 4),
        "current_mean": round(float(np.mean(current)), 4),
        "reference_max": round(float(np.max(reference)), 4),
        "current_max": round(float(np.max(current)), 4),
        "reference_n": int(len(reference)),
        "current_n": int(len(current)),
    }

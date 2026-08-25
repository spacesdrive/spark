"""
Combine the four scores and turn them into a probability.

Four views of the same transaction:

    tabular      tree model on label-free features
    graph        graph network over the transaction graph
    behavioral   how unusual this is for the entity, no labels
    velocity     how fast and how concentrated the activity is, no labels

They are added together with weights. The weights are searched on the
validation split, not guessed.

The combined score is then calibrated with isotonic regression. Before
calibration a 0.7 does not mean "70 percent of these are fraud". After
calibration it roughly does. This matters because every threshold is picked by
expected cost, and cost is meaningless if the probabilities are wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from ml.config import CONFIG, Config

CHANNELS: List[str] = ["tabular", "graph", "behavioral", "velocity"]


def _stack(scores: Dict[str, np.ndarray]) -> np.ndarray:
    missing = [c for c in CHANNELS if c not in scores]
    if missing:
        raise KeyError(f"missing channel scores: {missing}")
    return np.column_stack([np.asarray(scores[c], dtype=float) for c in CHANNELS])


def _simplex_candidates(n: int, seed: int) -> np.ndarray:
    """
    Candidate weight vectors: a coarse deterministic grid plus a Dirichlet
    sample. The grid guarantees the obvious corners (each channel alone, equal
    weights) are always tried; the sample fills the interior.
    """
    grid: List[List[float]] = []
    for i in range(len(CHANNELS)):
        w = [0.0] * len(CHANNELS)
        w[i] = 1.0
        grid.append(w)
    grid.append([1.0 / len(CHANNELS)] * len(CHANNELS))
    grid.append([0.45, 0.35, 0.10, 0.10])  # the value suggested in the brief

    step = 0.25
    levels = np.arange(0.0, 1.0 + 1e-9, step)
    for a in levels:
        for b in levels:
            for c in levels:
                d = 1.0 - a - b - c
                if -1e-9 <= d <= 1.0 + 1e-9:
                    grid.append([a, b, c, max(d, 0.0)])

    rng = np.random.default_rng(seed)
    sampled = rng.dirichlet(np.ones(len(CHANNELS)), size=max(n - len(grid), 0))
    return np.vstack([np.asarray(grid, dtype=float), sampled])


@dataclass
class FusionModel:
    """Searched fusion weights plus the isotonic calibrator fitted on top."""

    weights: Dict[str, float]
    calibrator: Optional[IsotonicRegression]
    selection_metric: str
    val_score_uncalibrated: float
    val_score_calibrated: float
    default_weight_score: float
    search_size: int
    leaderboard: List[dict] = field(default_factory=list)

    def fuse(self, scores: Dict[str, np.ndarray]) -> np.ndarray:
        """Weighted blend of the four channels, before calibration."""
        w = np.array([self.weights[c] for c in CHANNELS], dtype=float)
        return _stack(scores) @ w

    def predict(self, scores: Dict[str, np.ndarray]) -> np.ndarray:
        """Final calibrated risk probability."""
        fused = self.fuse(scores)
        if self.calibrator is None:
            return np.clip(fused, 0.0, 1.0)
        return np.clip(self.calibrator.predict(fused), 0.0, 1.0)

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        return path

    @staticmethod
    def load(path: Path) -> "FusionModel":
        return joblib.load(Path(path))


def _metric(y: np.ndarray, s: np.ndarray, name: str) -> float:
    if name == "pr_auc":
        return float(average_precision_score(y, s))
    if name == "roc_auc":
        return float(roc_auc_score(y, s))
    raise ValueError(f"unknown selection metric {name!r}")


def fit_fusion(
    val_scores: Dict[str, np.ndarray],
    y_val: np.ndarray,
    cfg: Config = CONFIG,
    verbose: bool = True,
) -> FusionModel:
    """
    Search fusion weights and fit the calibrator, both on validation only.

    Using validation for this is what keeps the test set held out. Fusion
    weights and calibration are model selection: fitting them against test
    scores would turn the final numbers into training performance wearing a
    held-out label.
    """
    fcfg = cfg.fusion
    S = _stack(val_scores)
    y = np.asarray(y_val).astype(int)

    candidates = _simplex_candidates(fcfg.n_weight_candidates, fcfg.seed)
    results = []
    for w in candidates:
        total = w.sum()
        if total <= 0:
            continue
        w = w / total
        results.append((float(_metric(y, S @ w, fcfg.selection_metric)), w))

    results.sort(key=lambda r: r[0], reverse=True)
    best_score, best_w = results[0]

    default_w = np.array([cfg.fusion.default_weights[c] for c in CHANNELS])
    default_w = default_w / default_w.sum()
    default_score = float(_metric(y, S @ default_w, fcfg.selection_metric))

    fused_val = S @ best_w
    calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    calibrator.fit(fused_val, y)
    calibrated = np.clip(calibrator.predict(fused_val), 0.0, 1.0)

    leaderboard = [
        {"weights": dict(zip(CHANNELS, np.round(w, 4).tolist())), "score": round(s, 6)}
        for s, w in results[:10]
    ]

    if verbose:
        print(f"[fusion] searched {len(results)} weight vectors on validation")
        print(f"[fusion] best     {dict(zip(CHANNELS, np.round(best_w, 3)))} "
              f"-> {fcfg.selection_metric}={best_score:.4f}")
        print(f"[fusion] brief's suggested weights "
              f"{dict(zip(CHANNELS, np.round(default_w, 3)))} "
              f"-> {fcfg.selection_metric}={default_score:.4f}")
        print(f"[fusion] calibration: Brier "
              f"{brier_score_loss(y, np.clip(fused_val, 0, 1)):.4f} -> "
              f"{brier_score_loss(y, calibrated):.4f}")

    return FusionModel(
        weights={c: float(w) for c, w in zip(CHANNELS, best_w)},
        calibrator=calibrator,
        selection_metric=fcfg.selection_metric,
        val_score_uncalibrated=float(best_score),
        val_score_calibrated=float(_metric(y, calibrated, fcfg.selection_metric)),
        default_weight_score=default_score,
        search_size=len(results),
        leaderboard=leaderboard,
    )


def calibration_table(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> pd.DataFrame:
    """
    Reliability table: predicted probability against observed frequency.

    A well-calibrated model has ``mean_predicted`` close to ``observed_rate``
    in every populated bin. This is the evidence for the claim that the score
    is a probability rather than just a ranking.
    """
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, n_bins - 1)
    rows = []
    for b in range(n_bins):
        m = idx == b
        if not m.any():
            continue
        rows.append(
            {
                "bin": f"[{edges[b]:.1f}, {edges[b + 1]:.1f})",
                "n": int(m.sum()),
                "mean_predicted": float(p[m].mean()),
                "observed_rate": float(y[m].mean()),
                "gap": float(p[m].mean() - y[m].mean()),
            }
        )
    return pd.DataFrame(rows)

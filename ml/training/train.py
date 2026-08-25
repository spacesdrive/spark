"""
Train everything and save it.

    python -m ml.training.train

Runs each step in order and writes the results to artifacts/. The scoring
engine and the CLI load that folder, so what was measured is what gets served.

Order:

    prepare, graph, Model A, Model B, extra channels, fusion,
    calibration, thresholds, rings

Thresholds and fusion weights are fitted on validation. The test split is not
touched anywhere in this file.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Optional

import numpy as np
import pandas as pd

from ml.calibration.fuse import CHANNELS, FusionModel, fit_fusion
from ml.config import ARTIFACT_DIR, CONFIG, RAW_CSV, Config
from ml.data.loader import file_digest
from ml.evaluation.metrics import choose_thresholds, ranking_metrics
from ml.graph.build import build_relation_graph, neighbour_risk_features
from ml.graph.rings import (
    annotate_with_labels,
    detect_rings,
    transaction_to_cluster,
)
from ml.models.components import fit_channels
from ml.models.graph_nn import train_graph_model
from ml.models.tabular import train_tabular
from ml.preprocessing.prepare import Dataset, describe, prepare


@dataclass
class TrainedBundle:
    """Everything training produced, held together in memory."""

    dataset: Dataset
    tabular: object
    graph_model: object
    channels: object
    fusion: FusionModel
    thresholds: Dict[str, object]
    metadata: dict
    graph: object
    graph_features: pd.DataFrame


def channel_scores(
    ds: Dataset,
    tabular,
    graph_model,
    channels,
    graph_features: pd.DataFrame,
    adj_norm,
) -> Dict[str, np.ndarray]:
    """
    Score all four channels for every transaction in the dataset.

    The graph model is transductive, so it scores the whole node set in one
    pass; the other three are row-wise. Everything is computed once here and
    sliced by split downstream, which keeps train, validation and test scores
    provably consistent with one another.
    """
    X_base = ds.base
    X_graph = pd.concat(
        [ds.base.reset_index(drop=True), ds.risk.reset_index(drop=True),
         graph_features.reset_index(drop=True)],
        axis=1,
    )
    unsup = channels.score(X_base)
    return {
        "tabular": tabular.predict_proba(X_base),
        "graph": graph_model.predict_proba(X_graph, adj_norm),
        "behavioral": unsup["behavioral"],
        "velocity": unsup["velocity"],
    }


def train(
    cfg: Config = CONFIG,
    artifact_dir: Path = ARTIFACT_DIR,
    verbose: bool = True,
    raw_path: Optional[Path] = None,
    progress: Optional[Callable[[str, float], None]] = None,
) -> TrainedBundle:
    """
    Run the full pipeline and persist the artifact bundle.

    ``raw_path`` trains on a different CSV than the built-in one, which is how
    an organization trains on its own transactions. Everything else is
    identical, so a custom model is produced by exactly the same code, with the
    same split discipline, as the built-in one. The feature cache is keyed on a
    hash of the raw file, so one dataset can never reuse another one's cache.

    ``progress`` is called as ``(stage_name, fraction)`` after each step, so a
    caller can report real progress rather than animating a timer.
    """
    t_start = time.perf_counter()
    timings: Dict[str, float] = {}
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Progress is reported from where each step actually starts, so the number
    # a caller shows reflects work done rather than time elapsed.
    stages = ["prepare", "graph", "tabular model", "graph model",
              "unsupervised channels", "fusion", "thresholds", "rings",
              "persist"]

    def _step(name: str) -> float:
        timings[name] = time.perf_counter()
        if verbose:
            print(f"\n=== {name} ===")
        if progress is not None and name in stages:
            progress(name, stages.index(name) / len(stages))
        return timings[name]

    # data
    _step("prepare")
    ds = prepare(cfg=cfg, raw_path=raw_path, verbose=verbose)
    timings["prepare"] = time.perf_counter() - timings["prepare"]
    if verbose:
        print(ds.summary().to_string(index=False))

    tr = ds.mask("train")
    va = ds.mask("val")
    if not tr.any() or not va.any():
        raise RuntimeError("train or validation split has no labeled rows")

    # graph
    _step("graph")
    graph = build_relation_graph(ds.df, cfg=cfg, verbose=verbose)
    gfeat = neighbour_risk_features(
        graph, ds.y, ds.labeled, lag=cfg.features.label_lag_steps, verbose=verbose
    )
    adj_norm = graph.normalised()
    timings["graph"] = time.perf_counter() - timings["graph"]
    if verbose:
        print(graph.describe().to_string(index=False))

    # Model A
    _step("tabular model")
    tabular = train_tabular(
        ds.base[tr], ds.y[tr], ds.base[va], ds.y[va], cfg=cfg, verbose=verbose
    )
    timings["tabular model"] = time.perf_counter() - timings["tabular model"]

    # Model B
    _step("graph model")
    X_graph = pd.concat(
        [ds.base.reset_index(drop=True), ds.risk.reset_index(drop=True),
         gfeat.reset_index(drop=True)],
        axis=1,
    )
    graph_model = train_graph_model(
        X_graph, ds.y, adj_norm, tr, va, cfg=cfg, verbose=verbose
    )
    timings["graph model"] = time.perf_counter() - timings["graph model"]

    # unsupervised channels
    _step("unsupervised channels")
    channels = fit_channels(ds.base, tr)
    timings["unsupervised channels"] = (
        time.perf_counter() - timings["unsupervised channels"]
    )

    # fusion + calibration
    _step("fusion")
    all_scores = channel_scores(ds, tabular, graph_model, channels, gfeat, adj_norm)
    val_scores = {k: v[va] for k, v in all_scores.items()}
    fusion = fit_fusion(val_scores, ds.y[va], cfg=cfg, verbose=verbose)
    timings["fusion"] = time.perf_counter() - timings["fusion"]

    if verbose:
        print("\n[fusion] per-channel validation ranking quality:")
        for ch in CHANNELS:
            m = ranking_metrics(ds.y[va], val_scores[ch])
            print(f"  {ch:<11} PR-AUC={m.pr_auc:.4f}  ROC-AUC={m.roc_auc:.4f}")

    # thresholds
    _step("thresholds")
    p_val = fusion.predict(val_scores)
    amounts = ds.df["Amount"].to_numpy()
    thresholds = choose_thresholds(
        ds.y[va],
        p_val,
        amounts[va],
        cost=cfg.cost,
        high_precision_target=cfg.decision.high_precision_target,
        high_recall_target=cfg.decision.high_recall_target,
        review_band_frac=cfg.decision.review_band_frac,
    )
    timings["thresholds"] = time.perf_counter() - timings["thresholds"]
    if verbose:
        for name, op in thresholds.items():
            print(f"  {name:<15} review>={op.review_threshold:.4f} "
                  f"block>={op.block_threshold:.4f}  ({op.rationale})")

    # rings
    _step("rings")
    p_all = fusion.predict(all_scores)
    rings = detect_rings(ds.df, cfg=cfg, txn_risk=p_all, verbose=verbose)
    rings = annotate_with_labels(rings, ds.y, ds.labeled)
    timings["rings"] = time.perf_counter() - timings["rings"]

    # persist
    _step("persist")
    import joblib

    tabular.save(artifact_dir / "tabular_model.joblib")
    graph_model.save(artifact_dir / "graph_model.pt")
    fusion.save(artifact_dir / "fusion.joblib")
    joblib.dump(channels, artifact_dir / "channels.joblib")

    ring_rows = [r.as_dict() for r in rings]
    with open(artifact_dir / "rings.json", "w", encoding="utf-8") as fh:
        json.dump(ring_rows, fh, indent=2)
    # Exact transaction -> ring map, so the scoring engine and the evaluation
    # always agree about who belongs to which ring.
    with open(artifact_dir / "ring_membership.json", "w", encoding="utf-8") as fh:
        json.dump(transaction_to_cluster(rings), fh)
    np.save(artifact_dir / "channel_scores.npy", np.column_stack(
        [all_scores[c] for c in CHANNELS]
    ))
    np.save(artifact_dir / "fused_scores.npy", p_all)

    # Stop the save timer before building metadata. Metadata includes the
    # timing dict, so measuring after would store the raw clock value
    # instead of an elapsed time.
    timings["persist"] = time.perf_counter() - timings["persist"]

    metadata = {
        "model_version": cfg.model_version,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "seed": cfg.seed,
        "dataset": describe(ds),
        "raw_sha256": file_digest(RAW_CSV),
        "config": cfg.to_dict(),
        "channels": CHANNELS,
        "fusion_weights": fusion.weights,
        "fusion_selection_metric": fusion.selection_metric,
        "fusion_val_score": fusion.val_score_uncalibrated,
        "fusion_val_score_calibrated": fusion.val_score_calibrated,
        "fusion_default_weight_score": fusion.default_weight_score,
        "fusion_leaderboard": fusion.leaderboard,
        "tabular_features": tabular.feature_names,
        "tabular_best_iteration": tabular.best_iteration,
        "graph_features": list(X_graph.columns),
        "graph_best_epoch": graph_model.best_epoch,
        "graph_val_pr_auc": graph_model.best_val_pr_auc,
        "graph_structure": graph.describe().to_dict(orient="records"),
        "thresholds": {k: v.as_dict() for k, v in thresholds.items()},
        "n_rings_detected": len(rings),
        "timings_seconds": {k: round(v, 3) for k, v in timings.items()},
        "total_train_seconds": round(time.perf_counter() - t_start, 3),
    }
    with open(artifact_dir / "model_metadata.json", "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2, default=str)

    if verbose:
        print(f"\n[train] artifacts written to {artifact_dir}")
        print(f"[train] total {metadata['total_train_seconds']}s")

    return TrainedBundle(
        dataset=ds,
        tabular=tabular,
        graph_model=graph_model,
        channels=channels,
        fusion=fusion,
        thresholds=thresholds,
        metadata=metadata,
        graph=graph,
        graph_features=gfeat,
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Train the Spark risk models.")
    ap.add_argument("--artifacts", default=str(ARTIFACT_DIR))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    train(artifact_dir=Path(args.artifacts), verbose=not args.quiet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

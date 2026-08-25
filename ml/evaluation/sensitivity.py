"""
How much does the chargeback delay matter?

The biggest assumption in this project is how fast a merchant learns that a
payment was fraud. Entity risk counts are the strongest signal we have, and
they are only worth something if the confirmations arrive in time.

Assuming they arrive instantly is the usual shortcut and it is wrong. Real
chargebacks land weeks later.

This retrains and re-evaluates the whole pipeline at several delays, so you
can see how much of the headline number depends on the assumption.

Each run is isolated: its own artifact folder and its own feature cache key.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import shutil
import tempfile
from pathlib import Path
from typing import List

import pandas as pd

from ml.config import CONFIG, REPORT_DIR
from ml.evaluation.evaluate import evaluate
from ml.training.train import train

#: Delays to evaluate, in ``Time`` units. The stream is 77,881 transactions
#: long, so 2,000 is roughly 2.6% of it and 6,000 roughly 7.7%.
DEFAULT_LAGS: List[int] = [0, 500, 2000, 6000]


def run_one(lag: int, verbose: bool = False) -> dict:
    """Train and evaluate the full pipeline at one disclosure delay."""
    cfg = dataclasses.replace(
        CONFIG,
        features=dataclasses.replace(CONFIG.features, label_lag_steps=lag),
    )
    tmp = Path(tempfile.mkdtemp(prefix=f"spark_lag_{lag}_"))
    try:
        train(cfg=cfg, artifact_dir=tmp, verbose=verbose)
        ev = evaluate(cfg=cfg, artifact_dir=tmp, report_dir=tmp, verbose=False)

        test = next(r for r in ev["ranking_by_split"] if r["split"] == "test")
        val = next(r for r in ev["ranking_by_split"] if r["split"] == "val")
        bal = next(r for r in ev["operating_points_test"] if r["mode"] == "balanced")
        rings = ev["rings"]["test"]

        return {
            "label_lag_steps": lag,
            "val_pr_auc": val["pr_auc"],
            "test_pr_auc": test["pr_auc"],
            "test_roc_auc": test["roc_auc"],
            "test_precision": bal["precision"],
            "test_recall": bal["recall"],
            "test_f1": bal["f1"],
            "test_expected_cost": bal["expected_cost"],
            "test_net_benefit": bal["net_benefit"],
            "ring_precision": rings["precision"],
            "ring_recall": rings["recall_of_test_fraud"],
            "fusion_weights": ev["fusion_weights"],
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run(lags: List[int] = None, verbose: bool = False) -> pd.DataFrame:
    lags = lags or DEFAULT_LAGS
    rows = []
    for lag in lags:
        print(f"\n[sensitivity] === label_lag_steps = {lag} ===")
        row = run_one(lag, verbose=verbose)
        rows.append(row)
        print(
            f"[sensitivity] lag={lag:5d}  test PR-AUC={row['test_pr_auc']:.4f}  "
            f"ROC-AUC={row['test_roc_auc']:.4f}  "
            f"ring precision={row['ring_precision']}"
        )
    return pd.DataFrame(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Chargeback-lag sensitivity study.")
    ap.add_argument("--lags", type=int, nargs="+", default=DEFAULT_LAGS)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    df = run(args.lags, verbose=args.verbose)

    print("\n" + "=" * 74)
    print("CHARGEBACK-LAG SENSITIVITY  (held-out test)")
    print("=" * 74)
    cols = ["label_lag_steps", "val_pr_auc", "test_pr_auc", "test_roc_auc",
            "test_precision", "test_recall", "test_expected_cost",
            "ring_precision", "ring_recall"]
    print(df[cols].to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    print("\nReading this table:")
    print("  label_lag_steps = 0 assumes a chargeback is known the instant the")
    print("  transaction happens. It is the number most fraud papers report and")
    print("  it is not achievable in production. The rows below it show what the")
    print("  same pipeline delivers once confirmations arrive late.")
    print()
    print("  The ring detector reads no labels at all, so its precision and")
    print("  recall are the columns that should barely move. That is the point")
    print("  of having it: it is the part of the system that keeps working when")
    print("  the feedback loop is slow.")

    out = Path(REPORT_DIR) / "sensitivity.json"
    out.write_text(json.dumps(df.to_dict(orient="records"), indent=2, default=float),
                   encoding="utf-8")
    print(f"\nWritten to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Run everything end to end.

    python -m spark.demo

Scores the held-out test split, then prints: example decisions with reasons,
the rings behind them, the measured test metrics, the cost of each operating
point, and the scoring speed.

Every number comes from actually running the pipeline.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

from ml.config import ARTIFACT_DIR, CONFIG, REPORT_DIR
from ml.evaluation.evaluate import evaluate
from spark._cliutil import header, kv, rule, section, table
from spark.risk.audit import AuditLog
from spark.risk.engine import ScoringEngine
from spark.risk.score import render_decision


def _percentiles(values: List[float]) -> dict:
    a = np.asarray(values, dtype=float)
    return {
        "n": len(a),
        "mean_ms": float(a.mean()),
        "p50_ms": float(np.percentile(a, 50)),
        "p95_ms": float(np.percentile(a, 95)),
        "p99_ms": float(np.percentile(a, 99)),
        "max_ms": float(a.max()),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="End-to-end Spark demonstration.")
    ap.add_argument("--mode", default="balanced",
                    help="operating point: balanced, high_precision, high_recall")
    ap.add_argument("--examples", type=int, default=3,
                    help="worked examples to display")
    ap.add_argument("--bench", type=int, default=500,
                    help="transactions to time for the latency benchmark")
    ap.add_argument("--artifacts", default=str(ARTIFACT_DIR))
    ap.add_argument("--skip-eval", action="store_true",
                    help="skip the held-out evaluation (faster)")
    args = ap.parse_args(argv)

    header("SPARK  -  ABUSE-RING SENTINEL")
    print("Track 02: AI Risk Manager.  Defence-only: this system detects,")
    print("scores, explains and flags. It never advises how to evade.")
    # 1. load
    section("1. loading trained model")
    t0 = time.perf_counter()
    try:
        engine = ScoringEngine(artifact_dir=Path(args.artifacts), mode=args.mode)
    except FileNotFoundError as exc:
        print(f"\n{exc}")
        return 1
    load_s = time.perf_counter() - t0

    meta = engine.metadata
    kv("model version", meta["model_version"])
    kv("trained", meta["created_utc"])
    kv("dataset", "S-FFSD (public, simulated)")
    kv("raw sha256", meta["raw_sha256"][:16] + "...")
    kv("chargeback lag", f"{meta['config']['features']['label_lag_steps']} time units")
    kv("fusion weights", ", ".join(
        f"{k}={v:.3f}" for k, v in meta["fusion_weights"].items()))
    kv("operating mode", f"{args.mode}  "
                         f"(review>={engine.review_threshold:.4f}, "
                         f"block>={engine.block_threshold:.4f})")
    kv("total load time", f"{load_s:.2f}s")
    for k, v in engine.timings.items():
        kv(f"  {k}", f"{v:.1f} ms")
    # 2. score the held-out split
    section("2. scoring the held-out test split")
    te_idx = np.where(engine.ds.mask("test"))[0]
    t0 = time.perf_counter()
    batch = engine.score_batch(te_idx)
    batch_s = time.perf_counter() - t0
    kv("transactions scored", f"{len(batch):,}")
    kv("wall time", f"{batch_s:.2f}s")
    kv("throughput", f"{len(batch) / batch_s:,.0f} txn/s")

    counts = batch["decision"].value_counts()
    print()
    for k in ("APPROVE", "REVIEW", "BLOCK"):
        n = int(counts.get(k, 0))
        print(f"  {k:<8} {n:6,}  ({n / len(batch):6.1%})")
    # 3. worked examples
    section(f"3. worked examples ({args.examples} highest-risk transactions)")
    top = batch.nlargest(args.examples, "risk_score")["index"].to_numpy()
    audit = AuditLog()
    for i in top:
        d = engine.score_one(int(i))
        render_decision(d)
        audit.record(d.as_dict())
    # 4. rings
    section("4. abuse rings detected (label-free)")
    rings = sorted(engine.rings, key=lambda r: r["risk_score"], reverse=True)
    if rings:
        view = pd.DataFrame(rings)[[
            "cluster_id", "n_accounts", "n_transactions", "total_value",
            "fan_in", "temporal_density", "small_amount_score", "risk_score",
            "confirmed_labeled", "confirmed_fraud",
        ]].head(8).copy()
        view["precision"] = (
            view["confirmed_fraud"] / view["confirmed_labeled"].replace(0, np.nan)
        )
        table(view, floats="{:.3f}")
        print("\n  precision here is checked against confirmed outcomes AFTER")
        print("  detection. The detector itself never reads a label.")
    else:
        print("  no rings in the artifact bundle")
    # 5. held-out metrics
    if args.skip_eval:
        print("\n(skipping held-out evaluation)")
        return 0

    section("5. held-out evaluation")
    print("  thresholds and fusion weights were fixed on validation;")
    print("  the test split below was not used to select anything.\n")
    ev = evaluate(artifact_dir=Path(args.artifacts), report_dir=REPORT_DIR,
                  verbose=False)

    print(rule())
    print("HELD-OUT TEST RESULTS")
    print(rule())
    row = next(r for r in ev["ranking_by_split"] if r["split"] == "test")
    op = next(r for r in ev["operating_points_test"] if r["mode"] == args.mode)

    kv("transactions", f"{row['n']:,}")
    kv("fraud (base rate)", f"{row['n_positive']:,}  ({row['base_rate']:.4f})")
    print()
    kv("Precision", f"{op['precision']:.4f}")
    kv("Recall", f"{op['recall']:.4f}")
    kv("F1", f"{op['f1']:.4f}")
    kv("PR-AUC", f"{row['pr_auc']:.4f}")
    kv("ROC-AUC", f"{row['roc_auc']:.4f}")
    kv("FPR", f"{op['fpr']:.4f}")
    kv("FNR", f"{op['fnr']:.4f}")
    kv("Brier score", f"{row['brier']:.4f}")
    print()
    kv("Confusion matrix", f"TP={op['tp']:,}  FP={op['fp']:,}  "
                           f"FN={op['fn']:,}  TN={op['tn']:,}")
    if not op["transfers"]:
        print(f"\n  ! {op['transfer_note']}")

    section("false-positive cost and business impact")
    c = CONFIG.cost
    kv("false positive cost", f"{c.false_positive_cost:.2f} per blocked good order")
    kv("false negative cost",
       f"{c.false_negative_amount_frac:.0%} of amount + "
       f"{c.false_negative_fixed_cost:.2f} fixed")
    kv("manual review cost", f"{c.manual_review_cost:.2f} per review "
                             f"(catches {c.review_catch_rate:.0%} of fraud)")
    print()
    kv("Expected cost", f"{op['expected_cost']:,.2f}")
    kv("Cost per 1,000 txn", f"{op['cost_per_1k']:,.2f}")
    kv("Loss with no system", f"{op['baseline_loss_no_system']:,.2f}")
    kv("Prevented loss", f"{op['prevented_loss']:,.2f}")
    kv("Residual loss", f"{op['residual_loss']:,.2f}")
    kv("Net benefit", f"{op['net_benefit']:,.2f}")

    section("all operating points on held-out test")
    table(pd.DataFrame(ev["operating_points_test"])[
        ["mode", "block_threshold", "precision", "recall", "f1",
         "fpr", "expected_cost", "net_benefit", "transfers"]
    ])

    section("ring detector on held-out test")
    rt = ev["rings"]["test"]
    kv("alert threshold", f"{ev['rings']['threshold_selected_on_validation']} "
                          f"(chosen on validation)")
    if rt["precision"] is not None:
        kv("rings alerted", rt["rings_alerted"])
        kv("confirmed txns covered", f"{rt['confirmed_transactions_covered']:,}")
        kv("Precision", f"{rt['precision']:.4f}")
        kv("Recall", f"{rt['recall_of_test_fraud']:.4f}")
        kv("Lift over base rate", f"{rt['lift_over_base']:.2f}x")

    section("score drift, validation -> test")
    d = ev["score_drift"]
    kv("PSI", f"{d['psi']}  ({d['status']})")
    print(f"  {d['implication']}")
    # 6. latency
    section("6. scoring latency")
    n_bench = min(args.bench, len(te_idx))
    sample = te_idx[:n_bench]
    lat: List[float] = []
    for i in sample:
        t0 = time.perf_counter()
        engine.score_one(int(i), explain=False)
        lat.append((time.perf_counter() - t0) * 1000)
    p = _percentiles(lat)
    kv("measured on", f"{p['n']:,} transactions (explanation off)")
    kv("mean", f"{p['mean_ms']:.2f} ms")
    kv("p50", f"{p['p50_ms']:.2f} ms")
    kv("p95", f"{p['p95_ms']:.2f} ms")
    kv("p99", f"{p['p99_ms']:.2f} ms")

    lat_x: List[float] = []
    for i in sample[: min(100, n_bench)]:
        t0 = time.perf_counter()
        engine.score_one(int(i), explain=True)
        lat_x.append((time.perf_counter() - t0) * 1000)
    px = _percentiles(lat_x)
    print()
    kv("with SHAP explanation", f"{px['n']:,} transactions")
    kv("  mean", f"{px['mean_ms']:.2f} ms")
    kv("  p95", f"{px['p95_ms']:.2f} ms")

    print()
    kv("batch throughput", f"{len(batch) / batch_s:,.0f} txn/s")
    print("\n  One-off costs paid at startup, not per transaction:")
    for k, v in engine.timings.items():
        kv(f"    {k}", f"{v:.1f} ms")

    bench_path = Path(REPORT_DIR) / "latency.json"
    bench_path.write_text(json.dumps(
        {"per_transaction": p, "with_explanation": px,
         "batch_throughput_per_s": len(batch) / batch_s,
         "startup": engine.timings}, indent=2), encoding="utf-8")

    print(f"\n{rule()}")
    print(f"Reports written to {REPORT_DIR}")
    print(f"Audit log:         {audit.path}")
    print(rule())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

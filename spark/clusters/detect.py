"""
Find and inspect abuse rings.

    python -m spark.clusters.detect --top 10
    python -m spark.clusters.detect --cluster ring_068000_916

Detection reads no fraud labels. The confirmed columns are shown only so you
can check the result afterwards.
"""

from __future__ import annotations

import argparse
import json

import pandas as pd

from ml.config import ARTIFACT_DIR, CONFIG
from ml.graph.rings import annotate_with_labels, clusters_to_frame, detect_rings
from ml.preprocessing.prepare import prepare
from spark._cliutil import header, kv, rule, section, table

SIGNATURE_KEYS = [
    "fan_in",
    "single_use_rate",
    "temporal_density",
    "amount_homogeneity",
    "small_amount_score",
]


def render_cluster(c: dict) -> None:
    print("\n" + rule())
    print(f"Risk Cluster: {c['cluster_id']}")
    print(f"  window            Time {c['window_start']:,} - {c['window_end']:,}")
    print(f"  active            Time {c['first_seen']:,} - {c['last_seen']:,} "
          f"(span {c['time_span']:,})")
    print(f"\n  accounts          {c['n_accounts']:,}")
    print(f"  transactions      {c['n_transactions']:,}")
    print(f"  merchant cells    {c['n_cells']}")
    print(f"  total value       {c['total_value']:,.2f}")
    print(f"  median amount     {c['median_amount']:,.2f}")
    print(f"\n  merchants         {', '.join(c['merchants'][:5])}")
    print(f"  channels          {', '.join(c['channels'][:5])}")
    print(f"  locations         {', '.join(c['locations'][:5])}")
    print(f"\n  ring score        {c['risk_score']:.4f}  "
          f"(confidence {c['confidence']:.2f})")
    print("  signature:")
    for k in SIGNATURE_KEYS:
        print(f"    {k:<22} {c[k]:.4f}")
    print("\n  why this was flagged:")
    for r in c["reasons"]:
        print(f"    - {r}")
    if c.get("mean_txn_risk") is not None:
        print(f"\n  mean transaction risk score  {c['mean_txn_risk']:.4f}")
    if c.get("confirmed_labeled"):
        prec = c["confirmed_fraud"] / c["confirmed_labeled"]
        print(f"  confirmed outcomes           {c['confirmed_labeled']:,} "
              f"({c['confirmed_fraud']:,} fraud, precision {prec:.4f})")
        print("  (ground truth, checked after detection - never an input)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Detect abuse rings.")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--cluster", help="show one cluster by id")
    ap.add_argument("--min-score", type=float, default=0.0)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--from-artifacts", action="store_true",
                    help="load rings from the trained bundle instead of recomputing")
    args = ap.parse_args(argv)

    if args.from_artifacts:
        rows = json.loads((ARTIFACT_DIR / "rings.json").read_text(encoding="utf-8"))
        frame = pd.DataFrame(rows)
    else:
        ds = prepare(verbose=False)
        rings = annotate_with_labels(
            detect_rings(ds.df, verbose=True), ds.y, ds.labeled
        )
        frame = clusters_to_frame(rings)
        rows = [r.as_dict() for r in rings]

    frame = frame[frame["risk_score"] >= args.min_score]
    rows = [r for r in rows if r["risk_score"] >= args.min_score]

    if args.json:
        print(json.dumps(rows[: args.top], indent=2, default=float))
        return 0

    header("ABUSE-RING DETECTION")
    kv("detection", "label-free (structure, timing, amount shape)")
    kv("candidate rings", f"{len(frame):,}")
    kv("window / stride",
       f"{CONFIG.cluster.window:,} / {CONFIG.cluster.stride:,} time units")

    if args.cluster:
        match = [r for r in rows if r["cluster_id"] == args.cluster]
        if not match:
            print(f"\nNo cluster with id {args.cluster!r}")
            return 1
        render_cluster(match[0])
        return 0

    section(f"top {args.top} rings by score")
    cols = ["cluster_id", "n_accounts", "n_transactions", "total_value"]
    cols += SIGNATURE_KEYS + ["risk_score"]
    view = frame.head(args.top).copy()
    if "confirmed_labeled" in view.columns:
        view["confirmed"] = view["confirmed_labeled"]
        view["fraud"] = view["confirmed_fraud"]
        view["precision"] = view["confirmed_fraud"] / view["confirmed_labeled"]
        cols += ["confirmed", "fraud", "precision"]
    table(view[cols], floats="{:.3f}")

    for r in rows[: min(3, args.top)]:
        render_cluster(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Show the feature matrix.

    python -m spark.features.build

Prints what was built, which group each feature belongs to, and a check that
the features really do only look at the past.
"""

from __future__ import annotations

import argparse

from ml.preprocessing.prepare import prepare
from spark._cliutil import header, kv, section, table


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build and describe features.")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--show", type=int, default=12, help="features to list per family")
    args = ap.parse_args(argv)

    ds = prepare(use_cache=not args.no_cache, verbose=True)

    header("FEATURE MATRIX")
    kv("rows", f"{len(ds.df):,}")
    kv("base features", len(ds.base_columns))
    kv("risk features", len(ds.risk_columns))
    kv("total", len(ds.base_columns) + len(ds.risk_columns))

    section("base family: no labels used, feeds the tabular model")
    print("  behaviour, velocity and entity history. No label is ever read.")
    for c in ds.base_columns[: args.show]:
        print(f"    {c}")
    print(f"    ... and {len(ds.base_columns) - args.show} more")

    section("risk family: past outcomes only, feeds the graph model")
    print("  derived from confirmed outcomes that preceded the transaction,")
    print("  delayed by the configured chargeback lag.")
    for c in ds.risk_columns:
        print(f"    {c}")

    section("causality check")
    # The first transaction of the stream has no past, so every history
    # feature must be zero. This is a cheap, direct assertion that the pass
    # emits features before it updates its accumulators.
    first = ds.base.iloc[0]
    hist_cols = [c for c in ds.base_columns
                 if c.endswith(("_txn_count", "_cnt_w20", "_amt_mean_hist"))]
    nonzero = [c for c in hist_cols if abs(float(first[c])) > 1e-9]
    kv("first row history features", f"{len(hist_cols)} checked")
    kv("non-zero among them", f"{len(nonzero)} (expected 0)")
    print("  PASS" if not nonzero else f"  FAIL: {nonzero[:5]}")

    first_risk = ds.risk.iloc[0]
    kv("first row known outcomes",
       f"{float(first_risk['Target_known_outcomes']):.0f} (expected 0)")

    section("summary statistics, base family")
    desc = ds.base.describe().T[["mean", "std", "min", "max"]]
    table(desc.head(args.show).reset_index().rename(columns={"index": "feature"}),
          floats="{:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

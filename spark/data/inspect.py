"""
Look at the raw dataset.

    python -m spark.data.inspect

Prints what the file contains and, just as important, what it does not. The
availability table is where missing fields like device and IP are stated
plainly instead of glossed over.
"""

from __future__ import annotations

import argparse

import pandas as pd

from ml.config import ENTITY_COLS, ENTITY_ROLE, LABEL_FRAUD, LABEL_UNKNOWN, RAW_CSV
from ml.data.loader import load_raw, make_time_splits, validate_raw
from spark._cliutil import header, kv, section, table

#: What an abuse-ring detector wants, against what S-FFSD provides.
#: DERIVED means the system computes it from what is there; NOT AVAILABLE
#: means the field does not exist and the system does not invent it.
ENTITY_AVAILABILITY = [
    ("merchants", "YES", "Target, 886 distinct"),
    ("customer accounts", "YES", "Source, 30,346 distinct"),
    ("transactions", "YES", "one row each"),
    ("devices", "NOT AVAILABLE", "no device identifier in the source data"),
    ("IP addresses", "NOT AVAILABLE", "no network identifier in the source data"),
    ("payment instruments", "PARTIAL", "Type is a channel/instrument class, not a card"),
    ("locations", "YES", "Location, 296 distinct"),
    ("transaction velocity", "DERIVED", "past-only windowed counts per entity"),
    ("coordinated behaviour", "DERIVED", "shared merchant/channel/location + burst"),
    ("fraud labels", "PARTIAL", "38% labeled; the rest is genuinely unknown"),
    ("time-based evaluation", "YES", "Time is a strict transaction sequence"),
    ("graph construction", "YES", "4 entity relations over transaction nodes"),
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Inspect the raw dataset.")
    ap.add_argument("--path", default=str(RAW_CSV))
    ap.add_argument("--rows", type=int, default=8)
    args = ap.parse_args(argv)

    df = load_raw(args.path)
    raw = df.drop(columns=["txn_id"])
    rep = validate_raw(raw)

    header(f"DATASET INSPECTION  -  {args.path}")

    section("schema")
    table(pd.DataFrame({
        "column": raw.columns,
        "dtype": [str(t) for t in raw.dtypes],
        "nulls": raw.isna().sum().to_numpy(),
        "distinct": [raw[c].nunique() for c in raw.columns],
    }))

    section("validation")
    kv("status", "PASS" if rep.ok else "FAIL")
    for e in rep.errors:
        print(f"  ERROR   {e}")
    for w in rep.warnings:
        print(f"  warning {w}")

    section("labels")
    s = rep.stats
    kv("rows", f"{s['n_rows']:,}")
    kv("labeled", f"{s['n_labeled']:,} ({s['n_labeled'] / s['n_rows']:.1%})")
    kv("  fraud", f"{s['n_fraud']:,}")
    kv("  legitimate", f"{s['n_legit']:,}")
    kv("unlabeled", f"{s['n_unlabeled']:,} ({s['n_unlabeled'] / s['n_rows']:.1%})")
    kv("fraud rate (labeled)", f"{s['fraud_rate_labeled']:.4f}")
    print("\n  Unlabeled rows are kept in the graph and in every velocity")
    print("  accumulator, because they are real traffic, but excluded")
    print("  supervised fitting and from every reported metric.")

    section("amounts")
    kv("min / median / max",
       f"{s['amount_min']:.2f} / {s['amount_median']:.2f} / {s['amount_max']:,.2f}")
    kv("mean", f"{s['amount_mean']:.2f}")

    section("entities")
    table(pd.DataFrame({
        "column": ENTITY_COLS,
        "role": [ENTITY_ROLE[c] for c in ENTITY_COLS],
        "distinct": [int(raw[c].nunique()) for c in ENTITY_COLS],
        "top value": [raw[c].value_counts().index[0] for c in ENTITY_COLS],
        "top count": [int(raw[c].value_counts().iloc[0]) for c in ENTITY_COLS],
    }))

    section("what this dataset can and cannot represent")
    table(pd.DataFrame(ENTITY_AVAILABILITY,
                       columns=["capability", "status", "note"]))

    section("fraud rate over time (deciles)")
    d = raw.copy()
    d["decile"] = pd.qcut(d["Time"], 10, labels=False)
    g = d.groupby("decile").agg(
        rows=("Labels", "size"),
        labeled=("Labels", lambda x: int((x != LABEL_UNKNOWN).sum())),
        fraud=("Labels", lambda x: int((x == LABEL_FRAUD).sum())),
    )
    g["fraud_rate"] = (g["fraud"] / g["labeled"]).round(4)
    table(g.reset_index())
    print("\n  The fraud rate more than triples across the stream. A random")
    print("  train/test split would hide this; the time-ordered split does not.")

    section("time-ordered splits")
    table(make_time_splits(df).summary(df))

    section(f"first {args.rows} rows")
    table(raw.head(args.rows), floats="{:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

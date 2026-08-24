"""
Build or refresh the modelling dataset.

    python -m spark.data.prepare
"""

from __future__ import annotations

import argparse
import json

from ml.preprocessing.prepare import describe, prepare
from spark._cliutil import header, kv, section, table


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Prepare the modelling dataset.")
    ap.add_argument("--no-cache", action="store_true", help="force a fresh causal pass")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    ds = prepare(use_cache=not args.no_cache, verbose=not args.json)
    info = describe(ds)
    if args.json:
        print(json.dumps(info, indent=2, default=str))
        return 0

    header("DATASET PREPARED")
    kv("fingerprint", ds.fingerprint)
    kv("base features", info["n_base_features"])
    kv("risk features", info["n_risk_features"])
    kv("train ends at Time", info["train_end_time"])
    kv("val ends at Time", info["val_end_time"])
    section("splits")
    table(ds.summary())
    if info["raw_warnings"]:
        section("data warnings")
        for w in info["raw_warnings"]:
            print(f"  {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

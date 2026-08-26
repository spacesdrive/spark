"""
Score transactions.

    python -m spark.risk.score --split test --limit 10
    python -m spark.risk.score --txn txn_070123
    python -m spark.risk.score --split test --summary

Every decision is added to the audit log.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from ml.config import ARTIFACT_DIR
from ml.evaluation.metrics import binary_metrics
from spark._cliutil import header, kv, rule, section, table
from spark.risk.audit import AuditLog
from spark.risk.engine import ScoringEngine


def render_decision(d, show_channels: bool = True) -> None:
    """One decision, rendered the way an analyst would want to read it."""
    print("\n" + rule())
    print(f"Transaction: {d.transaction_id}    Time: {d.time:,}")
    print(f"{d.source} -> {d.target}   amount {d.amount:,.2f}   "
          f"{d.payment_type} @ {d.location}")
    print(f"\n  Risk Score: {d.risk_score:.4f}")
    print(f"  Decision:   {d.decision}   (mode: {d.mode}, path: {d.path})")
    print(f"  Model:      {d.model_version}")

    if show_channels and d.channel_scores:
        print("\n  Channel scores:")
        for c, v in d.channel_scores.items():
            share = d.channel_attribution.get(c)
            suffix = f"   ({share:.0%} of final score)" if share else ""
            print(f"    {c:<11} {v:.4f}{suffix}")

    if d.reasons:
        print("\n  Contributing factors:")
        for r in d.reasons:
            print(f"    {r}")

    if d.cluster:
        c = d.cluster
        print(f"\n  Risk Cluster: {c['cluster_id']}")
        print(f"    accounts      {c['n_accounts']:,}")
        print(f"    transactions  {c['n_transactions']:,}")
        print(f"    total value   {c['total_value']:,.2f}")
        print(f"    merchants     {', '.join(c['merchants'][:3])}")
        print(f"    channels      {', '.join(c['channels'][:3])}")
        print(f"    ring score    {c['risk_score']:.4f} "
              f"(confidence {c['confidence']:.2f})")
        for r in c["reasons"][:3]:
            print(f"    - {r}")

    if d.label is not None:
        truth = "FRAUD" if d.label == 1 else "legitimate"
        print(f"\n  Ground truth: {truth} "
              f"(never an input; shown for evaluation only)")
    if d.latency_ms is not None:
        print(f"  Scored in {d.latency_ms:.1f} ms")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Score transactions.")
    ap.add_argument("--split", default="test", choices=["train", "val", "test"])
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--txn", help="score one transaction by id")
    ap.add_argument("--mode", default="balanced")
    ap.add_argument("--summary", action="store_true",
                    help="aggregate over the split instead of per-transaction detail")
    ap.add_argument("--highest-risk", action="store_true",
                    help="show the highest-risk transactions rather than the first")
    ap.add_argument("--artifacts", default=str(ARTIFACT_DIR))
    ap.add_argument("--no-audit", action="store_true")
    args = ap.parse_args(argv)

    engine = ScoringEngine(artifact_dir=args.artifacts, mode=args.mode)
    audit = None if args.no_audit else AuditLog()

    header(f"TRANSACTION SCORING  -  mode: {args.mode}")
    kv("review threshold", f"{engine.review_threshold:.4f}")
    kv("block threshold", f"{engine.block_threshold:.4f}")

    if args.txn:
        matches = np.where(engine.ds.df["txn_id"].to_numpy() == args.txn)[0]
        if len(matches) == 0:
            print(f"\nNo transaction with id {args.txn!r}")
            return 1
        d = engine.score_one(int(matches[0]))
        render_decision(d)
        if audit:
            audit.record(d.as_dict())
        return 0

    mask = engine.ds.mask(args.split)
    idx = np.where(mask)[0]

    if args.summary:
        batch = engine.score_batch(idx)
        section(f"{args.split} split, {len(batch):,} labeled transactions")
        counts = batch["decision"].value_counts()
        for k in ("APPROVE", "REVIEW", "BLOCK"):
            n = int(counts.get(k, 0))
            print(f"  {k:<8} {n:6,}  ({n / len(batch):.1%})")
        kv("cold-start path", f"{int((batch['path'] == 'COLD_START').sum()):,}")

        bm = binary_metrics(
            batch["label"].to_numpy(),
            batch["risk_score"].to_numpy(),
            engine.block_threshold,
        )
        section("outcome at the block threshold")
        table(pd.DataFrame([{
            "precision": bm.precision, "recall": bm.recall, "f1": bm.f1,
            "fpr": bm.fpr, "tp": bm.tp, "fp": bm.fp, "fn": bm.fn, "tn": bm.tn,
        }]))
        if audit:
            n = audit.record_many(
                {
                    "transaction_id": r.transaction_id,
                    "risk_score": float(r.risk_score),
                    "decision": r.decision,
                    "path": r.path,
                    "mode": args.mode,
                    "model_version": engine.metadata["model_version"],
                    "amount": float(r.Amount),
                    "time": int(r.Time),
                    "source": r.Source,
                    "target": r.Target,
                }
                for r in batch.itertuples()
            )
            print(f"\n[audit] {n:,} decisions appended to {audit.path}")
        return 0

    if args.highest_risk:
        batch = engine.score_batch(idx)
        idx = batch.nlargest(args.limit, "risk_score")["index"].to_numpy()
    else:
        idx = idx[: args.limit]

    for i in idx:
        d = engine.score_one(int(i))
        render_decision(d)
        if audit:
            audit.record(d.as_dict())

    if audit:
        print(f"\n[audit] appended to {audit.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

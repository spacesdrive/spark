"""
Run the held-out test.

This is the only place the test split is read. Model weights, fusion weights,
the calibrator, and the thresholds all come from the saved artifacts exactly
as training left them. Nothing is refitted here.

It prints more than the headline numbers on purpose:

- every split, so you can see how much worse test is than train
- three operating points, all chosen on validation
- a cost breakdown, because money is the point
- a calibration table, because the cost model needs good probabilities
- a cold-entity slice: how well it works on merchants the system barely knew
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from ml.calibration.fuse import CHANNELS, FusionModel, calibration_table
from ml.config import ARTIFACT_DIR, CONFIG, REPORT_DIR, Config
from ml.evaluation.drift import drift_report
from ml.evaluation.metrics import (
    binary_metrics,
    cost_sweep,
    expected_cost,
    ranking_metrics,
)
from ml.graph.build import build_relation_graph, neighbour_risk_features
from ml.graph.rings import annotate_with_labels, detect_rings
from ml.models.graph_nn import GraphModel
from ml.models.tabular import TabularModel
from ml.preprocessing.prepare import prepare
from ml.training.train import channel_scores


def load_artifacts(artifact_dir: Path = ARTIFACT_DIR) -> dict:
    """Load the bundle produced by ``ml.training.train``."""
    artifact_dir = Path(artifact_dir)
    meta_path = artifact_dir / "model_metadata.json"
    if not meta_path.exists():
        raise FileNotFoundError(
            f"No trained model at {artifact_dir}.\n"
            "Train one first:  python -m ml.training.train"
        )
    with open(meta_path, encoding="utf-8") as fh:
        metadata = json.load(fh)
    return {
        "metadata": metadata,
        "tabular": TabularModel.load(artifact_dir / "tabular_model.joblib"),
        "graph_model": GraphModel.load(artifact_dir / "graph_model.pt"),
        "fusion": FusionModel.load(artifact_dir / "fusion.joblib"),
        "channels": joblib.load(artifact_dir / "channels.joblib"),
    }


def _cold_entity_mask(ds, quantile: float = 0.15) -> np.ndarray:
    """
    Transactions on merchants the system had barely seen before.

    ``Target_txn_count`` is past-only by construction, so this asks: at the
    moment of scoring, how much history did this merchant have? The cut is the
    given quantile of the *training* distribution rather than a fixed count,
    so the slice stays meaningful if the dataset is swapped.

    This is the honest stress test. Entity-history and entity-risk features
    carry no information here, so it is where a system that looks good only
    because it memorised known-bad merchants will come apart.
    """
    counts = ds.base["Target_txn_count"].to_numpy()
    cut = float(np.quantile(counts[ds.splits.train], quantile))
    return counts <= cut


def evaluate(
    cfg: Config = CONFIG,
    artifact_dir: Path = ARTIFACT_DIR,
    report_dir: Path = REPORT_DIR,
    verbose: bool = True,
    raw_path=None,
) -> dict:
    """
    Run the full held-out evaluation and write reports.

    ``raw_path`` evaluates a model trained on a different CSV, which is how a
    custom model is measured. It must be the same file the model was trained
    on, so that the split boundaries line up and the test rows really are rows
    the model never saw.
    """
    art = load_artifacts(artifact_dir)
    meta = art["metadata"]

    ds = prepare(cfg=cfg, raw_path=raw_path, verbose=False)
    graph = build_relation_graph(ds.df, cfg=cfg, verbose=False)
    gfeat = neighbour_risk_features(
        graph, ds.y, ds.labeled, lag=cfg.features.label_lag_steps, verbose=False
    )
    adj_norm = graph.normalised()

    scores = channel_scores(
        ds, art["tabular"], art["graph_model"], art["channels"], gfeat, adj_norm
    )
    fusion: FusionModel = art["fusion"]
    p_all = fusion.predict(scores)
    amounts = ds.df["Amount"].to_numpy()

    masks = {
        "train": ds.mask("train"),
        "val": ds.mask("val"),
        "test": ds.mask("test"),
    }

    out: dict = {
        "model_version": meta["model_version"],
        "fusion_weights": fusion.weights,
        "label_lag_steps": cfg.features.label_lag_steps,
        "thresholds": meta["thresholds"],
    }

    # ranking, per split and per channel
    per_split = []
    for name, m in masks.items():
        r = ranking_metrics(ds.y[m], p_all[m])
        row = {"split": name, **r.as_dict()}
        row["lift_over_base"] = (
            r.pr_auc / r.base_rate if r.base_rate > 0 else float("nan")
        )
        per_split.append(row)
    out["ranking_by_split"] = per_split

    per_channel = []
    for ch in CHANNELS + ["fused"]:
        s = p_all if ch == "fused" else scores[ch]
        row = {"channel": ch}
        for name, m in masks.items():
            row[f"{name}_pr_auc"] = ranking_metrics(ds.y[m], s[m]).pr_auc
        per_channel.append(row)
    out["ranking_by_channel"] = per_channel

    # operating points on the held-out test
    te = masks["test"]
    operating = []
    for name, op in meta["thresholds"].items():
        rev, blk = op["review_threshold"], op["block_threshold"]
        bm = binary_metrics(ds.y[te], p_all[te], blk)
        cb = expected_cost(ds.y[te], p_all[te], amounts[te], rev, blk, cfg.cost)
        operating.append(
            {
                "mode": name,
                "selected_on": op["selected_on"],
                "rationale": op["rationale"],
                "review_threshold": rev,
                "block_threshold": blk,
                **bm.as_dict(),
                "expected_cost": cb.expected_cost,
                "cost_per_1k": cb.cost_per_1k,
                "prevented_loss": cb.prevented_loss,
                "residual_loss": cb.residual_loss,
                "baseline_loss_no_system": cb.baseline_loss_no_system,
                "net_benefit": cb.net_benefit,
                "n_approve": cb.n_approve,
                "n_review": cb.n_review,
                "n_block": cb.n_block,
                # A threshold chosen on validation can land outside the range
                # the test scores actually occupy. When that happens the point
                # is not "high precision", it is inactive, and saying so is the
                # difference between an honest report and a flattering one.
                "transfers": bool(bm.alert_rate >= 0.005),
                "transfer_note": (
                    ""
                    if bm.alert_rate >= 0.005
                    else (
                        f"threshold {blk:.4f} sits above almost the entire test "
                        f"score range; only {bm.n_predicted_positive} of "
                        f"{int(te.sum())} transactions reach it, so this "
                        "operating point does not transfer across the observed "
                        "score drift"
                    )
                ),
            }
        )
    out["operating_points_test"] = operating

    # cost curve
    sweep = cost_sweep(
        ds.y[te], p_all[te], amounts[te],
        cost=cfg.cost, review_band_frac=cfg.decision.review_band_frac,
    )
    out["cost_sweep_test"] = sweep.to_dict(orient="records")

    # calibration
    out["calibration_test"] = calibration_table(
        ds.y[te], p_all[te]
    ).to_dict(orient="records")

    # score drift
    # Measured, not assumed: the calibrator and every threshold were fitted on
    # validation, so how far the test score distribution has moved from it is
    # a precondition for trusting either.
    out["score_drift"] = drift_report(p_all[masks["val"]], p_all[masks["test"]])

    # cold-entity stress slice
    cold = _cold_entity_mask(ds) & te
    warm = (~_cold_entity_mask(ds)) & te
    slices = []
    for label, m in (("cold_entities", cold), ("warm_entities", warm)):
        if m.sum() < 20 or len(np.unique(ds.y[m])) < 2:
            slices.append({"slice": label, "n": int(m.sum()), "note": "too few rows"})
            continue
        r = ranking_metrics(ds.y[m], p_all[m])
        blk = meta["thresholds"]["balanced"]["block_threshold"]
        bm = binary_metrics(ds.y[m], p_all[m], blk)
        slices.append({"slice": label, **r.as_dict(), **bm.as_dict()})
    out["stress_slices_test"] = slices

    # ring detector
    rings = annotate_with_labels(
        detect_rings(ds.df, cfg=cfg, txn_risk=p_all, verbose=False),
        ds.y, ds.labeled,
    )
    out["rings"] = _evaluate_rings(rings, ds, masks)

    # write
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    with open(report_dir / "evaluation.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, default=float)

    if verbose:
        print_report(out)
        print(f"\n[evaluate] written to {report_dir / 'evaluation.json'}")

    return out


def _evaluate_rings(rings, ds, masks) -> dict:
    """
    Evaluate the label-free ring detector.

    The alert threshold is chosen on the validation window and then applied to
    the test window, exactly as the transaction thresholds are. Choosing it on
    test would make the ring numbers self-fulfilling.
    """
    val_time = (ds.splits.val_end_time, ds.splits.train_end_time)
    y, labeled = ds.y, ds.labeled

    def _slice(rs, lo, hi):
        keep = []
        for r in rs:
            idx = np.asarray(r.txn_indices, dtype=int)
            t = ds.df["Time"].to_numpy()[idx]
            inside = (t > lo) & (t <= hi)
            if inside.sum() == 0:
                continue
            keep.append((r, idx[inside]))
        return keep

    def _stats(pairs, threshold):
        """
        Coverage of the alerted rings, deduplicated by transaction.

        Windows overlap on purpose, so a ring that crosses a window edge is
        found from either side. That means the same transaction can appear
        in several rings. Summing per-ring counts therefore double-counts it, and
        produced a reported recall above 1.0 before this was fixed. Union the
        transaction indices first, then count once.
        """
        rings_hit = 0
        covered: set = set()
        for r, idx in pairs:
            if r.risk_score < threshold:
                continue
            rings_hit += 1
            covered.update(int(i) for i in idx)
        if not covered:
            return rings_hit, 0, 0
        arr = np.fromiter(covered, dtype=int, count=len(covered))
        lab = arr[labeled[arr]]
        return rings_hit, int(len(lab)), int(y[lab].sum())

    # Candidate thresholds are evaluated on validation only, and selected on
    # F1 rather than precision. Maximising precision alone walks the threshold
    # into the extreme tail. Measured here it picked 0.75, where two rings
    # survive at 97% precision and cover almost no traffic. A ring detector
    # that alerts on nothing is not precise, it is switched off.
    val_lo, val_hi = ds.splits.train_end_time, ds.splits.val_end_time
    val_pairs = _slice(rings, val_lo, val_hi)
    t_all = ds.df["Time"].to_numpy()
    val_window = (t_all > val_lo) & (t_all <= val_hi) & labeled
    val_fraud_total = int(y[val_window].sum())

    grid = np.round(np.arange(0.40, 0.86, 0.025), 3)
    best_t, best_f1 = None, -1.0
    val_rows = []
    for t in grid:
        n_r, lab_n, fr_n = _stats(val_pairs, t)
        prec = fr_n / lab_n if lab_n else 0.0
        rec = fr_n / val_fraud_total if val_fraud_total else 0.0
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0
        val_rows.append(
            {"threshold": float(t), "rings": n_r, "confirmed": lab_n,
             "fraud": fr_n, "precision": prec, "recall": rec, "f1": f1}
        )
        # Require a minimum evidence base so a threshold is never chosen on a
        # handful of transactions that happen to be all fraud.
        if lab_n >= 100 and f1 > best_f1:
            best_f1, best_t = f1, float(t)
    if best_t is None:
        best_t = 0.60

    test_pairs = _slice(rings, ds.splits.val_end_time, int(ds.df["Time"].max()))
    n_r, lab_n, fr_n = _stats(test_pairs, best_t)
    te = masks["test"]
    total_test_fraud = int(y[te].sum())
    base = float(y[te].mean()) if te.any() else 0.0

    return {
        "n_candidate_rings": len(rings),
        "threshold_selected_on_validation": best_t,
        "validation_sweep": val_rows,
        "test": {
            "rings_alerted": n_r,
            "confirmed_transactions_covered": lab_n,
            "confirmed_fraud_captured": fr_n,
            "precision": (fr_n / lab_n) if lab_n else None,
            "recall_of_test_fraud": (
                fr_n / total_test_fraud if total_test_fraud else None
            ),
            "test_base_rate": base,
            "lift_over_base": ((fr_n / lab_n) / base) if lab_n and base else None,
        },
        "top_rings": [
            {
                "cluster_id": r.cluster_id,
                "n_accounts": r.n_accounts,
                "n_transactions": r.n_transactions,
                "merchants": r.merchants[:3],
                "channels": r.channels[:3],
                "risk_score": round(r.risk_score, 4),
                "precision": r.precision,
                "reasons": r.reasons[:3],
            }
            for r in rings[:10]
        ],
    }


def print_report(out: dict) -> None:
    """Human-readable rendering of the evaluation, for the CLI."""
    bar = "=" * 74
    print(f"\n{bar}\nHELD-OUT EVALUATION  -  {out['model_version']}\n{bar}")
    print(f"chargeback label lag: {out['label_lag_steps']} time units")
    print(f"fusion weights: " + ", ".join(
        f"{k}={v:.3f}" for k, v in out["fusion_weights"].items()
    ))

    print("\nranking quality by split")
    df = pd.DataFrame(out["ranking_by_split"])[
        ["split", "n", "n_positive", "base_rate", "pr_auc", "roc_auc", "brier"]
    ]
    print(df.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    print("\nPR-AUC by channel")
    print(pd.DataFrame(out["ranking_by_channel"]).to_string(
        index=False, float_format=lambda v: f"{v:.4f}"
    ))

    print("\noperating points (thresholds chosen on VALIDATION)")
    op = pd.DataFrame(out["operating_points_test"])
    print(op[["mode", "block_threshold", "precision", "recall", "f1",
              "fpr", "fnr", "tp", "fp", "fn"]].to_string(
        index=False, float_format=lambda v: f"{v:.4f}"
    ))
    for row in out["operating_points_test"]:
        if not row["transfers"]:
            print(f"  ! {row['mode']}: {row['transfer_note']}")

    print("\nbusiness cost on held-out test")
    print(op[["mode", "n_approve", "n_review", "n_block", "expected_cost",
              "cost_per_1k", "prevented_loss", "net_benefit"]].to_string(
        index=False, float_format=lambda v: f"{v:,.2f}"
    ))

    print("\ncalibration (held-out test)")
    print(pd.DataFrame(out["calibration_test"]).to_string(
        index=False, float_format=lambda v: f"{v:.4f}"
    ))

    d = out["score_drift"]
    print("\nscore drift, validation -> test")
    print(f"PSI {d['psi']}  ({d['status']})")
    print(f"  mean {d['reference_mean']} -> {d['current_mean']}    "
          f"max {d['reference_max']} -> {d['current_max']}")
    print(f"  {d['implication']}")

    print("\nstress slices (held-out test)")
    sl = pd.DataFrame(out["stress_slices_test"])
    cols = [c for c in ["slice", "n", "base_rate", "pr_auc", "roc_auc",
                        "precision", "recall", "note"] if c in sl.columns]
    print(sl[cols].to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    r = out["rings"]
    print("\nabuse-ring detector (label-free)")
    print(f"candidate rings: {r['n_candidate_rings']}")
    print(f"alert threshold {r['threshold_selected_on_validation']} "
          f"(selected on validation)")
    t = r["test"]
    if t["precision"] is not None:
        print(f"held-out test: {t['rings_alerted']} rings alerted, "
              f"{t['confirmed_transactions_covered']:,} confirmed transactions")
        print(f"  precision {t['precision']:.4f}  "
              f"recall {t['recall_of_test_fraud']:.4f}  "
              f"lift {t['lift_over_base']:.2f}x over base rate "
              f"{t['test_base_rate']:.4f}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Evaluate on the held-out test set.")
    ap.add_argument("--artifacts", default=str(ARTIFACT_DIR))
    ap.add_argument("--reports", default=str(REPORT_DIR))
    ap.add_argument("--json", action="store_true", help="print raw JSON")
    args = ap.parse_args(argv)
    out = evaluate(
        artifact_dir=Path(args.artifacts),
        report_dir=Path(args.reports),
        verbose=not args.json,
    )
    if args.json:
        print(json.dumps(out, indent=2, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

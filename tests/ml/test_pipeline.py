"""
End to end tests against the real dataset and saved models.

These catch things a unit test cannot see: a split that stopped being time
ordered, a scoring engine that disagrees with the evaluation, a CLI that no
longer runs. They skip when the dataset or artifacts are missing.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.config import ARTIFACT_DIR

pytestmark = pytest.mark.slow


def _need_raw(raw_available):
    if not raw_available:
        pytest.skip("dataset not downloaded; run python -m spark.data.fetch")


def _need_artifacts(artifacts_available):
    if not artifacts_available:
        pytest.skip("no trained model; run python -m spark.models.train")


class TestPreparedDataset:
    def test_prepare_is_consistent(self, raw_available):
        _need_raw(raw_available)
        from ml.preprocessing.prepare import prepare

        ds = prepare(verbose=False)
        assert len(ds.base) == len(ds.df)
        assert len(ds.risk) == len(ds.df)
        assert ds.labeled.sum() > 0
        assert ds.y[~ds.labeled].sum() == 0, "unlabeled rows must not count as fraud"

    def test_cache_round_trips(self, raw_available):
        _need_raw(raw_available)
        from ml.preprocessing.prepare import prepare

        a = prepare(verbose=False)
        b = prepare(verbose=False)
        assert a.fingerprint == b.fingerprint
        pd.testing.assert_frame_equal(a.base, b.base)

    def test_splits_do_not_overlap_in_time(self, raw_available):
        _need_raw(raw_available)
        from ml.preprocessing.prepare import prepare

        ds = prepare(verbose=False)
        t = ds.df["Time"].to_numpy()
        assert t[ds.splits.train].max() < t[ds.splits.val].min()
        assert t[ds.splits.val].max() < t[ds.splits.test].min()

    def test_every_split_has_both_classes(self, raw_available):
        _need_raw(raw_available)
        from ml.preprocessing.prepare import prepare

        ds = prepare(verbose=False)
        for name in ("train", "val", "test"):
            y = ds.y[ds.mask(name)]
            assert set(np.unique(y)) == {0, 1}, f"{name} split is single-class"


class TestArtifacts:
    def test_metadata_is_complete(self, artifacts_available):
        _need_artifacts(artifacts_available)
        meta = json.loads(
            (Path(ARTIFACT_DIR) / "model_metadata.json").read_text(encoding="utf-8")
        )
        for key in (
            "model_version", "created_utc", "seed", "config", "fusion_weights",
            "thresholds", "tabular_features", "graph_features", "raw_sha256",
            "dataset", "timings_seconds",
        ):
            assert key in meta, f"metadata is missing {key}"

    def test_all_artifacts_present(self, artifacts_available):
        _need_artifacts(artifacts_available)
        for name in (
            "tabular_model.joblib", "graph_model.pt", "fusion.joblib",
            "channels.joblib", "rings.json", "ring_membership.json",
            "model_metadata.json",
        ):
            assert (Path(ARTIFACT_DIR) / name).exists(), f"missing artifact {name}"

    def test_thresholds_were_selected_on_validation(self, artifacts_available):
        _need_artifacts(artifacts_available)
        meta = json.loads(
            (Path(ARTIFACT_DIR) / "model_metadata.json").read_text(encoding="utf-8")
        )
        for name, op in meta["thresholds"].items():
            assert op["selected_on"] == "validation", (
                f"{name} threshold was not selected on validation"
            )
            assert op["review_threshold"] <= op["block_threshold"]


class TestScoringEngine:
    def test_scores_are_probabilities(self, artifacts_available, raw_available):
        _need_raw(raw_available)
        _need_artifacts(artifacts_available)
        from spark.risk.engine import ScoringEngine

        eng = ScoringEngine(with_explainer=False)
        idx = np.where(eng.ds.mask("test"))[0][:300]
        batch = eng.score_batch(idx)
        p = batch["risk_score"].to_numpy()
        assert (p >= 0).all() and (p <= 1).all()
        assert set(batch["decision"]).issubset({"APPROVE", "REVIEW", "BLOCK"})

    def test_scoring_is_deterministic(self, artifacts_available, raw_available):
        _need_raw(raw_available)
        _need_artifacts(artifacts_available)
        from spark.risk.engine import ScoringEngine

        eng = ScoringEngine(with_explainer=False)
        idx = np.where(eng.ds.mask("test"))[0][:200]
        a = eng.score_batch(idx)["risk_score"].to_numpy()
        b = eng.score_batch(idx)["risk_score"].to_numpy()
        np.testing.assert_array_equal(a, b)

    def test_single_and_batch_scores_agree(self, artifacts_available, raw_available):
        """
        One transaction scored alone must get the same number as when it is
        scored in a batch. A mismatch would mean the demo and the evaluation
        are reporting different systems.
        """
        _need_raw(raw_available)
        _need_artifacts(artifacts_available)
        from spark.risk.engine import ScoringEngine

        eng = ScoringEngine(with_explainer=False)
        idx = np.where(eng.ds.mask("test"))[0][:25]
        batch = eng.score_batch(idx).set_index("index")["risk_score"]
        for i in idx[:10]:
            d = eng.score_one(int(i), explain=False)
            assert d.risk_score == pytest.approx(float(batch.loc[i]), abs=1e-9)

    def test_decisions_follow_the_thresholds(self, artifacts_available, raw_available):
        _need_raw(raw_available)
        _need_artifacts(artifacts_available)
        from spark.risk.engine import ScoringEngine

        eng = ScoringEngine(with_explainer=False)
        idx = np.where(eng.ds.mask("test"))[0][:500]
        b = eng.score_batch(idx)
        for _, r in b.iterrows():
            if r["risk_score"] >= eng.block_threshold:
                assert r["decision"] == "BLOCK"
            elif r["risk_score"] >= eng.review_threshold:
                assert r["decision"] == "REVIEW"
            else:
                assert r["decision"] == "APPROVE"

    def test_explanations_are_produced(self, artifacts_available, raw_available):
        _need_raw(raw_available)
        _need_artifacts(artifacts_available)
        from spark.risk.engine import ScoringEngine

        eng = ScoringEngine()
        idx = int(np.where(eng.ds.mask("test"))[0][0])
        d = eng.score_one(idx, explain=True)
        assert d.reasons, "every decision must carry a reason"
        assert d.channel_scores
        assert d.latency_ms is not None

    def test_explanations_avoid_causal_language(self, artifacts_available,
                                                raw_available):
        """Reasons describe contribution to a score, never proven causation."""
        _need_raw(raw_available)
        _need_artifacts(artifacts_available)
        from spark.risk.engine import ScoringEngine

        eng = ScoringEngine()
        idx = np.where(eng.ds.mask("test"))[0][:20]
        banned = ("caused", "proves", "because the customer is", "guilty")
        for i in idx:
            for r in eng.score_one(int(i)).reasons:
                low = r.lower()
                for word in banned:
                    assert word not in low, f"causal language in reason: {r}"

    def test_unknown_mode_raises(self, artifacts_available, raw_available):
        _need_raw(raw_available)
        _need_artifacts(artifacts_available)
        from spark.risk.engine import ScoringEngine

        with pytest.raises(ValueError, match="unknown mode"):
            ScoringEngine(mode="does_not_exist", with_explainer=False)


class TestAuditLog:
    def test_append_and_read(self, tmp_path):
        from spark.risk.audit import AuditLog

        log = AuditLog(tmp_path / "d.jsonl")
        log.record({"transaction_id": "t1", "decision": "BLOCK", "risk_score": 0.9})
        log.record({"transaction_id": "t2", "decision": "APPROVE", "risk_score": 0.1})
        rows = log.read()
        assert len(rows) == 2
        assert rows[0]["transaction_id"] == "t2"  # most recent first

    def test_filter_by_transaction(self, tmp_path):
        from spark.risk.audit import AuditLog

        log = AuditLog(tmp_path / "d.jsonl")
        log.record({"transaction_id": "t1", "decision": "BLOCK"})
        log.record({"transaction_id": "t2", "decision": "APPROVE"})
        assert len(log.read(transaction_id="t1")) == 1

    def test_is_append_only(self, tmp_path):
        from spark.risk.audit import AuditLog

        log = AuditLog(tmp_path / "d.jsonl")
        log.record({"transaction_id": "t1", "decision": "BLOCK"})
        first = (tmp_path / "d.jsonl").read_text(encoding="utf-8")
        log.record({"transaction_id": "t2", "decision": "APPROVE"})
        second = (tmp_path / "d.jsonl").read_text(encoding="utf-8")
        assert second.startswith(first), "existing entries must never be rewritten"

    def test_truncated_line_does_not_lose_the_rest(self, tmp_path):
        from spark.risk.audit import AuditLog

        path = tmp_path / "d.jsonl"
        log = AuditLog(path)
        log.record({"transaction_id": "t1", "decision": "BLOCK"})
        with open(path, "a", encoding="utf-8") as fh:
            fh.write('{"broken": ')
        assert len(log.read()) == 1

    def test_stats(self, tmp_path):
        from spark.risk.audit import AuditLog

        log = AuditLog(tmp_path / "d.jsonl")
        for d in ("APPROVE", "APPROVE", "BLOCK"):
            log.record({"transaction_id": "x", "decision": d, "risk_score": 0.5})
        s = log.stats()
        assert s["total"] == 3
        assert s["approve"] == 2
        assert s["block"] == 1


class TestEvaluationIntegrity:
    def test_reported_metrics_reproduce(self, artifacts_available, raw_available):
        """Re-running the evaluation must produce the same numbers."""
        _need_raw(raw_available)
        _need_artifacts(artifacts_available)
        from ml.evaluation.evaluate import evaluate

        a = evaluate(verbose=False)
        b = evaluate(verbose=False)
        ta = next(r for r in a["ranking_by_split"] if r["split"] == "test")
        tb = next(r for r in b["ranking_by_split"] if r["split"] == "test")
        assert ta["pr_auc"] == pytest.approx(tb["pr_auc"])
        assert ta["roc_auc"] == pytest.approx(tb["roc_auc"])

    def test_test_metrics_are_not_suspiciously_perfect(self, artifacts_available,
                                                       raw_available):
        """
        A guard against accidental leakage.

        A held-out PR-AUC of 1.0 on a drifting real-world stream means a bug,
        not a breakthrough. If this ever trips, the split or the features have
        started seeing the future.
        """
        _need_raw(raw_available)
        _need_artifacts(artifacts_available)
        from ml.evaluation.evaluate import evaluate

        ev = evaluate(verbose=False)
        t = next(r for r in ev["ranking_by_split"] if r["split"] == "test")
        assert t["pr_auc"] < 0.999, "held-out PR-AUC of ~1.0 indicates leakage"
        assert t["roc_auc"] < 0.999

    def test_ring_recall_cannot_exceed_one(self, artifacts_available, raw_available):
        _need_raw(raw_available)
        _need_artifacts(artifacts_available)
        from ml.evaluation.evaluate import evaluate

        rt = evaluate(verbose=False)["rings"]["test"]
        if rt["recall_of_test_fraud"] is not None:
            assert 0.0 <= rt["recall_of_test_fraud"] <= 1.0
        if rt["precision"] is not None:
            assert 0.0 <= rt["precision"] <= 1.0


class TestCLI:
    """Every documented command must actually run."""

    @pytest.mark.parametrize(
        "cmd",
        [
            ["-m", "spark.data.inspect"],
            ["-m", "spark.data.prepare"],
            ["-m", "spark.features.build"],
        ],
    )
    def test_data_commands_run(self, cmd, raw_available):
        _need_raw(raw_available)
        r = subprocess.run([sys.executable, *cmd], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-2000:]

    @pytest.mark.parametrize(
        "cmd",
        [
            ["-m", "spark.models.evaluate"],
            ["-m", "spark.risk.score", "--split", "test", "--limit", "2",
             "--no-audit"],
            ["-m", "spark.clusters.detect", "--top", "3", "--from-artifacts"],
        ],
    )
    def test_model_commands_run(self, cmd, raw_available, artifacts_available):
        _need_raw(raw_available)
        _need_artifacts(artifacts_available)
        r = subprocess.run([sys.executable, *cmd], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-2000:]

    def test_demo_runs(self, raw_available, artifacts_available):
        _need_raw(raw_available)
        _need_artifacts(artifacts_available)
        r = subprocess.run(
            [sys.executable, "-m", "spark.demo", "--examples", "1", "--bench", "20"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr[-3000:]
        assert "HELD-OUT TEST RESULTS" in r.stdout
        assert "PR-AUC" in r.stdout

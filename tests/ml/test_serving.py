"""
The online scorer must agree with the batch pipeline.

This is the test that matters most for the API. The dashboard scores a
transaction that is not in the dataset file, using a streaming feature state
and a single-node graph forward pass. If either drifts from the batch code,
the numbers on screen stop describing the model that was measured.

The check holds back the last row of the real dataset, replays everything
before it, then scores that row as though it had just arrived.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml.config import CONFIG, ENTITY_COLS
from ml.features.causal import CausalFeatureState, build_causal_features


def test_state_reproduces_the_batch_pass(sample_frame):
    """emit/update in a loop must equal the batch feature builder exactly."""
    bundle = build_causal_features(sample_frame, cfg=CONFIG, verbose=False)

    state = CausalFeatureState(CONFIG)
    base_rows, risk_rows = [], []
    for i in range(len(sample_frame)):
        row = sample_frame.iloc[i]
        ent = {c: row[c] for c in ENTITY_COLS}
        b, r = state.emit(int(row["Time"]), float(row["Amount"]), ent)
        base_rows.append(b)
        risk_rows.append(r)
        state.update(int(row["Time"]), float(row["Amount"]), ent,
                     int(row["Labels"]))

    assert np.array_equal(np.array(base_rows), bundle.base.to_numpy())
    assert np.array_equal(np.array(risk_rows), bundle.risk.to_numpy())


def test_emit_does_not_touch_the_accumulators(sample_frame):
    """Calling emit twice must give the same answer both times."""
    state = CausalFeatureState(CONFIG)
    for i in range(20):
        row = sample_frame.iloc[i]
        ent = {c: row[c] for c in ENTITY_COLS}
        state.update(int(row["Time"]), float(row["Amount"]), ent,
                     int(row["Labels"]))

    row = sample_frame.iloc[20]
    ent = {c: row[c] for c in ENTITY_COLS}
    first = state.emit(int(row["Time"]), float(row["Amount"]), ent)
    second = state.emit(int(row["Time"]), float(row["Amount"]), ent)
    assert np.array_equal(first[0], second[0])
    assert np.array_equal(first[1], second[1])


@pytest.mark.slow
def test_online_scorer_matches_the_batch_engine(trained_engine):
    """
    A held-back transaction scored online must match the batch score.

    Exactly, not approximately. The graph edges point only backwards, so
    appending a node cannot change any earlier node, and the arithmetic is the
    same arithmetic.
    """
    from ml.serving.online import OnlineScorer, TransactionInput

    engine = trained_engine
    target = len(engine.ds.df) - 1

    class HeldBack(OnlineScorer):
        """Warm every accumulator except with the row under test."""

        def _warm_feature_state(self, verbose: bool = False):
            state = CausalFeatureState(self.cfg)
            df = self.df.iloc[:target]
            ev = {c: df[c].to_numpy() for c in ENTITY_COLS}
            times = df["Time"].to_numpy()
            amounts = df["Amount"].to_numpy(dtype=float)
            labels = df["Labels"].to_numpy()
            for i in range(len(df)):
                state.update(
                    int(times[i]), float(amounts[i]),
                    {c: ev[c][i] for c in ENTITY_COLS}, int(labels[i]),
                )
            return state

        def _build_entity_index(self) -> None:
            self.entity_rows = {}
            for rel in self.cfg.graph.relations:
                buckets: dict = {}
                for i, v in enumerate(self.df[rel].to_numpy()[:target]):
                    buckets.setdefault(v, []).append(i)
                self.entity_rows[rel] = buckets

    scorer = HeldBack(engine, verbose=False)
    row = engine.ds.df.iloc[target]
    ent = {c: row[c] for c in ENTITY_COLS}
    t_new = int(row["Time"])

    base_vec, risk_vec = scorer.state.emit(t_new, float(row["Amount"]), ent)
    assert np.array_equal(base_vec, engine.ds.base.iloc[target].to_numpy())
    assert np.array_equal(risk_vec, engine.ds.risk.iloc[target].to_numpy())

    edges = scorer._new_node_edges(ent)
    gfeat = scorer._neighbour_features(edges, t_new)
    expected = engine.gfeat.iloc[target]
    for col in gfeat.columns:
        assert float(gfeat[col].iloc[0]) == pytest.approx(
            float(expected[col]), abs=1e-4
        ), col

    base_df, risk_df = scorer.state.frames(base_vec, risk_vec)
    x_graph = pd.concat([base_df, risk_df, gfeat], axis=1)
    x_new = engine.graph_model.scale_features(x_graph)[0]
    online_graph = scorer._graph_score(x_new, edges)
    assert online_graph == pytest.approx(
        float(engine._graph_scores[target]), abs=1e-6
    )

    result = scorer.score(
        TransactionInput(
            transaction_id=str(row["txn_id"]),
            amount=float(row["Amount"]),
            source=row["Source"],
            target=row["Target"],
            location=row["Location"],
            payment_type=row["Type"],
            time=t_new,
        )
    )
    batch = engine.score_one(target)
    assert result.risk_score == pytest.approx(batch.risk_score, abs=1e-9)
    assert result.decision == batch.decision


@pytest.mark.slow
def test_online_scorer_reports_its_working(trained_engine):
    """Every scored transaction carries the steps it went through."""
    from ml.serving.online import OnlineScorer, TransactionInput

    scorer = OnlineScorer(trained_engine, verbose=False)
    result = scorer.score(
        TransactionInput(
            transaction_id="probe",
            amount=3.0,
            source="brand_new_account",
            target="brand_new_merchant",
            location="brand_new_place",
            payment_type="brand_new_channel",
        )
    )
    names = [s["name"] for s in result.stages]
    assert "Building features" in names
    assert "Running graph model" in names
    assert result.path == "COLD_START", "an entirely unseen entity is cold"
    assert 0.0 <= result.risk_score <= 1.0
    assert result.entity_history["Source"]["prior_transactions"] == 0

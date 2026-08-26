"""
Tests for the graph, neighbour features, and ring detection.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml.config import CONFIG
from ml.graph.build import build_relation_graph, neighbour_risk_features
from ml.graph.rings import (
    annotate_with_labels,
    detect_rings,
    transaction_to_cluster,
)


class TestRelationGraph:
    def test_edges_point_backwards_in_time(self, tiny_df):
        """
        No edge may carry information from a later transaction to an earlier
        one. This is what makes the graph model usable on a time-ordered
        holdout, so it is asserted for every edge in every relation.
        """
        g = build_relation_graph(tiny_df, verbose=False)
        times = tiny_df["Time"].to_numpy()
        for rel, adj in g.adj.items():
            coo = adj.tocoo()
            receiver_t = times[coo.row]
            sender_t = times[coo.col]
            assert (sender_t <= receiver_t).all(), (
                f"relation {rel} has an edge from the future"
            )

    def test_no_self_loops(self, tiny_df):
        g = build_relation_graph(tiny_df, verbose=False)
        for rel, adj in g.adj.items():
            coo = adj.tocoo()
            assert not (coo.row == coo.col).any(), f"{rel} has a self loop"

    def test_edges_only_join_matching_entity_values(self, tiny_df):
        """The graph must never invent a relationship the data does not have."""
        g = build_relation_graph(tiny_df, verbose=False)
        for rel, adj in g.adj.items():
            values = tiny_df[rel].to_numpy()
            coo = adj.tocoo()
            assert (values[coo.row] == values[coo.col]).all(), (
                f"{rel} links transactions that do not share that entity"
            )

    def test_in_degree_respects_k(self, tiny_df):
        g = build_relation_graph(tiny_df, verbose=False)
        k = CONFIG.graph.edges_per_transaction
        for adj in g.adj.values():
            deg = np.asarray(adj.sum(axis=1)).ravel()
            assert deg.max() <= k

    def test_normalised_rows_sum_to_one_or_zero(self, tiny_df):
        g = build_relation_graph(tiny_df, verbose=False)
        for adj in g.normalised().values():
            sums = np.asarray(adj.sum(axis=1)).ravel()
            for s in sums:
                assert s == pytest.approx(0.0) or s == pytest.approx(1.0)

    def test_lagged_adjacency_is_a_subset(self, tiny_df):
        g = build_relation_graph(tiny_df, verbose=False)
        full = g.lagged(0)
        lagged = g.lagged(5)
        for rel in g.relations:
            assert lagged[rel].nnz <= full[rel].nnz

    def test_lagged_adjacency_respects_the_delay(self, tiny_df):
        g = build_relation_graph(tiny_df, verbose=False)
        lag = 5
        times = tiny_df["Time"].to_numpy()
        for rel, adj in g.lagged(lag).items():
            coo = adj.tocoo()
            if coo.nnz:
                assert (times[coo.row] - times[coo.col] >= lag).all()

    def test_deterministic(self, tiny_df):
        a = build_relation_graph(tiny_df, verbose=False)
        b = build_relation_graph(tiny_df, verbose=False)
        for rel in a.relations:
            assert (a.adj[rel] != b.adj[rel]).nnz == 0


class TestNeighbourRiskFeatures:
    def test_unlabeled_neighbours_are_not_counted(self, tiny_df):
        g = build_relation_graph(tiny_df, verbose=False)
        y = np.where(tiny_df["Labels"].to_numpy() == 1, 1, 0)
        none_known = np.zeros(len(tiny_df), dtype=bool)
        nf = neighbour_risk_features(g, y, none_known, verbose=False)
        fraud_cols = [c for c in nf.columns if "fraud" in c]
        assert nf[fraud_cols].to_numpy().sum() == 0.0

    def test_degree_is_independent_of_labels(self, tiny_df):
        g = build_relation_graph(tiny_df, verbose=False)
        y = np.where(tiny_df["Labels"].to_numpy() == 1, 1, 0)
        labeled = tiny_df["Labels"].to_numpy() != 2
        a = neighbour_risk_features(g, y, labeled, verbose=False)
        b = neighbour_risk_features(g, np.zeros_like(y), labeled, verbose=False)
        deg_cols = [c for c in a.columns if "deg" in c]
        pd.testing.assert_frame_equal(a[deg_cols], b[deg_cols])

    def test_fraud_share_is_bounded(self, tiny_df):
        g = build_relation_graph(tiny_df, verbose=False)
        y = np.where(tiny_df["Labels"].to_numpy() == 1, 1, 0)
        labeled = tiny_df["Labels"].to_numpy() != 2
        nf = neighbour_risk_features(g, y, labeled, verbose=False)
        share = nf[[c for c in nf.columns if c.endswith("_fraud_share1")]]
        assert (share.to_numpy() >= 0).all()
        assert (share.to_numpy() <= 1).all()

    def test_no_nan_or_inf(self, tiny_df):
        g = build_relation_graph(tiny_df, verbose=False)
        y = np.where(tiny_df["Labels"].to_numpy() == 1, 1, 0)
        labeled = tiny_df["Labels"].to_numpy() != 2
        nf = neighbour_risk_features(g, y, labeled, verbose=False)
        assert not np.isnan(nf.to_numpy()).any()
        assert not np.isinf(nf.to_numpy()).any()


class TestRingDetection:
    def test_detection_reads_no_labels(self, tiny_df):
        """
        Ring detection must be label-blind.

        Detecting on the frame, then on a copy with every label destroyed, must
        produce identical rings. This is the property that lets the detector
        work on an attack before any chargeback has been filed.
        """
        cfg = CONFIG
        a = detect_rings(tiny_df, cfg=cfg, verbose=False)
        scrambled = tiny_df.copy()
        scrambled["Labels"] = 2
        b = detect_rings(scrambled, cfg=cfg, verbose=False)
        assert [r.cluster_id for r in a] == [r.cluster_id for r in b]
        assert [round(r.risk_score, 10) for r in a] == [
            round(r.risk_score, 10) for r in b
        ]

    def test_signature_components_are_bounded(self, tiny_df):
        for r in detect_rings(tiny_df, verbose=False):
            for v in (
                r.fan_in,
                r.single_use_rate,
                r.temporal_density,
                r.amount_homogeneity,
                r.small_amount_score,
                r.risk_score,
                r.confidence,
            ):
                assert 0.0 <= v <= 1.0

    def test_every_ring_has_a_reason(self, tiny_df):
        for r in detect_rings(tiny_df, verbose=False):
            assert r.reasons, f"{r.cluster_id} has no stated reason"

    def test_planted_ring_is_found(self, tiny_df):
        """The synthetic ring in the fixture must be detected."""
        rings = detect_rings(tiny_df, verbose=False)
        assert rings, "no rings detected at all"
        found = [r for r in rings if "T900" in r.merchants]
        assert found, "the planted T900 ring was not detected"
        best = max(found, key=lambda r: r.risk_score)
        # Single-use accounts converging on one merchant and channel.
        assert best.fan_in > 0.9
        assert best.single_use_rate > 0.9

    def test_annotation_does_not_change_detection(self, tiny_df):
        y = np.where(tiny_df["Labels"].to_numpy() == 1, 1, 0)
        labeled = tiny_df["Labels"].to_numpy() != 2
        rings = detect_rings(tiny_df, verbose=False)
        scores_before = [r.risk_score for r in rings]
        annotate_with_labels(rings, y, labeled)
        assert [r.risk_score for r in rings] == scores_before
        for r in rings:
            assert r.confirmed_labeled is not None

    def test_transaction_to_cluster_maps_members(self, tiny_df):
        rings = detect_rings(tiny_df, verbose=False)
        mapping = transaction_to_cluster(rings)
        for r in rings:
            for i in r.txn_indices:
                assert i in mapping

    def test_deterministic(self, tiny_df):
        a = detect_rings(tiny_df, verbose=False)
        b = detect_rings(tiny_df, verbose=False)
        assert [r.cluster_id for r in a] == [r.cluster_id for r in b]

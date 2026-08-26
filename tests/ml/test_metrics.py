"""
Tests for metrics, cost, decisions, thresholds, fusion, and drift.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from ml.calibration.fuse import CHANNELS, calibration_table, fit_fusion
from ml.config import CONFIG, CostConfig
from ml.evaluation.drift import (
    MONITOR,
    SHIFTED,
    STABLE,
    classify,
    drift_report,
    population_stability_index,
)
from ml.evaluation.metrics import (
    APPROVE,
    BLOCK,
    REVIEW,
    binary_metrics,
    choose_thresholds,
    cost_sweep,
    decide,
    expected_cost,
    ranking_metrics,
)


class TestRankingMetrics:
    def test_perfect_ranking(self):
        y = np.array([0, 0, 1, 1])
        s = np.array([0.1, 0.2, 0.8, 0.9])
        m = ranking_metrics(y, s)
        assert m.roc_auc == pytest.approx(1.0)
        assert m.pr_auc == pytest.approx(1.0)

    def test_single_class_returns_nan_not_zero(self):
        # Silently returning 0.0 would look like a terrible model rather than
        # an undefined metric.
        m = ranking_metrics(np.zeros(10, dtype=int), np.random.rand(10))
        assert np.isnan(m.roc_auc)
        assert np.isnan(m.pr_auc)

    def test_base_rate(self):
        m = ranking_metrics(np.array([0, 0, 0, 1]), np.array([0.1, 0.2, 0.3, 0.9]))
        assert m.base_rate == pytest.approx(0.25)


class TestBinaryMetrics:
    def test_confusion_matrix(self):
        y = np.array([1, 1, 0, 0])
        s = np.array([0.9, 0.2, 0.8, 0.1])
        m = binary_metrics(y, s, 0.5)
        assert (m.tp, m.fp, m.fn, m.tn) == (1, 1, 1, 1)
        assert m.precision == pytest.approx(0.5)
        assert m.recall == pytest.approx(0.5)
        assert m.f1 == pytest.approx(0.5)
        assert m.fpr == pytest.approx(0.5)
        assert m.fnr == pytest.approx(0.5)

    def test_counts_sum_to_n(self):
        rng = np.random.default_rng(0)
        y = rng.integers(0, 2, 200)
        s = rng.random(200)
        m = binary_metrics(y, s, 0.5)
        assert m.tp + m.fp + m.fn + m.tn == 200

    def test_no_alerts_is_reported_not_hidden(self):
        y = np.array([1, 0, 1, 0])
        s = np.array([0.1, 0.1, 0.2, 0.1])
        m = binary_metrics(y, s, 0.99)
        assert m.n_predicted_positive == 0
        assert m.alert_rate == 0.0


class TestDecisions:
    def test_three_way_routing(self):
        s = np.array([0.05, 0.3, 0.9])
        d = decide(s, 0.2, 0.6)
        assert list(d) == [APPROVE, REVIEW, BLOCK]

    def test_boundaries_are_inclusive_at_the_lower_edge(self):
        d = decide(np.array([0.2, 0.6]), 0.2, 0.6)
        assert list(d) == [REVIEW, BLOCK]

    def test_inverted_thresholds_raise(self):
        with pytest.raises(ValueError, match="must not exceed"):
            decide(np.array([0.5]), 0.9, 0.1)


class TestCostModel:
    def _cost(self, **kw) -> CostConfig:
        return dataclasses.replace(CONFIG.cost, **kw)

    def test_amount_weighted_fraud_costs_more_for_bigger_tickets(self):
        y = np.array([1, 1])
        s = np.array([0.0, 0.0])          # both approved
        small = expected_cost(y, s, np.array([10.0, 10.0]), 0.5, 0.9,
                              self._cost(amount_weighted=True))
        large = expected_cost(y, s, np.array([1000.0, 1000.0]), 0.5, 0.9,
                              self._cost(amount_weighted=True))
        assert large.expected_cost > small.expected_cost

    def test_flat_cost_ignores_amount(self):
        y = np.array([1, 1])
        s = np.array([0.0, 0.0])
        c = self._cost(amount_weighted=False)
        small = expected_cost(y, s, np.array([10.0, 10.0]), 0.5, 0.9, c)
        large = expected_cost(y, s, np.array([1000.0, 1000.0]), 0.5, 0.9, c)
        assert small.expected_cost == pytest.approx(large.expected_cost)

    def test_review_is_cheaper_than_approving_fraud(self):
        y = np.array([1])
        amt = np.array([500.0])
        approved = expected_cost(y, np.array([0.0]), amt, 0.4, 0.9)
        reviewed = expected_cost(y, np.array([0.5]), amt, 0.4, 0.9)
        assert reviewed.expected_cost < approved.expected_cost

    def test_review_is_not_free(self):
        """Fraud sent to review is only partly recovered, and review costs."""
        y = np.array([1])
        amt = np.array([500.0])
        reviewed = expected_cost(y, np.array([0.5]), amt, 0.4, 0.9)
        blocked = expected_cost(y, np.array([0.95]), amt, 0.4, 0.9)
        assert reviewed.expected_cost > blocked.expected_cost

    def test_blocking_legitimate_traffic_costs_money(self):
        y = np.array([0, 0])
        c = expected_cost(y, np.array([0.99, 0.99]), np.array([10.0, 10.0]), 0.4, 0.9)
        assert c.false_positive_cost == pytest.approx(2 * CONFIG.cost.false_positive_cost)
        assert c.blocked_legit == 2

    def test_baseline_and_net_benefit(self):
        y = np.array([1, 1, 0])
        amt = np.array([100.0, 200.0, 50.0])
        c = expected_cost(y, np.array([0.99, 0.99, 0.0]), amt, 0.4, 0.9)
        # All fraud stopped, no good order blocked: net benefit is the whole
        # baseline loss.
        assert c.residual_loss == pytest.approx(0.0)
        assert c.net_benefit == pytest.approx(c.baseline_loss_no_system)

    def test_counts_partition_the_population(self):
        rng = np.random.default_rng(1)
        y = rng.integers(0, 2, 100)
        s = rng.random(100)
        c = expected_cost(y, s, rng.random(100) * 100, 0.3, 0.7)
        assert c.n_approve + c.n_review + c.n_block == 100


class TestThresholdSelection:
    def _data(self, n=4000, seed=0):
        rng = np.random.default_rng(seed)
        y = rng.binomial(1, 0.15, n)
        s = np.clip(rng.normal(np.where(y == 1, 0.65, 0.3), 0.15), 0, 1)
        amt = rng.gamma(2.0, 60.0, n)
        return y, s, amt

    def test_returns_all_three_modes(self):
        y, s, amt = self._data()
        ops = choose_thresholds(y, s, amt)
        assert set(ops) == {"balanced", "high_precision", "high_recall"}

    def test_review_never_exceeds_block(self):
        y, s, amt = self._data()
        for op in choose_thresholds(y, s, amt).values():
            assert op.review_threshold <= op.block_threshold

    def test_high_precision_beats_high_recall_on_precision(self):
        y, s, amt = self._data()
        ops = choose_thresholds(y, s, amt)
        hp = binary_metrics(y, s, ops["high_precision"].block_threshold)
        hr = binary_metrics(y, s, ops["high_recall"].block_threshold)
        assert hp.precision >= hr.precision
        assert hr.recall >= hp.recall

    def test_degenerate_corners_are_excluded(self):
        """A threshold must be supported by enough validation alerts."""
        y, s, amt = self._data()
        ops = choose_thresholds(y, s, amt, min_alerts=200)
        hp = binary_metrics(y, s, ops["high_precision"].block_threshold)
        assert hp.n_predicted_positive >= 200

    def test_balanced_minimises_cost_on_its_own_grid(self):
        y, s, amt = self._data()
        ops = choose_thresholds(y, s, amt)
        bal = ops["balanced"]
        best = expected_cost(y, s, amt, bal.review_threshold, bal.block_threshold)
        sweep = cost_sweep(y, s, amt, review_band_frac=CONFIG.decision.review_band_frac)
        assert best.expected_cost <= sweep["expected_cost"].min() * 1.001

    def test_every_operating_point_states_its_rationale(self):
        y, s, amt = self._data()
        for op in choose_thresholds(y, s, amt).values():
            assert op.rationale
            assert op.selected_on == "validation"


class TestFusion:
    def _scores(self, n=3000, seed=0):
        rng = np.random.default_rng(seed)
        y = rng.binomial(1, 0.2, n)
        good = np.clip(rng.normal(np.where(y == 1, 0.75, 0.25), 0.15), 0, 1)
        noise = rng.random(n)
        return y, {
            "tabular": good,
            "graph": np.clip(good + rng.normal(0, 0.1, n), 0, 1),
            "behavioral": noise,
            "velocity": noise,
        }

    def test_weights_sum_to_one(self):
        y, s = self._scores()
        f = fit_fusion(s, y, verbose=False)
        assert sum(f.weights.values()) == pytest.approx(1.0)
        assert set(f.weights) == set(CHANNELS)

    def test_search_beats_or_matches_the_suggested_default(self):
        y, s = self._scores()
        f = fit_fusion(s, y, verbose=False)
        assert f.val_score_uncalibrated >= f.default_weight_score

    def test_search_downweights_pure_noise(self):
        y, s = self._scores()
        f = fit_fusion(s, y, verbose=False)
        informative = f.weights["tabular"] + f.weights["graph"]
        noise = f.weights["behavioral"] + f.weights["velocity"]
        assert informative > noise

    def test_predictions_are_probabilities(self):
        y, s = self._scores()
        f = fit_fusion(s, y, verbose=False)
        p = f.predict(s)
        assert (p >= 0).all() and (p <= 1).all()

    def test_calibration_improves_brier(self):
        from sklearn.metrics import brier_score_loss

        y, s = self._scores()
        f = fit_fusion(s, y, verbose=False)
        raw = np.clip(f.fuse(s), 0, 1)
        cal = f.predict(s)
        assert brier_score_loss(y, cal) <= brier_score_loss(y, raw)

    def test_calibration_table_bins_are_populated(self):
        y, s = self._scores()
        f = fit_fusion(s, y, verbose=False)
        tab = calibration_table(y, f.predict(s))
        assert len(tab) > 0
        assert tab["n"].sum() == len(y)

    def test_missing_channel_raises(self):
        y, s = self._scores()
        f = fit_fusion(s, y, verbose=False)
        with pytest.raises(KeyError):
            f.predict({k: v for k, v in s.items() if k != "graph"})


class TestDrift:
    def test_identical_distributions_have_zero_psi(self):
        rng = np.random.default_rng(0)
        a = rng.random(2000)
        assert population_stability_index(a, a) == pytest.approx(0.0, abs=1e-9)

    def test_shifted_distribution_is_detected(self):
        rng = np.random.default_rng(0)
        a = rng.beta(2, 8, 3000)
        b = rng.beta(8, 2, 3000)
        assert population_stability_index(a, b) > 0.25

    def test_classification_bands(self):
        assert classify(0.05) == STABLE
        assert classify(0.15) == MONITOR
        assert classify(0.9) == SHIFTED

    def test_report_states_an_implication(self):
        rng = np.random.default_rng(0)
        rep = drift_report(rng.beta(2, 8, 1000), rng.beta(8, 2, 1000))
        assert rep["status"] == SHIFTED
        assert "recalibration" in rep["implication"]

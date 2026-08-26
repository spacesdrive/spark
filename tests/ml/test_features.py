"""
Tests for feature building.

The important ones prove that no feature can see the future. Everything this
project reports depends on that, and it is the kind of thing that quietly
breaks during a refactor.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml.features.causal import (
    EntityHistory,
    RiskCounter,
    SlidingDistinct,
    build_causal_features,
)


class TestEntityHistory:
    def test_empty_history_is_zero(self):
        h = EntityHistory()
        assert h.lifetime() == (0, 0.0, 0.0, 0.0)
        assert h.window(100, 50) == (0, 0.0, 0.0, 0.0)

    def test_lifetime_statistics(self):
        h = EntityHistory()
        for t, a in [(0, 10.0), (1, 20.0), (2, 30.0)]:
            h.add(t, a)
        cnt, total, mean, std = h.lifetime()
        assert cnt == 3
        assert total == pytest.approx(60.0)
        assert mean == pytest.approx(20.0)
        assert std == pytest.approx(np.std([10, 20, 30]))

    def test_window_excludes_older_rows(self):
        h = EntityHistory()
        for t in range(10):
            h.add(t * 10, 5.0)     # times 0,10,...,90
        cnt, total, _, _ = h.window(90, 25)   # keeps t >= 65 -> 70, 80, 90
        assert cnt == 3
        assert total == pytest.approx(15.0)

    def test_window_matches_bruteforce(self):
        """
        Windowed aggregates equal a direct recomputation.

        The query time is at or after every stored time, which is the only
        situation the streaming pass ever creates: a row is added only once it
        has been reached, so nothing in the history is ever ahead of the
        current clock. ``window`` relies on that and does not bound the upper
        end of the range.
        """
        rng = np.random.default_rng(0)
        times = np.sort(rng.integers(0, 500, 60))
        amts = rng.random(60) * 100
        h = EntityHistory()
        for t, a in zip(times, amts):
            h.add(int(t), float(a))

        t_q = int(times.max())
        for span in (10, 50, 200):
            cnt, total, mean, std = h.window(t_q, span)
            keep = amts[times >= t_q - span]
            assert cnt == len(keep)
            assert total == pytest.approx(keep.sum())
            if len(keep):
                assert mean == pytest.approx(keep.mean())
                assert std == pytest.approx(keep.std())


class TestSlidingDistinct:
    def test_counts_distinct_inside_window(self):
        s = SlidingDistinct(span=10)
        s.add("m1", 0, "a")
        s.add("m1", 1, "b")
        s.add("m1", 2, "a")
        assert s.query("m1", 5) == 2

    def test_expires_outside_window(self):
        s = SlidingDistinct(span=10)
        s.add("m1", 0, "a")
        s.add("m1", 1, "b")
        assert s.query("m1", 100) == 0

    def test_unknown_key_is_zero(self):
        assert SlidingDistinct(span=10).query("nope", 5) == 0


class TestRiskCounter:
    def test_label_invisible_until_disclosed(self):
        rc = RiskCounter(lag=100)
        rc.observe(t=0, key="T1", label=1, amount=50.0)
        rc.advance(50)
        n, f, _, _ = rc.stats("T1", 0.1, 20.0)
        assert (n, f) == (0, 0), "label must stay hidden before the lag elapses"
        rc.advance(100)
        n, f, _, _ = rc.stats("T1", 0.1, 20.0)
        assert (n, f) == (1, 1)

    def test_zero_lag_discloses_immediately(self):
        rc = RiskCounter(lag=0)
        rc.observe(t=10, key="T1", label=1, amount=5.0)
        rc.advance(10)
        n, f, _, _ = rc.stats("T1", 0.1, 20.0)
        assert (n, f) == (1, 1)

    def test_unlabeled_is_never_recorded(self):
        rc = RiskCounter(lag=0)
        rc.observe(t=0, key="T1", label=2, amount=5.0)
        rc.advance(10)
        assert rc.stats("T1", 0.1, 20.0)[0] == 0

    def test_smoothing_pulls_toward_prior(self):
        rc = RiskCounter(lag=0)
        rc.observe(t=0, key="T1", label=1, amount=10.0)
        rc.advance(0)
        _, _, rate, _ = rc.stats("T1", prior_rate=0.1, prior_strength=20.0)
        # One confirmed fraud must not read as a 100%-fraud merchant.
        assert 0.1 < rate < 0.2


class TestCausality:
    """The core guarantee: features are emitted before the row updates state."""

    def test_first_row_has_no_history(self, tiny_df):
        fb = build_causal_features(tiny_df, verbose=False)
        first = fb.base.iloc[0]
        for col in fb.base_columns:
            if col.endswith(("_txn_count", "_amt_mean_hist", "_amt_std_hist")):
                assert first[col] == 0.0, f"{col} must be 0 for the first row"
        assert fb.risk.iloc[0]["Target_known_outcomes"] == 0.0

    def test_features_depend_only_on_the_past(self, tiny_df):
        """
        Truncating the future must not change the past's features.

        This is the strongest available check. Compute features on the full
        frame, then on a prefix of it, and require the overlapping rows to be
        identical. Any leakage from later rows into earlier ones breaks it.
        """
        full = build_causal_features(tiny_df, verbose=False)
        k = 30
        prefix = build_causal_features(
            tiny_df.iloc[:k].reset_index(drop=True), verbose=False
        )
        pd.testing.assert_frame_equal(
            full.base.iloc[:k].reset_index(drop=True),
            prefix.base.reset_index(drop=True),
            check_exact=False,
            rtol=1e-6,
        )
        pd.testing.assert_frame_equal(
            full.risk.iloc[:k].reset_index(drop=True),
            prefix.risk.reset_index(drop=True),
            check_exact=False,
            rtol=1e-6,
        )

    def test_own_label_never_reaches_own_features(self, tiny_df):
        """Flipping a row's label must not change that row's own features."""
        base_out = build_causal_features(tiny_df, verbose=False)
        flipped = tiny_df.copy()
        idx = int(np.where(flipped["Labels"].to_numpy() == 1)[0][0])
        flipped.loc[idx, "Labels"] = 0
        other = build_causal_features(flipped, verbose=False)
        pd.testing.assert_series_equal(
            base_out.risk.iloc[idx], other.risk.iloc[idx], check_names=False
        )

    def test_train_mask_restricts_risk_counters(self, tiny_df):
        n = len(tiny_df)
        none_allowed = np.zeros(n, dtype=bool)
        restricted = build_causal_features(
            tiny_df, train_mask=none_allowed, verbose=False
        )
        assert restricted.risk["Target_known_frauds"].sum() == 0.0


class TestFeatureOutput:
    def test_no_nan_or_inf(self, tiny_df):
        fb = build_causal_features(tiny_df, verbose=False)
        for frame in (fb.base, fb.risk):
            arr = frame.to_numpy()
            assert not np.isnan(arr).any()
            assert not np.isinf(arr).any()

    def test_shapes_and_index_align(self, tiny_df):
        fb = build_causal_features(tiny_df, verbose=False)
        assert len(fb.base) == len(tiny_df)
        assert len(fb.risk) == len(tiny_df)
        assert list(fb.base.columns) == fb.base_columns
        assert list(fb.risk.columns) == fb.risk_columns

    def test_deterministic(self, tiny_df):
        a = build_causal_features(tiny_df, verbose=False)
        b = build_causal_features(tiny_df, verbose=False)
        pd.testing.assert_frame_equal(a.base, b.base)
        pd.testing.assert_frame_equal(a.risk, b.risk)

    def test_ring_shows_high_merchant_fan_in(self, tiny_df):
        """The planted ring must produce the signal it was planted to produce."""
        fb = build_causal_features(tiny_df, verbose=False)
        ring_rows = tiny_df["Target"] == "T900"
        ordinary = ~ring_rows
        col = "Target_distinct_Source_w20"
        # Each ring transaction comes from a different account, so distinct
        # accounts per merchant climbs; repeat customers do not do that.
        assert fb.base.loc[ring_rows, col].max() > fb.base.loc[ordinary, col].max()

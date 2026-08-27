"""
Tests for loading, validation, and splitting.
"""

from __future__ import annotations

import pandas as pd
import pytest

from ml.config import CONFIG
from ml.data.loader import (
    binary_labels,
    labeled_mask,
    load_raw,
    make_time_splits,
    validate_raw,
)


def _valid_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Time": [0, 1, 2, 3],
            "Source": ["S1", "S2", "S1", "S3"],
            "Target": ["T1", "T1", "T2", "T1"],
            "Amount": [10.0, 20.0, 5.5, 0.0],
            "Location": ["L1", "L1", "L2", "L1"],
            "Type": ["TP1", "TP1", "TP2", "TP1"],
            "Labels": [0, 1, 2, 0],
        }
    )


class TestValidation:
    def test_valid_frame_passes(self):
        rep = validate_raw(_valid_frame())
        assert rep.ok
        assert rep.stats["n_rows"] == 4
        assert rep.stats["n_fraud"] == 1
        assert rep.stats["n_unlabeled"] == 1

    def test_missing_column_is_an_error(self):
        rep = validate_raw(_valid_frame().drop(columns=["Amount"]))
        assert not rep.ok
        assert any("missing required columns" in e for e in rep.errors)

    def test_empty_frame_is_an_error(self):
        rep = validate_raw(_valid_frame().iloc[0:0])
        assert not rep.ok

    def test_null_values_are_an_error(self):
        df = _valid_frame()
        df.loc[0, "Source"] = None
        rep = validate_raw(df)
        assert not rep.ok
        assert any("null values" in e for e in rep.errors)

    def test_label_outside_domain_is_an_error(self):
        df = _valid_frame()
        df.loc[0, "Labels"] = 7
        rep = validate_raw(df)
        assert not rep.ok
        assert any("outside" in e for e in rep.errors)

    def test_negative_amount_is_an_error(self):
        df = _valid_frame()
        df.loc[0, "Amount"] = -1.0
        rep = validate_raw(df)
        assert not rep.ok
        assert any("negative" in e for e in rep.errors)

    def test_no_positives_is_an_error(self):
        df = _valid_frame()
        df["Labels"] = [0, 0, 0, 0]
        rep = validate_raw(df)
        assert not rep.ok
        assert any("no positive" in e for e in rep.errors)

    def test_zero_amount_is_a_warning_not_an_error(self):
        # The real dataset has 6,812 zero-amount rows. They are legitimate
        # records and must not fail the pipeline.
        rep = validate_raw(_valid_frame())
        assert rep.ok
        assert any("Amount == 0" in w for w in rep.warnings)

    def test_duplicate_rows_are_a_warning(self):
        df = pd.concat([_valid_frame(), _valid_frame().iloc[[0]]], ignore_index=True)
        rep = validate_raw(df)
        assert rep.ok
        assert any("duplicated" in w for w in rep.warnings)

    def test_unsorted_time_is_a_warning(self):
        df = _valid_frame().iloc[::-1].reset_index(drop=True)
        rep = validate_raw(df)
        assert any("not sorted" in w for w in rep.warnings)

    def test_raise_if_invalid(self):
        rep = validate_raw(_valid_frame().drop(columns=["Time"]))
        with pytest.raises(ValueError, match="failed validation"):
            rep.raise_if_invalid()


class TestLabels:
    def test_labeled_mask_excludes_unknown(self):
        df = _valid_frame()
        m = labeled_mask(df)
        assert m.tolist() == [True, True, False, True]

    def test_binary_labels_coerce_unknown_to_zero(self):
        y = binary_labels(_valid_frame())
        assert y.tolist() == [0, 1, 0, 0]
        assert y[2] == 0  # was LABEL_UNKNOWN


class TestSplits:
    def test_splits_are_disjoint_and_complete(self):
        df = pd.DataFrame(
            {
                "Time": list(range(100)),
                "Source": ["S1"] * 100,
                "Target": ["T1"] * 100,
                "Amount": [1.0] * 100,
                "Location": ["L1"] * 100,
                "Type": ["TP1"] * 100,
                "Labels": [0, 1] * 50,
            }
        )
        sp = make_time_splits(df)
        total = sp.train.astype(int) + sp.val.astype(int) + sp.test.astype(int)
        assert (total == 1).all(), "splits must partition the rows exactly once"

    def test_splits_are_time_ordered(self):
        df = pd.DataFrame(
            {
                "Time": list(range(100)),
                "Source": ["S1"] * 100,
                "Target": ["T1"] * 100,
                "Amount": [1.0] * 100,
                "Location": ["L1"] * 100,
                "Type": ["TP1"] * 100,
                "Labels": [0, 1] * 50,
            }
        )
        sp = make_time_splits(df)
        t = df["Time"].to_numpy()
        # This is the property every reported metric depends on: no test
        # transaction may precede a training transaction.
        assert t[sp.train].max() < t[sp.val].min()
        assert t[sp.val].max() < t[sp.test].min()

    def test_too_few_rows_raises(self):
        df = _valid_frame()
        with pytest.raises(ValueError, match="at least 10 rows"):
            make_time_splits(df)


@pytest.mark.slow
class TestRealDataset:
    def test_loads_and_validates(self, raw_available):
        if not raw_available:
            pytest.skip("dataset not downloaded; run python -m spark.data.fetch")
        df = load_raw()
        assert len(df) > 1000
        assert df["Time"].is_monotonic_increasing
        assert df.index.is_unique
        assert list(df.index) == list(range(len(df)))

    def test_split_fractions_are_respected(self, raw_available):
        if not raw_available:
            pytest.skip("dataset not downloaded")
        df = load_raw()
        sp = make_time_splits(df)
        assert abs(sp.train.mean() - CONFIG.split.train_frac) < 0.01
        assert abs(sp.val.mean() - CONFIG.split.val_frac) < 0.01

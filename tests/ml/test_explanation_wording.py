"""
Every contributing feature has to read as a sentence.

Features are generated per entity, so Source, Target, Location and Type each
get the same families. Only a few combinations had hand-written phrases, and
the rest fell through to the raw column name: a real explanation on the
dashboard read "Type amt std hist = 11,342.146" beside neighbours written in
plain English. That is the one place the product is supposed to be explaining
itself, so a debug line there is a defect.
"""

from __future__ import annotations

import pytest

from ml.config import ENTITY_ROLE
from ml.evaluation.explain import _phrase

#: Every family the feature builder emits for each entity.
SUFFIXES = [
    "_txn_count",
    "_is_new",
    "_age",
    "_gap_since_last",
    "_amt_mean_hist",
    "_amt_std_hist",
    "_amt_z",
    "_cnt_w20",
    "_amt_sum_w500",
    "_amt_mean_w20",
]


@pytest.mark.parametrize("entity", sorted(ENTITY_ROLE))
@pytest.mark.parametrize("suffix", SUFFIXES)
def test_every_family_reads_as_a_sentence(entity: str, suffix: str) -> None:
    text = _phrase(f"{entity}{suffix}", 12.5)

    # The give-away for the raw fallback is the "name = number" shape.
    assert " = " not in text, f"{entity}{suffix} fell through to the raw name"
    # And no underscored column name should survive into user-facing text.
    assert "_" not in text


def test_the_case_that_was_reported() -> None:
    text = _phrase("Type_amt_std_hist", 11342.146)
    assert text == "amounts for this payment channel vary by about 11,342.15"


def test_hand_written_phrases_still_win() -> None:
    """The specific wording beats the generated family sentence."""
    assert _phrase("Source_txn_count", 2) == "account has 2 prior transactions"
    assert _phrase("amount_cents", 95) == "amount ends in 95 cents"


def test_an_unknown_feature_is_still_reported() -> None:
    """Never drop something that moved the score just because it has no phrase."""
    assert "made up feature" in _phrase("made_up_feature", 1.5)

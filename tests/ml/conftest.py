"""
Fixtures for the pipeline tests.

Most of them run on a small made-up frame so they are fast and the expected
values can be checked by hand. The ones that need the real dataset or a trained
model are marked slow and skip when those are not on disk.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from ml.config import ARTIFACT_DIR, RAW_CSV


@pytest.fixture
def tiny_df() -> pd.DataFrame:
    """
    A small, hand-checkable transaction frame.

    Deliberately contains a ring: accounts S900-S907 all hit merchant T900 on
    channel TP900 in a tight burst with near-identical small amounts.
    """
    rows = []
    t = 0

    # ordinary traffic: repeat customers, varied amounts, spread out
    for i in range(40):
        rows.append(
            {
                "Time": t,
                "Source": f"S{100 + (i % 8)}",
                "Target": f"T{100 + (i % 3)}",
                "Amount": float(50 + (i * 7) % 300),
                "Location": f"L{100 + (i % 2)}",
                "Type": f"TP{100 + (i % 2)}",
                "Labels": 0 if i % 5 else 2,
            }
        )
        t += 3

    # a ring: many single-use accounts, one merchant, one channel, tight burst,
    # small near-identical amounts
    for i in range(20):
        rows.append(
            {
                "Time": t,
                "Source": f"S{900 + i}",
                "Target": "T900",
                "Amount": 4.0 + (i % 3) * 0.5,
                "Location": "L900",
                "Type": "TP900",
                "Labels": 1 if i % 4 else 2,
            }
        )
        t += 1

    df = pd.DataFrame(rows)
    df["txn_id"] = ["txn_" + str(i).zfill(6) for i in range(len(df))]
    return df


@pytest.fixture
def raw_available() -> bool:
    return RAW_CSV.exists()


@pytest.fixture
def artifacts_available() -> bool:
    return (Path(ARTIFACT_DIR) / "model_metadata.json").exists()


@pytest.fixture
def sample_frame(tiny_df) -> pd.DataFrame:
    """The hand-checkable frame, under the name the serving tests use."""
    return tiny_df


@pytest.fixture(scope="session")
def trained_engine():
    """
    The real loaded engine, shared across the session.

    Loading it takes a few seconds, so it is built once. Tests that use it are
    marked slow and skip when there is no trained model on disk.
    """
    if not (Path(ARTIFACT_DIR) / "model_metadata.json").exists():
        pytest.skip("no trained model; run python -m spark.models.train")
    from spark.risk.engine import ScoringEngine

    return ScoringEngine(mode="balanced", with_explainer=True, verbose=False)

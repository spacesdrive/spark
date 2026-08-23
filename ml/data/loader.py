"""
Load the raw CSV, check it, and split it by time.

The checks are strict on purpose. If a bad file gets through, the model still
trains and still prints numbers, but those numbers mean nothing.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ml.config import (
    CONFIG,
    ENTITY_COLS,
    LABEL_COL,
    LABEL_FRAUD,
    LABEL_LEGIT,
    LABEL_UNKNOWN,
    RAW_CSV,
    RAW_SCHEMA,
    TIME_COL,
    Config,
)


# Validation


@dataclass
class ValidationReport:
    """Outcome of validating a raw dataframe."""

    n_rows: int = 0
    n_cols: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stats: Dict[str, object] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def raise_if_invalid(self) -> "ValidationReport":
        if self.errors:
            joined = "\n  - ".join(self.errors)
            raise ValueError(f"Raw data failed validation:\n  - {joined}")
        return self


def validate_raw(df: pd.DataFrame) -> ValidationReport:
    """
    Check a raw S-FFSD frame against the dataset contract.

    Errors are conditions that make the pipeline unsound (missing column, bad
    label value, non-monotonic time). Warnings are conditions worth knowing
    about that the pipeline can handle (duplicates, zero amounts).
    """
    rep = ValidationReport(n_rows=len(df), n_cols=df.shape[1])

    # columns present
    missing = [c for c in RAW_SCHEMA if c not in df.columns]
    if missing:
        rep.errors.append(f"missing required columns: {missing}")
        return rep

    extra = [c for c in df.columns if c not in RAW_SCHEMA]
    if extra:
        rep.warnings.append(f"unexpected extra columns ignored: {extra}")

    # empty
    if len(df) == 0:
        rep.errors.append("dataset is empty")
        return rep

    # dtypes
    if not pd.api.types.is_integer_dtype(df[TIME_COL]):
        rep.errors.append(f"{TIME_COL} must be integer, got {df[TIME_COL].dtype}")
    if not pd.api.types.is_numeric_dtype(df["Amount"]):
        rep.errors.append(f"Amount must be numeric, got {df['Amount'].dtype}")
    if not pd.api.types.is_integer_dtype(df[LABEL_COL]):
        rep.errors.append(f"{LABEL_COL} must be integer, got {df[LABEL_COL].dtype}")

    # nulls
    nulls = df[list(RAW_SCHEMA)].isna().sum()
    bad_null = {c: int(n) for c, n in nulls.items() if n > 0}
    if bad_null:
        rep.errors.append(f"null values present in required columns: {bad_null}")

    # label domain
    if pd.api.types.is_integer_dtype(df[LABEL_COL]):
        allowed = {LABEL_LEGIT, LABEL_FRAUD, LABEL_UNKNOWN}
        seen = set(df[LABEL_COL].unique().tolist())
        if not seen.issubset(allowed):
            rep.errors.append(
                f"{LABEL_COL} contains values outside {sorted(allowed)}: "
                f"{sorted(seen - allowed)}"
            )
        n_labeled = int((df[LABEL_COL] != LABEL_UNKNOWN).sum())
        if n_labeled == 0:
            rep.errors.append("no labeled rows: supervised training is impossible")
        elif int((df[LABEL_COL] == LABEL_FRAUD).sum()) == 0:
            rep.errors.append("no positive (fraud) rows: nothing to learn")

    # time ordering
    if pd.api.types.is_integer_dtype(df[TIME_COL]):
        if not df[TIME_COL].is_monotonic_increasing:
            rep.warnings.append(
                f"{TIME_COL} is not sorted; the loader will sort by it"
            )
        if df[TIME_COL].duplicated().any():
            n_dup_t = int(df[TIME_COL].duplicated().sum())
            rep.warnings.append(
                f"{n_dup_t} duplicate {TIME_COL} values; ties broken by row order"
            )
        if (df[TIME_COL] < 0).any():
            rep.errors.append(f"{TIME_COL} contains negative values")

    # amounts
    if pd.api.types.is_numeric_dtype(df["Amount"]):
        if (df["Amount"] < 0).any():
            rep.errors.append("Amount contains negative values")
        n_zero = int((df["Amount"] == 0).sum())
        if n_zero:
            rep.warnings.append(f"{n_zero} rows with Amount == 0")
        if np.isinf(df["Amount"]).any():
            rep.errors.append("Amount contains infinite values")

    # entity columns
    for col in ENTITY_COLS:
        if (df[col].astype(str).str.strip() == "").any():
            rep.errors.append(f"{col} contains empty strings")

    # duplicates
    n_dup = int(df.duplicated(subset=list(RAW_SCHEMA)).sum())
    if n_dup:
        rep.warnings.append(f"{n_dup} fully duplicated rows")

    # summary stats
    rep.stats = {
        "n_rows": len(df),
        "time_min": int(df[TIME_COL].min()),
        "time_max": int(df[TIME_COL].max()),
        "amount_min": float(df["Amount"].min()),
        "amount_max": float(df["Amount"].max()),
        "amount_mean": float(df["Amount"].mean()),
        "amount_median": float(df["Amount"].median()),
        "n_labeled": int((df[LABEL_COL] != LABEL_UNKNOWN).sum()),
        "n_fraud": int((df[LABEL_COL] == LABEL_FRAUD).sum()),
        "n_legit": int((df[LABEL_COL] == LABEL_LEGIT).sum()),
        "n_unlabeled": int((df[LABEL_COL] == LABEL_UNKNOWN).sum()),
        "n_duplicate_rows": n_dup,
        "cardinality": {c: int(df[c].nunique()) for c in ENTITY_COLS},
    }
    lab = rep.stats["n_labeled"]
    rep.stats["fraud_rate_labeled"] = (
        float(rep.stats["n_fraud"] / lab) if lab else 0.0
    )
    return rep


# Loading


def file_digest(path: Path) -> str:
    """SHA-256 of the raw file, recorded in artifacts for reproducibility."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_raw(path: Optional[Path] = None, validate: bool = True) -> pd.DataFrame:
    """
    Load the raw dataset, validate it, and return it sorted by time.

    The returned frame carries a fresh ``RangeIndex``; downstream code uses
    positional indices as transaction node ids, so the index must be dense.
    """
    path = Path(path) if path is not None else RAW_CSV
    if not path.exists():
        raise FileNotFoundError(
            f"Raw dataset not found at {path}.\n"
            "Fetch it with:  python -m spark.data.fetch"
        )

    df = pd.read_csv(path)
    df = df[[c for c in RAW_SCHEMA if c in df.columns]].copy()

    for col in ENTITY_COLS:
        if col in df.columns:
            df[col] = df[col].astype(str)

    if validate:
        validate_raw(df).raise_if_invalid()

    df = df.sort_values(TIME_COL, kind="mergesort").reset_index(drop=True)
    df["txn_id"] = ["txn_" + str(i).zfill(6) for i in range(len(df))]
    return df


# Splitting


@dataclass
class Splits:
    """Boolean masks over the full frame, aligned to its positional index."""

    train: np.ndarray
    val: np.ndarray
    test: np.ndarray
    train_end_time: int
    val_end_time: int

    def as_dict(self) -> Dict[str, np.ndarray]:
        return {"train": self.train, "val": self.val, "test": self.test}

    def summary(self, df: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for name, mask in self.as_dict().items():
            sub = df.loc[mask]
            lab = sub[sub[LABEL_COL] != LABEL_UNKNOWN]
            rows.append(
                {
                    "split": name,
                    "rows": int(mask.sum()),
                    "time_min": int(sub[TIME_COL].min()) if len(sub) else -1,
                    "time_max": int(sub[TIME_COL].max()) if len(sub) else -1,
                    "labeled": int(len(lab)),
                    "fraud": int((lab[LABEL_COL] == LABEL_FRAUD).sum()),
                    "fraud_rate": (
                        float((lab[LABEL_COL] == LABEL_FRAUD).mean()) if len(lab) else 0.0
                    ),
                    "unlabeled": int((sub[LABEL_COL] == LABEL_UNKNOWN).sum()),
                }
            )
        return pd.DataFrame(rows)


def make_time_splits(df: pd.DataFrame, cfg: Config = CONFIG) -> Splits:
    """
    Split strictly by time, never by random sampling.

    A random split on a time-ordered payment stream lets the model see the
    future: it can learn a fraud ring from transactions that occur *after* the
    ones it is asked to score. Every number this project reports depends on
    that not happening, so the split is positional on sorted time and the
    boundaries are recorded in the artifact.
    """
    n = len(df)
    if n < 10:
        raise ValueError(f"need at least 10 rows to split, got {n}")

    i_train = int(n * cfg.split.train_frac)
    i_val = int(n * (cfg.split.train_frac + cfg.split.val_frac))

    times = df[TIME_COL].to_numpy()
    train_end_time = int(times[i_train - 1])
    val_end_time = int(times[i_val - 1])

    # Boundaries are placed on time values, not row positions, so that rows
    # sharing a timestamp never straddle a split.
    train = times <= train_end_time
    val = (times > train_end_time) & (times <= val_end_time)
    test = times > val_end_time

    for name, mask in (("train", train), ("val", val), ("test", test)):
        if not mask.any():
            raise ValueError(f"{name} split is empty; adjust split fractions")

    return Splits(
        train=train,
        val=val,
        test=test,
        train_end_time=train_end_time,
        val_end_time=val_end_time,
    )


def labeled_mask(df: pd.DataFrame) -> np.ndarray:
    """Rows with a confirmed outcome. Unlabeled rows are excluded from metrics."""
    return (df[LABEL_COL] != LABEL_UNKNOWN).to_numpy()


def binary_labels(df: pd.DataFrame) -> np.ndarray:
    """
    Labels as 0/1.

    Unlabeled rows map to 0 so array shapes stay aligned with the full frame;
    callers must always combine this with :func:`labeled_mask` before scoring.
    """
    y = df[LABEL_COL].to_numpy().copy()
    y[y == LABEL_UNKNOWN] = LABEL_LEGIT
    return y.astype(np.int8)

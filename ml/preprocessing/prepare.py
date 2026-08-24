"""
Build the modelling dataset: raw CSV to features, with caching.

The feature pass is the slowest step, so its output is cached. The cache key
is a hash of the raw file, the split settings, and the feature settings.
Change any of them and the cache misses. Change none and every command reuses
the same matrix.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

from ml.config import CONFIG, PROCESSED_DIR, RAW_CSV, Config
from ml.data.loader import (
    Splits,
    binary_labels,
    file_digest,
    labeled_mask,
    load_raw,
    make_time_splits,
    validate_raw,
)
from ml.features.causal import build_causal_features


@dataclass
class Dataset:
    """Everything downstream stages need, assembled once."""

    df: pd.DataFrame              # raw frame, time-sorted, with txn_id
    base: pd.DataFrame            # label-free features   (Model A input)
    risk: pd.DataFrame            # leak-free risk features (Model B input)
    splits: Splits
    y: np.ndarray                 # 0/1 labels, unlabeled coerced to 0
    labeled: np.ndarray           # rows with a confirmed outcome
    fingerprint: str

    @property
    def base_columns(self) -> List[str]:
        return list(self.base.columns)

    @property
    def risk_columns(self) -> List[str]:
        return list(self.risk.columns)

    def features(self, include_risk: bool = True) -> pd.DataFrame:
        return pd.concat([self.base, self.risk], axis=1) if include_risk else self.base

    def mask(self, split: str, labeled_only: bool = True) -> np.ndarray:
        """Boolean mask for a split, optionally restricted to labeled rows."""
        m = getattr(self.splits, split)
        return (m & self.labeled) if labeled_only else m

    def summary(self) -> pd.DataFrame:
        return self.splits.summary(self.df)


def _fingerprint(cfg: Config, raw_path: Path) -> str:
    """Hash of every input that determines the cached feature matrix."""
    payload = {
        "raw_sha256": file_digest(raw_path),
        "split": {
            "train_frac": cfg.split.train_frac,
            "val_frac": cfg.split.val_frac,
        },
        "features": {
            "velocity_windows": cfg.features.velocity_windows,
            "velocity_entities": cfg.features.velocity_entities,
            "risk_prior_strength": cfg.features.risk_prior_strength,
            "label_lag_steps": cfg.features.label_lag_steps,
        },
    }
    blob = json.dumps(payload, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def prepare(
    cfg: Config = CONFIG,
    raw_path: Optional[Path] = None,
    use_cache: bool = True,
    verbose: bool = True,
) -> Dataset:
    """
    Build (or load from cache) the full modelling dataset.

    A note on what the risk accumulators are allowed to see, because it is the
    subtlest correctness question in the project.

    They see **every confirmed outcome that precedes the transaction being
    scored**, regardless of which split that outcome falls in. They do not see
    the transaction's own label, and they cannot see the future. The
    single-pass structure makes both impossible.

    Restricting them to the training split instead would be *more*
    conservative and *less* correct. A deployed system scoring a transaction in
    March knows about the chargebacks it confirmed in February; pretending
    otherwise does not remove leakage, it simulates a system that has forgotten
    its own history. It also silently destroys the signal that matters most
    here: the abuse ring in this dataset begins after the training window, so
    train-gated counters report it as a merchant with zero known fraud.

    What *is* optimistic is assuming a confirmed outcome is known the instant
    it happens. Real chargebacks arrive weeks later. That assumption is
    isolated in ``FeatureConfig.label_lag_steps`` and its cost is measured.
    See ``ml.evaluation.sensitivity``.
    """
    raw_path = Path(raw_path) if raw_path else RAW_CSV
    df = load_raw(raw_path)
    splits = make_time_splits(df, cfg)
    fp = _fingerprint(cfg, raw_path)

    base_path = PROCESSED_DIR / f"base_{fp}.parquet"
    risk_path = PROCESSED_DIR / f"risk_{fp}.parquet"

    if use_cache and base_path.exists() and risk_path.exists():
        if verbose:
            print(f"[prepare] cache hit ({fp})")
        base = pd.read_parquet(base_path)
        risk = pd.read_parquet(risk_path)
    else:
        if verbose:
            print(f"[prepare] cache miss ({fp}); running causal pass")
        bundle = build_causal_features(
            df, cfg=cfg, train_mask=None, verbose=verbose
        )
        base, risk = bundle.base, bundle.risk
        base.to_parquet(base_path, index=False)
        risk.to_parquet(risk_path, index=False)
        if verbose:
            print(f"[prepare] cached to {base_path.name}, {risk_path.name}")

    return Dataset(
        df=df,
        base=base,
        risk=risk,
        splits=splits,
        y=binary_labels(df),
        labeled=labeled_mask(df),
        fingerprint=fp,
    )


def describe(ds: Dataset) -> dict:
    """Structured summary written into reports and model metadata."""
    rep = validate_raw(ds.df.drop(columns=["txn_id"]))
    return {
        "fingerprint": ds.fingerprint,
        "raw_stats": rep.stats,
        "raw_warnings": rep.warnings,
        "splits": ds.summary().to_dict(orient="records"),
        "n_base_features": len(ds.base_columns),
        "n_risk_features": len(ds.risk_columns),
        "train_end_time": ds.splits.train_end_time,
        "val_end_time": ds.splits.val_end_time,
    }

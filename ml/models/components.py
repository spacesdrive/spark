"""
Two simple risk scores that need no labels.

Both learned models need history, and both get weaker when confirmed fraud
labels arrive late. These two do not. A brand new account moving ten times
faster than normal is suspicious on its own.

Each one works the same way:

1. Combine a few named signals into one raw number.
2. Convert that number to its percentile against the training data.

Step 2 is what makes the output usable. A raw sum has no meaning on its own,
but "higher than 97 percent of normal traffic" does.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np
import pandas as pd

#: Signals feeding the behavioural channel. The sign says which direction is
#: suspicious: +1 means "larger is more unusual".
BEHAVIOURAL_SIGNALS: Dict[str, float] = {
    "Source_amt_z": 1.0,               # spend far from this account's own norm
    "Target_amt_z": 1.0,               # spend far from this merchant's norm
    "Source_new_Target": 1.0,          # first time at this merchant
    "Source_new_Type": 1.0,            # first time on this payment channel
    "Source_type_entropy_shift": 1.0,  # channel mix suddenly changing
    "Source_is_new": 1.0,              # no history at all
    "is_round_amount": 1.0,            # round amounts over-represented in abuse
}

#: Signals feeding the velocity channel.
VELOCITY_SIGNALS: Dict[str, float] = {
    "burst_ratio_Source": 1.0,          # account busier than its own baseline
    "burst_ratio_Target": 1.0,          # merchant busier than its own baseline
    "Source_cnt_w20": 1.0,              # short-window account volume
    "Target_distinct_Source_w500": 1.0, # accounts converging on the merchant
    "Type_distinct_Source_w500": 1.0,   # accounts converging on the channel
    "Target_fanin_ratio_w500": 1.0,     # share of them that are one-time
}


@dataclass
class EmpiricalScorer:
    """
    Maps a raw signal combination onto its training-set percentile.

    Holding the training quantiles fixed is deliberate: it means a shift in
    the live score distribution shows up as a shift in output, rather than
    being silently normalised away. That is what makes the score comparable
    across time and usable for drift monitoring.
    """

    name: str
    signals: List[str]
    weights: np.ndarray
    centre: np.ndarray
    spread: np.ndarray
    quantiles: np.ndarray  # sorted raw scores from the training split

    def raw(self, X: pd.DataFrame) -> np.ndarray:
        missing = [c for c in self.signals if c not in X.columns]
        if missing:
            raise KeyError(f"{self.name}: missing signals {missing}")
        arr = X[self.signals].to_numpy(dtype=np.float64)
        arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
        # Robust standardisation, so one heavy-tailed signal cannot swamp the
        # rest. Clipping bounds the influence of extreme outliers.
        z = (arr - self.centre) / self.spread
        z = np.clip(z, -6.0, 6.0)
        return z @ self.weights

    def score(self, X: pd.DataFrame) -> np.ndarray:
        """Percentile of each row against the training distribution, in [0, 1]."""
        r = self.raw(X)
        pos = np.searchsorted(self.quantiles, r, side="right")
        return np.clip(pos / max(len(self.quantiles), 1), 0.0, 1.0)


def _fit(
    name: str, spec: Dict[str, float], X: pd.DataFrame, train_mask: np.ndarray
) -> EmpiricalScorer:
    signals = [s for s in spec if s in X.columns]
    if not signals:
        raise KeyError(f"{name}: none of its signals are present in the features")
    weights = np.array([spec[s] for s in signals], dtype=np.float64)
    weights = weights / weights.sum()

    train = X.loc[train_mask, signals].to_numpy(dtype=np.float64)
    train = np.nan_to_num(train, nan=0.0, posinf=0.0, neginf=0.0)

    # Median and IQR rather than mean and standard deviation: velocity
    # features are heavily right-skewed and the mean sits inside the tail.
    centre = np.median(train, axis=0)
    q75, q25 = np.percentile(train, [75, 25], axis=0)
    spread = (q75 - q25)
    spread[spread < 1e-6] = 1.0

    scorer = EmpiricalScorer(
        name=name,
        signals=signals,
        weights=weights,
        centre=centre,
        spread=spread,
        quantiles=np.array([0.0]),
    )
    raw_train = scorer.raw(X.loc[train_mask])
    scorer.quantiles = np.sort(raw_train)
    return scorer


@dataclass
class UnsupervisedChannels:
    behavioural: EmpiricalScorer
    velocity: EmpiricalScorer

    def score(self, X: pd.DataFrame) -> Dict[str, np.ndarray]:
        return {
            "behavioral": self.behavioural.score(X),
            "velocity": self.velocity.score(X),
        }


def fit_channels(X: pd.DataFrame, train_mask: np.ndarray) -> UnsupervisedChannels:
    """Fit both unsupervised channels on the training split."""
    return UnsupervisedChannels(
        behavioural=_fit("behavioral", BEHAVIOURAL_SIGNALS, X, train_mask),
        velocity=_fit("velocity", VELOCITY_SIGNALS, X, train_mask),
    )

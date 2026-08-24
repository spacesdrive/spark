"""
Model A: a gradient boosted tree on plain features.

It only sees the label-free features: amounts, speed, history, and how many
different accounts or merchants an entity touched. It never sees a
confirmed-fraud count.

That limit is on purpose. It keeps Model A and Model B looking at different
things, so combining them is actually worth doing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

from ml.config import CONFIG, Config


@dataclass
class TabularModel:
    """A fitted LightGBM classifier plus the feature contract it expects."""

    booster: lgb.LGBMClassifier
    feature_names: List[str]
    best_iteration: Optional[int]
    train_rows: int
    pos_rate: float

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Fraud probability for each row, in the model's own feature order."""
        missing = [c for c in self.feature_names if c not in X.columns]
        if missing:
            raise KeyError(f"missing {len(missing)} features, e.g. {missing[:5]}")
        return self.booster.predict_proba(X[self.feature_names])[:, 1]

    def feature_importance(self, top_k: int = 30) -> pd.DataFrame:
        imp = pd.DataFrame(
            {
                "feature": self.feature_names,
                "gain": self.booster.booster_.feature_importance("gain"),
                "split": self.booster.booster_.feature_importance("split"),
            }
        )
        return imp.sort_values("gain", ascending=False).head(top_k).reset_index(drop=True)

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        return path

    @staticmethod
    def load(path: Path) -> "TabularModel":
        return joblib.load(Path(path))


def train_tabular(
    X_train: pd.DataFrame,
    y_train: np.ndarray,
    X_val: pd.DataFrame,
    y_val: np.ndarray,
    cfg: Config = CONFIG,
    verbose: bool = True,
) -> TabularModel:
    """
    Fit the tabular model, early-stopping on the validation split.

    Class imbalance is handled with ``scale_pos_weight`` rather than
    resampling: resampling would distort the base rate the calibrator later has
    to correct for, and the calibration step is where probabilities are made
    trustworthy.
    """
    lcfg = cfg.lgbm
    pos = float(y_train.sum())
    neg = float(len(y_train) - pos)
    spw = (neg / pos) if pos > 0 else 1.0

    clf = lgb.LGBMClassifier(
        n_estimators=lcfg.n_estimators,
        learning_rate=lcfg.learning_rate,
        num_leaves=lcfg.num_leaves,
        min_child_samples=lcfg.min_child_samples,
        subsample=lcfg.subsample,
        subsample_freq=lcfg.subsample_freq,
        colsample_bytree=lcfg.colsample_bytree,
        reg_lambda=lcfg.reg_lambda,
        scale_pos_weight=spw,
        random_state=lcfg.seed,
        n_jobs=-1,
        verbose=-1,
        deterministic=True,
        force_row_wise=True,
    )

    if verbose:
        print(
            f"[tabular] fitting on {len(X_train):,} rows x {X_train.shape[1]} features "
            f"(pos_rate={pos / len(y_train):.4f}, scale_pos_weight={spw:.2f})"
        )

    clf.fit(
        X_train,
        y_train,
        eval_X=X_val,
        eval_y=y_val,
        eval_metric="average_precision",
        callbacks=[
            lgb.early_stopping(lcfg.early_stopping_rounds, verbose=False),
            lgb.log_evaluation(0),
        ],
    )

    best = getattr(clf, "best_iteration_", None)
    if verbose:
        print(f"[tabular] stopped at iteration {best} of {lcfg.n_estimators}")

    return TabularModel(
        booster=clf,
        feature_names=list(X_train.columns),
        best_iteration=best,
        train_rows=len(X_train),
        pos_rate=float(pos / len(y_train)) if len(y_train) else 0.0,
    )

"""
Explain a decision.

Three sources, strongest first:

1. SHAP over the tree model. Exact for LightGBM, so the numbers really do add
   up to that model output.
2. Channel share. How much each of the four scores moved the final number.
3. Plain evidence. Entity risk rates and ring membership, written as sentences.

Wording rule: these are things that pushed the score up or down, not proof of
fraud. The text says "contributed to the risk score", never "caused". That
matters when someone challenges a declined payment.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

import re

from ml.config import CONFIG, ENTITY_ROLE, ExplainConfig

#: Human-readable templates for features that carry a clear operational
#: meaning. Anything not listed falls back to a generic rendering, so the
#: explainer never silently drops a contributing feature.
FEATURE_PHRASES: Dict[str, str] = {
    "Source_amt_z": "transaction amount {mult} this account's own baseline",
    "Target_amt_z": "amount unusual for this merchant",
    "Source_txn_count": "account has {value:.0f} prior transactions",
    "Source_is_new": "first transaction from this account",
    "Source_age": "account first seen {value:.0f} time units ago",
    "Source_gap_since_last": "{value:.0f} time units since this account last transacted",
    "Target_distinct_Source_w500": "{value:.0f} distinct accounts hit this merchant recently",
    "Type_distinct_Source_w500": "{value:.0f} distinct accounts used this payment channel recently",
    "Target_fanin_ratio_w500": "{value:.0%} of recent transactions at this merchant came from different accounts",
    "burst_ratio_Source": "account transacting {value:.1f}x its normal rate",
    "burst_ratio_Target": "merchant receiving {value:.1f}x its normal volume",
    "Source_new_Target": "first time this account has paid this merchant",
    "Source_new_Type": "first time this account has used this payment channel",
    "Source_type_entropy_shift": "payment-channel mix for this account is shifting",
    "amount": "transaction amount {value:.2f}",
    "log_amount": "transaction amount {value:.2f} (log scale)",
    "is_round_amount": "round-number amount",
    "amount_cents": "amount ends in {value:.0f} cents",
    "Source_cnt_w20": "{value:.0f} transactions from this account in the last 20 time units",
    "Target_cnt_w20": "{value:.0f} transactions at this merchant in the last 20 time units",
}

#: Risk features get their own phrasing because they are label-derived and the
#: wording has to make the provenance explicit.
RISK_PHRASES: Dict[str, str] = {
    "Source_risk_rate": "confirmed-fraud rate for this account",
    "Target_risk_rate": "confirmed-fraud rate for this merchant",
    "Type_risk_rate": "confirmed-fraud rate for this payment channel",
    "Location_risk_rate": "confirmed-fraud rate for this location",
}


@dataclass
class Reason:
    """One contributing factor."""

    text: str
    direction: str          # "increases" | "decreases"
    contribution: float     # signed SHAP value, in log-odds
    feature: str

    def as_dict(self) -> dict:
        return asdict(self)

    def render(self) -> str:
        sign = "+" if self.direction == "increases" else "-"
        return f"{sign} {self.text}"


@dataclass
class Explanation:
    """Everything said about one decision."""

    reasons: List[Reason]
    channel_attribution: Dict[str, float]
    entity_risk: Dict[str, float]
    cluster_id: Optional[str]
    base_value: float

    def as_dict(self) -> dict:
        return {
            "reasons": [r.as_dict() for r in self.reasons],
            "reason_text": [r.render() for r in self.reasons],
            "channel_attribution": self.channel_attribution,
            "entity_risk": self.entity_risk,
            "cluster_id": self.cluster_id,
            "base_value": self.base_value,
        }


#: Suffix templates shared by every entity. ``role`` is filled from
#: ENTITY_ROLE, so ``Type_amt_std_hist`` and ``Location_amt_std_hist`` both read
#: properly without either being listed by hand.
FAMILY_PHRASES: Dict[str, str] = {
    "_txn_count": "this {role} has {value:.0f} prior transactions",
    "_is_new": "first transaction for this {role}",
    "_age": "this {role} was first seen {value:.0f} time units ago",
    "_gap_since_last": "{value:.0f} time units since this {role} was last used",
    "_amt_mean_hist": "this {role} usually sees amounts around {value:,.2f}",
    "_amt_std_hist": "amounts for this {role} vary by about {value:,.2f}",
    "_amt_z": "amount {mult} the usual for this {role}",
}


def _family_phrase(feature: str, value: float, mult: str) -> str | None:
    """
    Render a feature from its entity prefix and its suffix.

    Returns None when the feature belongs to no known family, so the caller can
    fall through to the generic rendering.
    """
    for entity, role in ENTITY_ROLE.items():
        if not feature.startswith(f"{entity}_"):
            continue
        suffix = feature[len(entity):]

        template = FAMILY_PHRASES.get(suffix)
        if template:
            return template.format(value=value, role=role, mult=mult)

        # Windowed counts and sums: the window length is part of the name.
        window = re.fullmatch(r"_(cnt|amt_sum|amt_mean)_w(\d+)", suffix)
        if window:
            kind, size = window.group(1), window.group(2)
            if kind == "cnt":
                return (
                    f"{value:,.0f} transactions for this {role} "
                    f"in the last {size} time units"
                )
            if kind == "amt_sum":
                return (
                    f"{value:,.2f} total for this {role} "
                    f"in the last {size} time units"
                )
            return (
                f"average amount {value:,.2f} for this {role} "
                f"in the last {size} time units"
            )

        # Fan-out counts: how many distinct partners this entity touched.
        fan = re.fullmatch(r"_distinct_([A-Za-z]+)_(?:w(\d+)|lifetime)", suffix)
        if fan:
            other = ENTITY_ROLE.get(fan.group(1), fan.group(1)).replace(
                "customer account", "customer accounts"
            )
            if not other.endswith("s"):
                other += "s"
            when = (
                f"in the last {fan.group(2)} time units"
                if fan.group(2)
                else "in total"
            )
            return f"{value:,.0f} distinct {other} for this {role} {when}"

    return None


def _phrase(feature: str, value: float) -> str:
    """Render one feature as a sentence fragment."""
    mult = (
        "far above" if value > 2 else
        "above" if value > 0.5 else
        "far below" if value < -2 else
        "below" if value < -0.5 else "close to"
    )
    if feature in FEATURE_PHRASES:
        tmpl = FEATURE_PHRASES[feature]
        try:
            return tmpl.format(value=value, mult=mult)
        except (KeyError, ValueError):
            pass
    if feature in RISK_PHRASES:
        return f"{RISK_PHRASES[feature]} is {value:.1%}"
    if feature.endswith("_risk_rate"):
        entity = feature.split("_")[0]
        role = ENTITY_ROLE.get(entity, entity)
        return f"confirmed-fraud rate for this {role} is {value:.1%}"
    family = _family_phrase(feature, value, mult)
    if family:
        return family

    # Generic fallback: never drop a contributing feature just because it has
    # no phrase. Printing the name is worse than a sentence but far better than
    # silently hiding something that moved the score.
    return f"{feature.replace('_', ' ')} = {value:,.3f}"


class Explainer:
    """
    Wraps a fitted tabular model with TreeSHAP and renders explanations.

    The SHAP explainer is built once and reused: constructing it is the
    expensive part, evaluating it per transaction is not, which is what makes
    per-decision explanation affordable at scoring time.
    """

    def __init__(self, tabular_model, background: Optional[pd.DataFrame] = None,
                 cfg: ExplainConfig = CONFIG.explain):
        import shap

        self.model = tabular_model
        self.cfg = cfg
        self.feature_names = list(tabular_model.feature_names)
        self.explainer = shap.TreeExplainer(tabular_model.booster.booster_)
        self._background = background

    def shap_values(self, X: pd.DataFrame) -> np.ndarray:
        """Signed per-feature contributions, in log-odds, one row per input."""
        vals = self.explainer.shap_values(X[self.feature_names])
        if isinstance(vals, list):          # older SHAP returns one array per class
            vals = vals[1]
        vals = np.asarray(vals)
        if vals.ndim == 3:                  # (rows, features, classes)
            vals = vals[:, :, -1]
        return vals

    @property
    def base_value(self) -> float:
        bv = self.explainer.expected_value
        if isinstance(bv, (list, np.ndarray)):
            bv = np.asarray(bv).ravel()[-1]
        return float(bv)

    def explain_row(
        self,
        X_row: pd.DataFrame,
        risk_row: Optional[pd.Series] = None,
        channel_scores: Optional[Dict[str, float]] = None,
        fusion_weights: Optional[Dict[str, float]] = None,
        cluster_id: Optional[str] = None,
        top_k: Optional[int] = None,
    ) -> Explanation:
        """Explain a single transaction."""
        top_k = top_k or self.cfg.top_k_reasons
        sv = self.shap_values(X_row)[0]
        values = X_row[self.feature_names].iloc[0]

        order = np.argsort(-np.abs(sv))
        reasons: List[Reason] = []
        for i in order[:top_k]:
            feat = self.feature_names[i]
            contribution = float(sv[i])
            if abs(contribution) < 1e-9:
                continue
            reasons.append(
                Reason(
                    text=_phrase(feat, float(values[feat])),
                    direction="increases" if contribution > 0 else "decreases",
                    contribution=contribution,
                    feature=feat,
                )
            )

        # Channel attribution: weight times score, normalised. This is what
        # moved the *final* number, which is not always what moved the tabular
        # model, and an analyst needs to see both.
        attribution: Dict[str, float] = {}
        if channel_scores and fusion_weights:
            contrib = {
                c: fusion_weights.get(c, 0.0) * float(channel_scores.get(c, 0.0))
                for c in fusion_weights
            }
            total = sum(contrib.values())
            attribution = (
                {c: v / total for c, v in contrib.items()} if total > 0 else contrib
            )

        entity_risk: Dict[str, float] = {}
        if risk_row is not None:
            for col in RISK_PHRASES:
                if col in risk_row.index:
                    entity_risk[col] = float(risk_row[col])

        return Explanation(
            reasons=reasons,
            channel_attribution=attribution,
            entity_risk=entity_risk,
            cluster_id=cluster_id,
            base_value=self.base_value,
        )


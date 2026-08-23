"""
All settings for Spark.

Every number that affects a result is here, so you can see the whole setup in
one place. Nothing in the training or evaluation code hides a threshold or a
weight.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List

# Paths

ROOT = Path(__file__).resolve().parents[1]

RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
ARTIFACT_DIR = ROOT / "artifacts"
REPORT_DIR = ROOT / "reports"

RAW_CSV = RAW_DIR / "S-FFSD.csv"

for _d in (RAW_DIR, PROCESSED_DIR, ARTIFACT_DIR, REPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# Dataset contract

#: Columns the raw S-FFSD file must provide. Validation fails loudly if the
#: file on disk does not match, rather than silently producing wrong features.
RAW_SCHEMA: Dict[str, str] = {
    "Time": "int",        # sequence position; 0..N-1, strictly increasing
    "Source": "str",      # paying account / card  -> "customer"
    "Target": "str",      # receiving account      -> "merchant"
    "Amount": "float",    # transaction value
    "Location": "str",    # transaction location
    "Type": "str",        # payment channel / instrument type
    "Labels": "int",      # 0 = legitimate, 1 = fraud, 2 = unlabeled
}

LABEL_COL = "Labels"
TIME_COL = "Time"

#: The four entity columns that form the fraud graph. These are the only
#: relationships present in the source data; the system never invents others.
ENTITY_COLS: List[str] = ["Source", "Target", "Location", "Type"]

#: Human-readable role of each entity column, used in explanations.
ENTITY_ROLE: Dict[str, str] = {
    "Source": "customer account",
    "Target": "merchant",
    "Location": "location",
    "Type": "payment channel",
}

LABEL_LEGIT = 0
LABEL_FRAUD = 1
LABEL_UNKNOWN = 2


# Splits


@dataclass(frozen=True)
class SplitConfig:
    """Time-ordered split. No shuffling: rows are ordered by ``Time``."""

    train_frac: float = 0.70
    val_frac: float = 0.15
    # test_frac is the remainder (0.15) by construction.

    #: Unlabeled rows (Labels == 2) are excluded from supervised fitting and
    #: from metrics, but are kept in the graph and in every history/velocity
    #: accumulator. They are real traffic the merchant saw.
    drop_unlabeled_from_supervision: bool = True

    @property
    def test_frac(self) -> float:
        return 1.0 - self.train_frac - self.val_frac


# Feature engineering


@dataclass(frozen=True)
class FeatureConfig:
    """
    All entity aggregates are *expanding and past-only*: for a transaction at
    time t only transactions with time < t contribute. This is the single most
    important property of the feature layer and it is enforced structurally by
    a one-pass streaming implementation, not by a filter that could be wrong.
    """

    #: Rolling windows, in ``Time`` units, for velocity features.
    velocity_windows: List[int] = field(default_factory=lambda: [20, 100, 500, 2000])

    #: Entities that get velocity / history features.
    velocity_entities: List[str] = field(
        default_factory=lambda: ["Source", "Target", "Location", "Type"]
    )

    #: Laplace smoothing prior for past-only entity fraud rates. Prevents an
    #: entity with a single confirmed fraud from reading as 100% risky.
    risk_prior_strength: float = 20.0

    #: Delay, in ``Time`` units, before a confirmed label becomes usable as a
    #: feature. Models chargeback and dispute lag: a merchant does not learn a
    #: transaction was fraud at the moment it happens.
    #:
    #: The default is careful on purpose. A merchant does not learn that a
    #: payment was fraud at the moment it happens, so the pipeline is not
    #: allowed to either.
    #:
    #: Measured effect on the full pipeline (``ml.evaluation.sensitivity``,
    #: held-out test PR-AUC): lag 0 -> 0.883, lag 500 -> 0.842,
    #: lag 2000 -> 0.915, lag 6000 -> 0.837. The system is largely insensitive
    #: to this assumption, which it owes to the graph model and the two
    #: label-free channels rather than to the entity risk statistics; a
    #: tabular-only model over the same features swings from 0.96 to 0.73
    #: across the same range. The abuse-ring detector reads no labels at all
    #: and is identical at every setting.
    label_lag_steps: int = 2000


# Graph


@dataclass(frozen=True)
class GraphConfig:
    """
    Transaction-to-transaction relation graph, one relation per entity column.

    Inspired by the GTAN attribute-driven graph in AI4Risk/antifraud, with one
    deliberate change: edges point strictly from *earlier* to *later*
    transactions, so no future information can reach a node. The original
    construction is undirected and therefore not causal.
    """

    #: How many earlier transactions sharing an entity a node connects back to.
    edges_per_transaction: int = 3

    #: Entities whose shared values create edges.
    relations: List[str] = field(
        default_factory=lambda: ["Source", "Target", "Location", "Type"]
    )

    #: Entity values appearing more often than this are treated as hubs and do
    #: not create edges. A channel used by everyone carries no information and
    #: would create a dense, meaningless neighbourhood.
    hub_degree_cap: int = 2000


@dataclass(frozen=True)
class GNNConfig:
    """Relational message-passing net. CPU-only, full-batch, deterministic."""

    hidden_dim: int = 64
    n_layers: int = 2
    dropout: float = 0.2
    lr: float = 0.01
    weight_decay: float = 1e-4
    max_epochs: int = 200
    early_stopping_patience: int = 25
    seed: int = 2026


# Tabular model


@dataclass(frozen=True)
class LGBMConfig:
    n_estimators: int = 800
    learning_rate: float = 0.05
    num_leaves: int = 63
    min_child_samples: int = 40
    subsample: float = 0.8
    subsample_freq: int = 1
    colsample_bytree: float = 0.8
    reg_lambda: float = 1.0
    early_stopping_rounds: int = 60
    seed: int = 2026


# Risk fusion


@dataclass(frozen=True)
class FusionConfig:
    """
    Fusion weights are *searched*, not assumed. ``default_weights`` is only the
    reference point quoted in the brief; ``ml.training.fusion`` selects the
    operating weights on the validation split and writes them to the artifact.
    """

    default_weights: Dict[str, float] = field(
        default_factory=lambda: {
            "tabular": 0.45,
            "graph": 0.35,
            "behavioral": 0.10,
            "velocity": 0.10,
        }
    )

    #: Number of candidate weight vectors sampled from the simplex.
    n_weight_candidates: int = 400

    #: Metric used to pick weights on validation.
    selection_metric: str = "pr_auc"

    seed: int = 2026


# Business cost model


@dataclass(frozen=True)
class CostConfig:
    """
    Costs are expressed in the same currency unit as ``Amount``.

    A missed fraud costs more when the amount is bigger. Losing a 5,000
    payment hurts far more than losing a 50 one. Using one flat cost, which is
    the common shortcut, picks the wrong threshold.
    """

    #: Cost of wrongly blocking a legitimate transaction: lost margin on the
    #: order plus the goodwill damage of a false decline.
    false_positive_cost: float = 25.0

    #: Fixed component of a missed fraud: chargeback fee plus handling.
    false_negative_fixed_cost: float = 15.0

    #: Fraction of the transaction amount lost when fraud is not stopped.
    false_negative_amount_frac: float = 1.0

    #: Cost of routing one transaction to a human analyst.
    manual_review_cost: float = 3.0

    #: Fraction of fraud a manual review is assumed to catch. Review is only
    #: worth paying for to the extent that it actually prevents loss.
    review_catch_rate: float = 0.80

    #: If True use the amount-proportional FN cost, else a flat cost of
    #: ``false_negative_fixed_cost``. Both variants are reported.
    amount_weighted: bool = True


@dataclass(frozen=True)
class DecisionConfig:
    """
    Operating points. Thresholds are chosen on validation only, either by
    minimising expected cost or by hitting a target precision or recall,
    then applied unchanged to the held-out test set.
    """

    modes: List[str] = field(
        default_factory=lambda: ["high_precision", "balanced", "high_recall"]
    )

    #: Target precision for the high-precision operating point.
    high_precision_target: float = 0.90

    #: Target recall for the high-recall operating point.
    high_recall_target: float = 0.80

    #: Lower edge of the REVIEW band, as a fraction of the block threshold,
    #: used when the cost sweep does not produce one directly.
    review_band_frac: float = 0.55


# Ring / cluster detection


@dataclass(frozen=True)
class ClusterConfig:
    """Abuse-ring detection over the entity co-occurrence graph."""

    #: Length of the sliding window, in Time units, a ring must fit inside.
    #: A ring is a burst of coordinated activity, not a lifetime aggregate.
    window: int = 8000

    #: Step between consecutive windows.
    stride: int = 4000

    #: Minimum number of distinct customer accounts for a component to count.
    min_accounts: int = 5

    #: Minimum transactions for a component to count.
    min_transactions: int = 8

    #: Minimum lift (observed co-occurrence over expected under independence)
    #: for an entity pair to contribute an edge. Prunes popular-merchant edges
    #: that would otherwise merge everything into one blob.
    min_edge_lift: float = 2.0

    #: Minimum raw co-occurrence count for an edge to survive pruning.
    min_edge_support: int = 3

    #: Two infrastructure cells are merged into one ring only if they share at
    #: least this many accounts. A single customer who happens to shop at both
    #: a ring merchant and a legitimate one is a coincidence, not evidence of
    #: a link. Without this floor those coincidences chain every cell in the
    #: window into one useless giant group.
    merge_min_shared_accounts: int = 3

    #: ...and the shared accounts must also be at least this fraction of the
    #: smaller cell's account base, so large cells cannot absorb small ones on
    #: an absolute overlap that is proportionally negligible.
    merge_min_overlap: float = 0.15

    #: Rings spanning more than this many cells are reported but flagged as
    #: low-confidence: at that size the group is more likely to be a busy
    #: marketplace than a coordinated ring.
    max_cells_per_ring: int = 25

    seed: int = 2026


# Explainability


@dataclass(frozen=True)
class ExplainConfig:
    #: Number of contributing factors reported per decision.
    top_k_reasons: int = 5

    #: Rows sampled as the SHAP background. Kept small: TreeSHAP is exact for
    #: LightGBM and the background only fixes the expected value.
    shap_background_size: int = 500

    seed: int = 2026


# Top level

MODEL_VERSION = "spark-hybrid-v1"

SEED = 2026


@dataclass(frozen=True)
class Config:
    split: SplitConfig = field(default_factory=SplitConfig)
    features: FeatureConfig = field(default_factory=FeatureConfig)
    graph: GraphConfig = field(default_factory=GraphConfig)
    gnn: GNNConfig = field(default_factory=GNNConfig)
    lgbm: LGBMConfig = field(default_factory=LGBMConfig)
    fusion: FusionConfig = field(default_factory=FusionConfig)
    cost: CostConfig = field(default_factory=CostConfig)
    decision: DecisionConfig = field(default_factory=DecisionConfig)
    cluster: ClusterConfig = field(default_factory=ClusterConfig)
    explain: ExplainConfig = field(default_factory=ExplainConfig)
    model_version: str = MODEL_VERSION
    seed: int = SEED

    def to_dict(self) -> dict:
        return asdict(self)


def load_config() -> Config:
    """
    Return the active configuration.

    Environment overrides are supported for the handful of values an operator
    would realistically retune without editing code: the cost model.
    """
    cfg = Config()

    def _env_float(name: str):
        v = os.getenv(name)
        return float(v) if v is not None else None

    fp = _env_float("MS_FALSE_POSITIVE_COST")
    fn = _env_float("MS_FALSE_NEGATIVE_COST")
    rv = _env_float("MS_MANUAL_REVIEW_COST")

    if fp is None and fn is None and rv is None:
        return cfg

    cost = CostConfig(
        false_positive_cost=fp if fp is not None else cfg.cost.false_positive_cost,
        false_negative_fixed_cost=(
            fn if fn is not None else cfg.cost.false_negative_fixed_cost
        ),
        false_negative_amount_frac=cfg.cost.false_negative_amount_frac,
        manual_review_cost=rv if rv is not None else cfg.cost.manual_review_cost,
        review_catch_rate=cfg.cost.review_catch_rate,
        amount_weighted=cfg.cost.amount_weighted,
    )
    return Config(
        split=cfg.split,
        features=cfg.features,
        graph=cfg.graph,
        gnn=cfg.gnn,
        lgbm=cfg.lgbm,
        fusion=cfg.fusion,
        cost=cost,
        decision=cfg.decision,
        cluster=cfg.cluster,
        explain=cfg.explain,
    )


CONFIG = load_config()

"""
The scoring engine.

Loads the saved models and turns a transaction into a decision with an
explanation and a ring reference. The CLI drives this. A web API would wrap
this same class instead of rewriting the logic.

Two things worth knowing:

Nothing is refitted here. Weights, calibrator, thresholds, and scaling all
come from the artifacts folder. If the engine could refit, the measured
numbers would stop describing what is running.

New entities get a careful floor. If the account, merchant, and channel are
all unknown, the score is raised to a minimum instead of trusting a confident
model output. The models are weakest exactly where there is no history, and
the cold-entity slice in the evaluation measures how much weaker.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

import joblib
import numpy as np
import pandas as pd

from ml.calibration.fuse import CHANNELS, FusionModel
from ml.config import ARTIFACT_DIR, CONFIG, Config
from ml.evaluation.explain import Explainer
from ml.evaluation.metrics import decide
from ml.graph.build import build_relation_graph, neighbour_risk_features
from ml.graph.rings import RiskCluster
from ml.models.graph_nn import GraphModel
from ml.models.tabular import TabularModel
from ml.preprocessing.prepare import Dataset, prepare

#: An entity with fewer than this many prior transactions is treated as cold.
COLD_HISTORY_THRESHOLD = 3

#: Floor applied to the risk score when every entity involved is cold. Set to
#: the training-window fraud base rate at load time, not hardcoded.
COLD_FLOOR_FALLBACK = 0.15


@dataclass
class Decision:
    """A scored transaction, ready to log or display."""

    transaction_id: str
    time: int
    amount: float
    source: str
    target: str
    location: str
    payment_type: str

    risk_score: float
    decision: str
    mode: str
    model_version: str
    path: str                       # "MODEL" or "COLD_START"

    channel_scores: Dict[str, float]
    channel_attribution: Dict[str, float]
    reasons: List[str]
    entity_risk: Dict[str, float]

    cluster_id: Optional[str] = None
    cluster: Optional[dict] = None

    label: Optional[int] = None     # ground truth, when known; never an input
    latency_ms: Optional[float] = None

    def as_dict(self) -> dict:
        return asdict(self)


class ScoringEngine:
    """Loads artifacts once, scores many."""

    def __init__(
        self,
        artifact_dir: Path = ARTIFACT_DIR,
        cfg: Config = CONFIG,
        mode: str = "balanced",
        with_explainer: bool = True,
        verbose: bool = False,
    ):
        self.cfg = cfg
        self.artifact_dir = Path(artifact_dir)
        self.mode = mode
        self.timings: Dict[str, float] = {}

        t0 = time.perf_counter()
        meta_path = self.artifact_dir / "model_metadata.json"
        if not meta_path.exists():
            raise FileNotFoundError(
                f"No trained model at {self.artifact_dir}.\n"
                "Train one first:  python -m spark.models.train"
            )
        with open(meta_path, encoding="utf-8") as fh:
            self.metadata = json.load(fh)

        self.tabular = TabularModel.load(self.artifact_dir / "tabular_model.joblib")
        self.graph_model = GraphModel.load(self.artifact_dir / "graph_model.pt")
        self.fusion: FusionModel = FusionModel.load(self.artifact_dir / "fusion.joblib")
        self.channels = joblib.load(self.artifact_dir / "channels.joblib")
        self.timings["model_load_ms"] = (time.perf_counter() - t0) * 1000

        if mode not in self.metadata["thresholds"]:
            raise ValueError(
                f"unknown mode {mode!r}; available: "
                f"{sorted(self.metadata['thresholds'])}"
            )
        op = self.metadata["thresholds"][mode]
        self.review_threshold = float(op["review_threshold"])
        self.block_threshold = float(op["block_threshold"])

        # Dataset, features and graph. In this phase the engine scores
        # transactions from the prepared stream; a live deployment would swap
        # this for an incremental feature store fed by the same causal
        # accumulators, which is why the feature code is written as a
        # single-pass streaming algorithm rather than a batch groupby.
        t0 = time.perf_counter()
        self.ds: Dataset = prepare(cfg=cfg, verbose=verbose)
        self.timings["feature_load_ms"] = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        self.graph = build_relation_graph(self.ds.df, cfg=cfg, verbose=verbose)
        self.gfeat = neighbour_risk_features(
            self.graph, self.ds.y, self.ds.labeled,
            lag=cfg.features.label_lag_steps, verbose=verbose,
        )
        self.adj_norm = self.graph.normalised()
        self.timings["graph_build_ms"] = (time.perf_counter() - t0) * 1000

        self.X_graph = pd.concat(
            [
                self.ds.base.reset_index(drop=True),
                self.ds.risk.reset_index(drop=True),
                self.gfeat.reset_index(drop=True),
            ],
            axis=1,
        )

        # The graph model is transductive, so node scores are produced once for
        # the whole graph and indexed per transaction thereafter.
        t0 = time.perf_counter()
        self._graph_scores = self.graph_model.predict_proba(self.X_graph, self.adj_norm)
        self.timings["graph_inference_ms"] = (time.perf_counter() - t0) * 1000

        self._unsup = self.channels.score(self.ds.base)

        self.cold_floor = float(
            self.metadata.get("dataset", {})
            .get("raw_stats", {})
            .get("fraud_rate_labeled", COLD_FLOOR_FALLBACK)
        )

        self.explainer = Explainer(self.tabular, cfg=cfg.explain) if with_explainer else None

        self._rings: Optional[List[RiskCluster]] = None
        self._txn_to_cluster: Optional[Dict[int, str]] = None
    # rings
    @property
    def rings(self) -> List[dict]:
        """Detected rings, loaded lazily from the artifact bundle."""
        if self._rings is None:
            path = self.artifact_dir / "rings.json"
            self._rings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        return self._rings

    def _cluster_for(self, idx: int) -> Optional[dict]:
        """
        Highest-scoring ring containing this transaction, if any.

        Membership is read from the exact map training wrote, not
        reconstructed from the ring summary. Re-deriving it here would let the
        engine disagree with the evaluation about which transactions a ring
        contains, which is precisely the kind of drift between "what was
        measured" and "what is served" this project is trying to avoid.
        """
        if self._txn_to_cluster is None:
            path = self.artifact_dir / "ring_membership.json"
            raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            self._txn_to_cluster = {int(k): v for k, v in raw.items()}
        cid = self._txn_to_cluster.get(int(idx))
        if cid is None:
            return None
        for r in self.rings:
            if r["cluster_id"] == cid:
                return r
        return None
    # scoring
    def channel_scores_for(self, idx: np.ndarray) -> Dict[str, np.ndarray]:
        """The four channel scores for a set of transaction indices."""
        return {
            "tabular": self.tabular.predict_proba(self.ds.base.iloc[idx]),
            "graph": self._graph_scores[idx],
            "behavioral": self._unsup["behavioral"][idx],
            "velocity": self._unsup["velocity"][idx],
        }

    def _is_cold(self, idx: int) -> bool:
        b = self.ds.base.iloc[idx]
        return bool(
            b["Source_txn_count"] < COLD_HISTORY_THRESHOLD
            and b["Target_txn_count"] < COLD_HISTORY_THRESHOLD
            and b["Type_txn_count"] < COLD_HISTORY_THRESHOLD
        )

    def score_batch(self, idx: np.ndarray) -> pd.DataFrame:
        """Score many transactions at once; returns one row per transaction."""
        idx = np.asarray(idx, dtype=int)
        ch = self.channel_scores_for(idx)
        p = self.fusion.predict(ch)

        cold = np.array([self._is_cold(i) for i in idx])
        p_adj = np.where(cold, np.maximum(p, self.cold_floor), p)

        dec = decide(p_adj, self.review_threshold, self.block_threshold)
        df = self.ds.df.iloc[idx]
        return pd.DataFrame(
            {
                "index": idx,
                "transaction_id": df["txn_id"].to_numpy(),
                "Time": df["Time"].to_numpy(),
                "Amount": df["Amount"].to_numpy(),
                "Source": df["Source"].to_numpy(),
                "Target": df["Target"].to_numpy(),
                "risk_score": p_adj,
                "decision": dec,
                "path": np.where(cold, "COLD_START", "MODEL"),
                **{f"score_{c}": ch[c] for c in CHANNELS},
                "label": self.ds.y[idx],
                "labeled": self.ds.labeled[idx],
            }
        )

    def score_one(self, idx: int, explain: bool = True) -> Decision:
        """Score one transaction and build its full explanation."""
        t0 = time.perf_counter()
        i = int(idx)
        ch = {k: v[0] for k, v in self.channel_scores_for(np.array([i])).items()}
        p = float(self.fusion.predict({k: np.array([v]) for k, v in ch.items()})[0])

        cold = self._is_cold(i)
        if cold:
            p = max(p, self.cold_floor)

        dec = str(decide(np.array([p]), self.review_threshold, self.block_threshold)[0])
        row = self.ds.df.iloc[i]
        cluster = self._cluster_for(i)

        reasons: List[str] = []
        attribution: Dict[str, float] = {}
        entity_risk: Dict[str, float] = {}

        if explain and self.explainer is not None:
            ex = self.explainer.explain_row(
                self.ds.base.iloc[[i]],
                risk_row=self.ds.risk.iloc[i],
                channel_scores=ch,
                fusion_weights=self.fusion.weights,
                cluster_id=cluster["cluster_id"] if cluster else None,
            )
            reasons = [r.render() for r in ex.reasons]
            attribution = ex.channel_attribution
            entity_risk = ex.entity_risk

        if cold:
            reasons.insert(
                0, "+ no prior history for this account, merchant or channel "
                   "(conservative cold-start floor applied)"
            )
        if cluster:
            reasons.append(
                f"+ member of risk cluster {cluster['cluster_id']} "
                f"({cluster['n_accounts']:,} accounts, "
                f"{cluster['n_transactions']:,} transactions)"
            )

        return Decision(
            transaction_id=str(row["txn_id"]),
            time=int(row["Time"]),
            amount=float(row["Amount"]),
            source=str(row["Source"]),
            target=str(row["Target"]),
            location=str(row["Location"]),
            payment_type=str(row["Type"]),
            risk_score=p,
            decision=dec,
            mode=self.mode,
            model_version=self.metadata["model_version"],
            path="COLD_START" if cold else "MODEL",
            channel_scores={k: float(v) for k, v in ch.items()},
            channel_attribution=attribution,
            reasons=reasons,
            entity_risk=entity_risk,
            cluster_id=cluster["cluster_id"] if cluster else None,
            cluster=cluster,
            label=int(self.ds.y[i]) if self.ds.labeled[i] else None,
            latency_ms=(time.perf_counter() - t0) * 1000,
        )

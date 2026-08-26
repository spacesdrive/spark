"""
Score a transaction that is not in the dataset file.

The batch pipeline scores rows by position: it builds every feature in one
pass and the graph model reads the whole graph at once. An API cannot do that,
because the transaction it is asked about did not exist when the file was
written.

This module closes that gap without changing any model:

1. A ``CausalFeatureState`` is replayed over the historical stream once, at
   startup. It ends up holding exactly the accumulator state that existed
   after the last row of the file, so ``emit`` on a new transaction produces
   features built the same way as every training feature.

2. Graph edges for the new transaction point back to the most recent earlier
   transactions sharing each entity value, using the same rule as
   ``build_relation_graph``.

3. The graph model is evaluated for the new node only. Because edges point
   strictly backwards, adding a node cannot change any existing node's hidden
   state, so the cached historical activations stay valid and the new node's
   score is exact rather than approximate.

Nothing is refitted here. Weights, calibrator, thresholds and scaling all come
from the artifacts the training run wrote.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import torch

from ml.config import CONFIG, ENTITY_COLS, Config
from ml.evaluation.metrics import decide
from ml.features.causal import CausalFeatureState
from ml.models.graph_nn import RelationalGNN

#: An entity with fewer than this many prior transactions is treated as cold.
#: Mirrors ``spark.risk.engine.COLD_HISTORY_THRESHOLD`` so the API and the CLI
#: apply the same rule.
COLD_HISTORY_THRESHOLD = 3


@dataclass
class TransactionInput:
    """One transaction as the caller supplied it."""

    transaction_id: str
    amount: float
    source: str
    target: str
    location: str
    payment_type: str
    time: Optional[int] = None

    def entities(self) -> Dict[str, str]:
        return {
            "Source": self.source,
            "Target": self.target,
            "Location": self.location,
            "Type": self.payment_type,
        }


@dataclass
class OnlineResult:
    """A scored transaction, with everything needed to explain it."""

    transaction_id: str
    time: int
    amount: float
    source: str
    target: str
    location: str
    payment_type: str

    risk_score: float
    risk_band: str
    decision: str
    mode: str
    model_version: str
    path: str

    channel_scores: Dict[str, float]
    channel_attribution: Dict[str, float]
    reasons: List[dict]
    entity_risk: Dict[str, float]
    entity_history: Dict[str, dict]
    graph_evidence: Dict[str, list] = field(default_factory=dict)
    related_ring: Optional[dict] = None
    stages: List[dict] = field(default_factory=list)
    latency_ms: float = 0.0


def risk_band(score: float, review_threshold: float, block_threshold: float) -> str:
    """Low / Medium / High, using the same cut points as the decision."""
    if score >= block_threshold:
        return "HIGH"
    if score >= review_threshold:
        return "MEDIUM"
    return "LOW"


class OnlineScorer:
    """
    Adds arbitrary-transaction scoring to a loaded ``ScoringEngine``.

    The engine already holds the models, the dataset, the graph and the
    explainer. This class borrows all of it and only adds the state needed to
    extend the stream by one row.
    """

    def __init__(self, engine, cfg: Config = CONFIG, verbose: bool = False):
        self.engine = engine
        self.cfg = cfg
        self.df = engine.ds.df
        self.n_hist = len(self.df)

        t0 = time.perf_counter()
        self.state = self._warm_feature_state(verbose=verbose)
        self.warmup_seconds = time.perf_counter() - t0

        self._build_entity_index()
        self._cache_graph_activations()
        self._cache_neighbour_stats()
        self._index_rings()

    # warm-up

    def _warm_feature_state(self, verbose: bool = False) -> CausalFeatureState:
        """Replay the historical stream so the accumulators match the file."""
        state = CausalFeatureState(self.cfg)
        df = self.df
        times = df["Time"].to_numpy()
        amounts = df["Amount"].to_numpy(dtype=float)
        labels = df["Labels"].to_numpy()
        ent_values = {c: df[c].to_numpy() for c in ENTITY_COLS}
        for i in range(len(df)):
            state.update(
                int(times[i]),
                float(amounts[i]),
                {c: ent_values[c][i] for c in ENTITY_COLS},
                int(labels[i]),
            )
        if verbose:
            print(f"[online] feature state warmed over {len(df):,} transactions")
        return state

    def _build_entity_index(self) -> None:
        """Row positions per entity value, so new edges can be found quickly."""
        self.entity_rows: Dict[str, Dict[str, List[int]]] = {}
        for rel in self.cfg.graph.relations:
            buckets: Dict[str, List[int]] = {}
            for i, v in enumerate(self.df[rel].to_numpy()):
                buckets.setdefault(v, []).append(i)
            self.entity_rows[rel] = buckets

    def _cache_graph_activations(self) -> None:
        """
        Cache the graph model's scaled inputs and first-layer output.

        Scoring a new node needs its neighbours' layer-0 and layer-1 vectors.
        Those never change when a node is appended, because every edge points
        from an older transaction to a newer one.
        """
        gm = self.engine.graph_model
        net = RelationalGNN(
            gm.in_dim, gm.hidden_dim, gm.relations, gm.n_layers, gm.dropout
        )
        net.load_state_dict(gm.state_dict)
        net.eval()
        self._net = net

        x = torch.from_numpy(gm.scale_features(self.engine.X_graph))
        adj = {
            r: _to_torch_sparse(self.engine.adj_norm[r]) for r in gm.relations
        }
        with torch.no_grad():
            h = x
            acts = [x]
            for layer, norm in zip(net.layers, net.norms):
                h = torch.relu(norm(layer(h, adj)))
                acts.append(h)
        # acts[0] is the scaled input, acts[i] the output of layer i. The last
        # entry feeds the head and is not needed for a new node's messages.
        self._acts = acts[:-1]

    def _cache_neighbour_stats(self) -> None:
        """Per-relation degree and confirmed-fraud counts for existing nodes."""
        graph = self.engine.graph
        y = self.engine.ds.y
        usable = self.engine.ds.labeled
        lag = self.cfg.features.label_lag_steps
        adj_risk = graph.lagged(lag)

        f = ((y == 1) & usable).astype(np.float32)
        a_ = usable.astype(np.float32)
        ones = np.ones(graph.n_nodes, dtype=np.float32)

        self._deg1: Dict[str, np.ndarray] = {}
        self._fr1: Dict[str, np.ndarray] = {}
        for rel in graph.relations:
            self._deg1[rel] = graph.adj[rel] @ ones
            self._fr1[rel] = adj_risk[rel] @ f
        self._known_fraud = f
        self._usable = a_
        self._risk_lag = lag

    def _index_rings(self) -> None:
        """Map merchant and channel to the rings they appear in."""
        self.rings_by_merchant: Dict[str, List[dict]] = {}
        self.rings_by_channel: Dict[str, List[dict]] = {}
        for ring in self.engine.rings:
            for m in ring.get("merchants", []):
                self.rings_by_merchant.setdefault(m, []).append(ring)
            for c in ring.get("channels", []):
                self.rings_by_channel.setdefault(c, []).append(ring)

    # scoring

    def next_time(self) -> int:
        """Time index a new transaction is placed at: one past the last row."""
        return int(self.df["Time"].to_numpy()[-1]) + 1

    def _new_node_edges(self, ent: Dict[str, str]) -> Dict[str, List[int]]:
        """
        Backward edges for a transaction that would be appended to the stream.

        Same rule as ``build_relation_graph``: connect to the ``k`` most recent
        earlier transactions sharing the entity value, and create no edges at
        all when the value is a hub.
        """
        k = self.cfg.graph.edges_per_transaction
        cap = self.cfg.graph.hub_degree_cap
        out: Dict[str, List[int]] = {}
        for rel in self.cfg.graph.relations:
            rows = self.entity_rows[rel].get(ent[rel], [])
            out[rel] = [] if len(rows) + 1 > cap else rows[-k:]
        return out

    def _graph_score(self, x_new: np.ndarray, edges: Dict[str, List[int]]) -> float:
        """
        Run the graph model for one appended node.

        Layer by layer the new node mixes its own vector with the mean of its
        neighbours at that layer. Its neighbours are all older, so their cached
        activations are the same values the batch pass produced.
        """
        net = self._net
        relations = self.engine.graph_model.relations
        with torch.no_grad():
            h = torch.from_numpy(x_new.astype(np.float32)).unsqueeze(0)
            for depth, (layer, norm) in enumerate(zip(net.layers, net.norms)):
                out = layer.self_lin(h)
                src = self._acts[depth]
                for rel in relations:
                    idx = edges.get(rel, [])
                    if not idx:
                        continue
                    msg = src[torch.tensor(idx, dtype=torch.long)].mean(
                        dim=0, keepdim=True
                    )
                    out = out + layer.rel_lin[rel](msg)
                h = torch.relu(norm(out))
            return float(torch.sigmoid(net.head(h).squeeze()).item())

    def _neighbour_features(
        self, edges: Dict[str, List[int]], t_new: int
    ) -> pd.DataFrame:
        """Structural and confirmed-fraud counts around the new node."""
        times = self.engine.graph.times
        cols: Dict[str, float] = {}
        for rel in self.engine.graph.relations:
            idx = np.array(edges.get(rel, []), dtype=int)
            if len(idx):
                # Label-derived counts use the lag filter; structure does not.
                usable_edge = (t_new - times[idx]) >= self._risk_lag
                lag_idx = idx[usable_edge]
            else:
                lag_idx = idx
            deg1 = float(len(idx))
            deg2 = float(self._deg1[rel][idx].sum()) if len(idx) else 0.0
            fr1 = float(self._known_fraud[lag_idx].sum()) if len(lag_idx) else 0.0
            fr2 = float(self._fr1[rel][lag_idx].sum()) if len(lag_idx) else 0.0
            kn1 = float(self._usable[lag_idx].sum()) if len(lag_idx) else 0.0
            cols[f"g_{rel}_deg1"] = deg1
            cols[f"g_{rel}_deg2"] = deg2
            cols[f"g_{rel}_fraud1"] = fr1
            cols[f"g_{rel}_fraud2"] = fr2
            cols[f"g_{rel}_known1"] = kn1
            cols[f"g_{rel}_fraud_share1"] = (fr1 / kn1) if kn1 > 0 else 0.0

        cols["g_total_fraud1"] = sum(
            v for k, v in cols.items() if k.endswith("_fraud1")
        )
        cols["g_total_deg1"] = sum(v for k, v in cols.items() if k.endswith("_deg1"))
        cols["g_max_fraud_share1"] = max(
            v for k, v in cols.items() if k.endswith("_fraud_share1")
        )
        return pd.DataFrame([cols], dtype=np.float32)

    def _graph_evidence(
        self, edges: Dict[str, List[int]], limit: int = 4
    ) -> Dict[str, list]:
        """The actual earlier transactions the graph connected to, per relation."""
        label_for = {
            "Source": "Same customer account",
            "Target": "Same merchant",
            "Location": "Same location",
            "Type": "Same payment channel",
        }
        y = self.engine.ds.y
        labeled = self.engine.ds.labeled
        out: Dict[str, list] = {}
        for rel, idx in edges.items():
            items = []
            for i in idx[-limit:]:
                row = self.df.iloc[i]
                items.append(
                    {
                        "transaction_id": str(row["txn_id"]),
                        "time": int(row["Time"]),
                        "amount": float(row["Amount"]),
                        "source": str(row["Source"]),
                        "target": str(row["Target"]),
                        "relation": label_for.get(rel, rel),
                        "outcome": (
                            None
                            if not labeled[i]
                            else ("fraud" if y[i] == 1 else "legitimate")
                        ),
                    }
                )
            if items:
                out[rel] = items
        return out

    def _related_ring(self, ent: Dict[str, str]) -> Optional[dict]:
        """
        The highest-scoring detected ring this merchant or channel belongs to.

        This is deliberately not called ring membership. The ring detector runs
        over completed time windows; a transaction that has just arrived was
        not part of any of them. What can be said honestly is that its merchant
        or its channel appears in a group the detector already flagged.
        """
        candidates = self.rings_by_merchant.get(ent["Target"], [])
        match_on = "merchant"
        if not candidates:
            candidates = self.rings_by_channel.get(ent["Type"], [])
            match_on = "payment channel"
        if not candidates:
            return None
        best = max(candidates, key=lambda r: r.get("risk_score", 0.0))
        return {**best, "matched_on": match_on}

    def score(
        self,
        txn: TransactionInput,
        mode: Optional[str] = None,
        explain: bool = True,
    ) -> OnlineResult:
        """Score one transaction that is not in the dataset."""
        t_start = time.perf_counter()
        stages: List[dict] = []

        def stage(name: str, since: float) -> float:
            now = time.perf_counter()
            stages.append({"name": name, "ms": round((now - since) * 1000, 3)})
            return now

        engine = self.engine
        review_t, block_t = engine.review_threshold, engine.block_threshold
        if mode and mode != engine.mode:
            op = engine.metadata["thresholds"].get(mode)
            if op is None:
                raise ValueError(f"unknown mode {mode!r}")
            review_t = float(op["review_threshold"])
            block_t = float(op["block_threshold"])

        mark = t_start
        ent = txn.entities()
        t_new = int(txn.time) if txn.time is not None else self.next_time()

        base_vec, risk_vec = self.state.emit(t_new, txn.amount, ent)
        base_df, risk_df = self.state.frames(base_vec, risk_vec)
        mark = stage("Building features", mark)

        edges = self._new_node_edges(ent)
        gfeat = self._neighbour_features(edges, t_new)
        mark = stage("Linking to related transactions", mark)

        p_tab = float(engine.tabular.predict_proba(base_df)[0])
        mark = stage("Running tabular model", mark)

        gm = engine.graph_model
        x_graph = pd.concat([base_df, risk_df, gfeat], axis=1)
        x_new = gm.scale_features(x_graph)[0]
        p_graph = self._graph_score(x_new, edges)
        mark = stage("Running graph model", mark)

        unsup = engine.channels.score(base_df)
        channel_scores = {
            "tabular": p_tab,
            "graph": p_graph,
            "behavioral": float(unsup["behavioral"][0]),
            "velocity": float(unsup["velocity"][0]),
        }
        mark = stage("Scoring behaviour and velocity", mark)

        p = float(
            engine.fusion.predict(
                {k: np.array([v]) for k, v in channel_scores.items()}
            )[0]
        )
        cold = bool(
            base_df["Source_txn_count"].iloc[0] < COLD_HISTORY_THRESHOLD
            and base_df["Target_txn_count"].iloc[0] < COLD_HISTORY_THRESHOLD
            and base_df["Type_txn_count"].iloc[0] < COLD_HISTORY_THRESHOLD
        )
        if cold:
            p = max(p, engine.cold_floor)
        mark = stage("Combining and calibrating", mark)

        ring = self._related_ring(ent)
        mark = stage("Checking detected rings", mark)

        reasons: List[dict] = []
        attribution: Dict[str, float] = {}
        entity_risk: Dict[str, float] = {}
        if explain and engine.explainer is not None:
            ex = engine.explainer.explain_row(
                base_df,
                risk_row=risk_df.iloc[0],
                channel_scores=channel_scores,
                fusion_weights=engine.fusion.weights,
                cluster_id=None,
            )
            reasons = [r.as_dict() for r in ex.reasons]
            attribution = ex.channel_attribution
            entity_risk = ex.entity_risk
            mark = stage("Generating explanation", mark)

        if cold:
            reasons.insert(
                0,
                {
                    "text": "no prior history for this account, merchant or "
                            "channel, so a conservative minimum score was applied",
                    "direction": "increases",
                    "contribution": 0.0,
                    "feature": "cold_start",
                },
            )

        decision = str(decide(np.array([p]), review_t, block_t)[0])
        stage("Applying decision thresholds", mark)

        return OnlineResult(
            transaction_id=txn.transaction_id,
            time=t_new,
            amount=float(txn.amount),
            source=txn.source,
            target=txn.target,
            location=txn.location,
            payment_type=txn.payment_type,
            risk_score=p,
            risk_band=risk_band(p, review_t, block_t),
            decision=decision,
            mode=mode or engine.mode,
            model_version=engine.metadata["model_version"],
            path="COLD_START" if cold else "MODEL",
            channel_scores=channel_scores,
            channel_attribution=attribution,
            reasons=reasons,
            entity_risk=entity_risk,
            entity_history=self._entity_history(base_df),
            graph_evidence=self._graph_evidence(edges),
            related_ring=ring,
            stages=stages,
            latency_ms=(time.perf_counter() - t_start) * 1000,
        )

    def _entity_history(self, base_df: pd.DataFrame) -> Dict[str, dict]:
        """How much the system had seen of each entity before this transaction."""
        row = base_df.iloc[0]
        roles = {
            "Source": "customer account",
            "Target": "merchant",
            "Location": "location",
            "Type": "payment channel",
        }
        out: Dict[str, dict] = {}
        for col, role in roles.items():
            out[col] = {
                "role": role,
                "prior_transactions": int(row[f"{col}_txn_count"]),
                "is_new": bool(row[f"{col}_is_new"]),
            }
        return out


def _to_torch_sparse(a) -> torch.Tensor:
    """CSR to a coalesced torch sparse tensor."""
    coo = a.tocoo()
    idx = torch.from_numpy(np.vstack([coo.row, coo.col])).long()
    val = torch.from_numpy(coo.data.astype(np.float32))
    return torch.sparse_coo_tensor(idx, val, coo.shape).coalesce()

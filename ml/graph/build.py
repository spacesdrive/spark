"""
Build a graph of transactions.

Each transaction is a node. Two transactions are connected if they share the
same customer, merchant, location, or payment channel.

Two rules keep the graph useful:

1. Edges only point from older to newer transactions. A transaction can look
   at its past, never at its future.

2. Very common values do not create edges. One location covers 16,812
   transactions here. Linking every pair that shares it would add millions of
   edges that only say "both of these are transactions".
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List

import numpy as np
import pandas as pd
import scipy.sparse as sp

from ml.config import CONFIG, TIME_COL, Config


@dataclass
class RelationGraph:
    """One sparse adjacency per relation, plus the bookkeeping to explain it."""

    n_nodes: int
    relations: List[str]
    adj: Dict[str, sp.csr_matrix]          # row = receiver, col = sender
    edge_counts: Dict[str, int]
    skipped_hubs: Dict[str, int]
    times: np.ndarray                      # node time, for lag-aware masking

    @property
    def total_edges(self) -> int:
        return int(sum(self.edge_counts.values()))

    def normalised(self) -> Dict[str, sp.csr_matrix]:
        """
        Row-normalised adjacencies, so message passing averages over
        neighbours instead of summing. Without this, a node with 3 neighbours
        and a node with 300 produce activations on completely different scales
        and the network spends its capacity undoing that.
        """
        out = {}
        for rel, a in self.adj.items():
            deg = np.asarray(a.sum(axis=1)).ravel()
            deg[deg == 0] = 1.0
            dinv = sp.diags(1.0 / deg)
            out[rel] = (dinv @ a).tocsr().astype(np.float32)
        return out

    def lagged(self, lag: int) -> Dict[str, sp.csr_matrix]:
        """
        Adjacency keeping only edges whose sender is at least ``lag`` time
        units older than the receiver.

        Used for the label-derived neighbour features. An edge surviving this
        filter is one where the sender's outcome would plausibly have been
        confirmed (charged back, disputed, or written off) by the time the
        receiver needed scoring. With ``lag == 0`` nothing is removed and the
        features assume instant confirmation, which is optimistic; raising it
        is how the sensitivity analysis prices that optimism.
        """
        if lag <= 0:
            return dict(self.adj)
        out = {}
        for rel, a in self.adj.items():
            coo = a.tocoo()
            keep = (self.times[coo.row] - self.times[coo.col]) >= lag
            out[rel] = sp.csr_matrix(
                (coo.data[keep], (coo.row[keep], coo.col[keep])), shape=a.shape
            )
        return out

    def describe(self) -> pd.DataFrame:
        rows = []
        for rel in self.relations:
            a = self.adj[rel]
            deg = np.asarray(a.sum(axis=1)).ravel()
            rows.append(
                {
                    "relation": rel,
                    "edges": self.edge_counts[rel],
                    "hub_values_skipped": self.skipped_hubs[rel],
                    "mean_in_degree": float(deg.mean()),
                    "max_in_degree": int(deg.max()) if len(deg) else 0,
                    "isolated_nodes": int((deg == 0).sum()),
                }
            )
        return pd.DataFrame(rows)


def build_relation_graph(
    df: pd.DataFrame, cfg: Config = CONFIG, verbose: bool = True
) -> RelationGraph:
    """
    Build the backward-in-time relation graph over transactions.

    ``df`` must be sorted by time with a dense index; node id == row position.
    """
    gcfg = cfg.graph
    n = len(df)
    k = gcfg.edges_per_transaction
    cap = gcfg.hub_degree_cap

    adj: Dict[str, sp.csr_matrix] = {}
    edge_counts: Dict[str, int] = {}
    skipped: Dict[str, int] = {}

    if verbose:
        print(f"[graph] building {len(gcfg.relations)} relations over {n:,} nodes "
              f"(k={k}, hub_cap={cap})")

    for rel in gcfg.relations:
        values = df[rel].to_numpy()
        buckets: Dict[str, List[int]] = defaultdict(list)
        for i, v in enumerate(values):
            buckets[v].append(i)

        rows: List[int] = []
        cols: List[int] = []
        n_hub = 0

        for value, idxs in buckets.items():
            if len(idxs) > cap:
                n_hub += 1
                continue
            # idxs is already ascending because it was built in row order,
            # and rows are time-sorted, so idxs is time-ordered too.
            for pos in range(1, len(idxs)):
                receiver = idxs[pos]
                lo = max(0, pos - k)
                for sender in idxs[lo:pos]:
                    rows.append(receiver)
                    cols.append(sender)

        data = np.ones(len(rows), dtype=np.float32)
        a = sp.csr_matrix(
            (data, (np.asarray(rows, dtype=np.int64), np.asarray(cols, dtype=np.int64))),
            shape=(n, n),
        )
        a.sum_duplicates()
        adj[rel] = a
        edge_counts[rel] = int(a.nnz)
        skipped[rel] = n_hub
        if verbose:
            print(f"[graph]   {rel:<9} edges={a.nnz:>9,}  hub values skipped={n_hub}")

    return RelationGraph(
        n_nodes=n,
        relations=list(gcfg.relations),
        adj=adj,
        edge_counts=edge_counts,
        skipped_hubs=skipped,
        times=df[TIME_COL].to_numpy(),
    )


def neighbour_risk_features(
    graph: RelationGraph,
    y: np.ndarray,
    usable: np.ndarray,
    lag: int = 0,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Structural neighbourhood statistics: degree and confirmed-fraud counts at
    one and two hops, per relation.

    This is the RGTAN "risk-aware neighbourhood" signal, rebuilt so it cannot
    leak. Three properties do that work:

    * the adjacency is directed backwards in time, so a node aggregates only
      over transactions that already happened;
    * ``usable`` marks rows with a *confirmed* outcome, so unlabeled traffic is
      never counted as legitimate by default;
    * ``lag`` drops edges whose sender is too recent for its outcome to have
      been confirmed, modelling chargeback delay.

    The reference implementation in AI4Risk/antifraud counts fraudulent
    neighbours over an undirected graph using the complete label vector,
    including the labels of held-out nodes. Its published numbers therefore
    are not comparable to the ones this project reports.
    """
    n = graph.n_nodes
    adj_risk = graph.lagged(lag)
    known_fraud = (y == 1) & usable
    known_any = usable
    f = known_fraud.astype(np.float32)
    a_ = known_any.astype(np.float32)
    ones = np.ones(n, dtype=np.float32)

    cols: Dict[str, np.ndarray] = {}
    for rel in graph.relations:
        # Structure (degree) uses every edge; label-derived counts use the
        # lag-filtered edges, because knowing a neighbour exists is immediate
        # but knowing it was fraud is not.
        adj = graph.adj[rel]
        adj_r = adj_risk[rel]
        deg1 = adj @ ones
        fr1 = adj_r @ f
        kn1 = adj_r @ a_
        # Two-hop counts via a second multiplication; A @ (A @ x) avoids ever
        # materialising A squared, which would be dense enough to hurt.
        deg2 = adj @ deg1
        fr2 = adj_r @ fr1

        cols[f"g_{rel}_deg1"] = deg1
        cols[f"g_{rel}_deg2"] = deg2
        cols[f"g_{rel}_fraud1"] = fr1
        cols[f"g_{rel}_fraud2"] = fr2
        cols[f"g_{rel}_known1"] = kn1
        # Share of *confirmed* neighbours that were fraud. Unconfirmed
        # neighbours are excluded from the denominator rather than being
        # silently treated as legitimate.
        cols[f"g_{rel}_fraud_share1"] = np.divide(
            fr1, kn1, out=np.zeros_like(fr1), where=kn1 > 0
        )

    out = pd.DataFrame(cols, dtype=np.float32)
    out["g_total_fraud1"] = out[[c for c in out.columns if c.endswith("_fraud1")]].sum(axis=1)
    out["g_total_deg1"] = out[[c for c in out.columns if c.endswith("_deg1")]].sum(axis=1)
    out["g_max_fraud_share1"] = out[
        [c for c in out.columns if c.endswith("_fraud_share1")]
    ].max(axis=1)

    if verbose:
        print(f"[graph] neighbour risk features: {out.shape[1]} columns")
    return out

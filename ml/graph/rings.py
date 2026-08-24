"""
Find abuse rings.

The transaction scorer asks "is this payment fraud?".
This asks "is a group working together right now?" and returns groups, not
single rows.

It never reads fraud labels. Rings are found from structure, timing, and
amount patterns only. Two reasons:

- A ring that has not caused a chargeback yet is the one you most want to
  catch. A detector that needs labels only finds rings after you have paid.
- Confirmed fraud labels arrive late in real life. This part keeps working
  while you wait.

Labels are used afterwards, only to check how good the results were.

How it works:

A cell is one (merchant, payment channel, location) combination inside one
time window. Accounts that use the same cell form a candidate group. Cells
that share a lot of accounts get merged into one ring.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

import networkx as nx
import numpy as np
import pandas as pd

from ml.config import CONFIG, TIME_COL, ClusterConfig, Config

#: Columns whose combination defines an infrastructure cell.
CELL_KEYS: Tuple[str, str, str] = ("Target", "Type", "Location")


@dataclass
class RiskCluster:
    """One detected ring, with the evidence that produced it."""

    cluster_id: str
    window_start: int
    window_end: int

    n_accounts: int
    n_transactions: int
    n_cells: int
    total_value: float

    merchants: List[str]
    channels: List[str]
    locations: List[str]
    accounts_sample: List[str]

    first_seen: int
    last_seen: int

    # ring signature, each component in [0, 1]
    fan_in: float
    single_use_rate: float
    temporal_density: float
    amount_homogeneity: float
    small_amount_score: float

    risk_score: float
    confidence: float
    reasons: List[str]

    # raw quantities kept for the analyst, not for scoring
    median_amount: float
    amount_cv: float
    time_span: int

    # populated only when the transaction scorer has run
    mean_txn_risk: Optional[float] = None
    high_risk_txn_count: Optional[int] = None

    # populated only during evaluation, never during detection
    confirmed_fraud: Optional[int] = None
    confirmed_labeled: Optional[int] = None

    txn_indices: List[int] = field(default_factory=list, repr=False)

    def as_dict(self, include_indices: bool = False) -> dict:
        d = asdict(self)
        if not include_indices:
            d.pop("txn_indices", None)
        return d

    @property
    def precision(self) -> Optional[float]:
        """Share of this ring's confirmed transactions that were fraud."""
        if not self.confirmed_labeled:
            return None
        return self.confirmed_fraud / self.confirmed_labeled


def _cell_table(win: pd.DataFrame, min_txn: int) -> pd.DataFrame:
    """Aggregate one window into infrastructure cells."""
    g = win.groupby(list(CELL_KEYS), sort=False)
    cells = g.agg(
        n=("Amount", "size"),
        n_accounts=("Source", "nunique"),
        amt_sum=("Amount", "sum"),
        amt_mean=("Amount", "mean"),
        amt_med=("Amount", "median"),
        amt_std=("Amount", "std"),
        t_min=(TIME_COL, "min"),
        t_max=(TIME_COL, "max"),
    ).reset_index()
    return cells[cells["n"] >= min_txn].copy()


def _signature(cells: pd.DataFrame, win: pd.DataFrame) -> pd.DataFrame:
    """Attach the five signature components to each cell."""
    cells = cells.copy()
    cells["span"] = (cells["t_max"] - cells["t_min"] + 1).clip(lower=1)

    # Fan-in: one fresh account per transaction is the burner-account pattern.
    cells["fan_in"] = cells["n_accounts"] / cells["n"]

    # Temporal density: transactions per unit time inside the cell's own span,
    # capped at 1 so a single hyper-dense cell cannot dominate the average.
    cells["temporal_density"] = (cells["n"] / cells["span"]).clip(upper=1.0)

    # Amount homogeneity: rings send near-identical amounts, real customers
    # do not. cv -> 0 gives 1.0; cv -> large gives ~0.
    cv = (cells["amt_std"] / cells["amt_mean"].replace(0, np.nan)).fillna(0.0)
    cells["amount_cv"] = cv
    cells["amount_homogeneity"] = 1.0 / (1.0 + cv)

    # Small-amount score: card testing validates credentials with amounts far
    # below the window's typical ticket.
    win_med = float(win["Amount"].median()) or 1.0
    ratio = cells["amt_med"] / win_med
    cells["small_amount_score"] = 1.0 / (1.0 + ratio)

    return cells


def _merge_cells_into_rings(
    win: pd.DataFrame, cells: pd.DataFrame, ccfg: ClusterConfig
) -> List[List[int]]:
    """
    Merge cells that share a *substantial* account base.

    A ring operating through several merchants on one channel shows up as
    several cells bound together by the accounts they have in common, and the
    analyst should see one ring rather than five fragments.

    The overlap floor is what makes this work. Linking cells on any shared
    account at all chains the entire window into a single component through
    ordinary customers who happen to shop in more than one place. Measured on
    this dataset, that produced a 4,826-account "ring" covering the largest
    normal merchants, and dropped precision from 0.86 to 0.62. Requiring
    both an absolute and a proportional overlap keeps the merge to groups that
    genuinely share an account pool.
    """
    n_cells = len(cells)
    cell_accounts: List[set] = []
    keys = list(zip(*[win[c].to_numpy() for c in CELL_KEYS]))
    cell_index = {
        tuple(r): i for i, r in enumerate(cells[list(CELL_KEYS)].to_numpy())
    }
    buckets: Dict[int, set] = defaultdict(set)
    for src, key in zip(win["Source"].to_numpy(), keys):
        ci = cell_index.get(key)
        if ci is not None:
            buckets[ci].add(src)
    cell_accounts = [buckets.get(i, set()) for i in range(n_cells)]

    # Candidate pairs come from an inverted index, so cells that share no
    # account are never compared.
    account_to_cells: Dict[str, set] = defaultdict(set)
    for ci, accts in enumerate(cell_accounts):
        for a in accts:
            account_to_cells[a].add(ci)

    shared: Dict[Tuple[int, int], int] = defaultdict(int)
    for cis in account_to_cells.values():
        if len(cis) < 2:
            continue
        ordered = sorted(cis)
        for a_i in range(len(ordered)):
            for b_i in range(a_i + 1, len(ordered)):
                shared[(ordered[a_i], ordered[b_i])] += 1

    g = nx.Graph()
    g.add_nodes_from(range(n_cells))
    for (i, j), count in shared.items():
        smaller = min(len(cell_accounts[i]), len(cell_accounts[j]))
        if smaller == 0:
            continue
        if (
            count >= ccfg.merge_min_shared_accounts
            and count / smaller >= ccfg.merge_min_overlap
        ):
            g.add_edge(i, j, weight=count)

    return [sorted(comp) for comp in nx.connected_components(g)]


def detect_rings(
    df: pd.DataFrame,
    cfg: Config = CONFIG,
    txn_risk: Optional[np.ndarray] = None,
    verbose: bool = True,
) -> List[RiskCluster]:
    """
    Find abuse rings across sliding time windows.

    Arguments:
    df
        Time-sorted transaction frame with a dense index.
    txn_risk
        Optional per-transaction risk scores aligned to ``df``. Used only to
        annotate a ring after it has been found, never to find it.
    """
    ccfg = cfg.cluster
    times = df[TIME_COL].to_numpy()
    t_min, t_max = int(times.min()), int(times.max())

    clusters: List[RiskCluster] = []
    seen: set = set()
    serial = 0

    starts = list(range(t_min, max(t_max - ccfg.window + 1, t_min + 1), ccfg.stride))
    if verbose:
        print(
            f"[rings] scanning {len(starts)} windows of {ccfg.window:,} "
            f"(stride {ccfg.stride:,}) over t={t_min:,}..{t_max:,}"
        )

    for w_start in starts:
        w_end = w_start + ccfg.window
        win = df.loc[(times >= w_start) & (times < w_end)]
        if len(win) < ccfg.min_transactions:
            continue

        cells = _cell_table(win, ccfg.min_transactions)
        if cells.empty:
            continue
        cells = _signature(cells, win)

        for group in _merge_cells_into_rings(win, cells, ccfg):
            grp = cells.iloc[group]
            sel = np.ones(len(win), dtype=bool)
            keys = list(zip(*[win[c].to_numpy() for c in CELL_KEYS]))
            wanted = set(map(tuple, grp[list(CELL_KEYS)].to_numpy()))
            sel = np.array([k in wanted for k in keys])
            member = win.loc[sel]

            if len(member) < ccfg.min_transactions:
                continue
            accounts = member["Source"].unique()
            if len(accounts) < ccfg.min_accounts:
                continue

            # Overlapping windows re-find the same ring; keep it once.
            sig = (frozenset(accounts), int(member[TIME_COL].min()))
            if sig in seen:
                continue
            seen.add(sig)

            clusters.append(
                _score_cluster(member, grp, w_start, w_end, serial, txn_risk)
            )
            serial += 1

    clusters.sort(key=lambda c: c.risk_score, reverse=True)
    if verbose:
        print(f"[rings] {len(clusters)} candidate rings")
    return clusters


def _score_cluster(
    member: pd.DataFrame,
    cells: pd.DataFrame,
    w_start: int,
    w_end: int,
    serial: int,
    txn_risk: Optional[np.ndarray],
) -> RiskCluster:
    """Turn a merged cell group into a scored, explainable ring."""
    n_txn = len(member)
    per_account = member["Source"].value_counts()
    n_acc = len(per_account)

    merch = member["Target"].value_counts()
    chan = member["Type"].value_counts()
    loc = member["Location"].value_counts()

    span = int(member[TIME_COL].max() - member[TIME_COL].min()) + 1

    # Transaction-weighted averages of the per-cell signature: a ring made of
    # one huge cell and one tiny one should read as the huge one.
    w = cells["n"].to_numpy(dtype=float)
    w = w / w.sum() if w.sum() else np.ones(len(cells)) / max(len(cells), 1)

    fan_in = float(n_acc / n_txn) if n_txn else 0.0
    single_use = float((per_account == 1).mean())
    density = float((cells["temporal_density"].to_numpy() * w).sum())
    homogeneity = float((cells["amount_homogeneity"].to_numpy() * w).sum())
    small_amt = float((cells["small_amount_score"].to_numpy() * w).sum())

    components = {
        "fan_in": fan_in,
        "single_use_rate": single_use,
        "temporal_density": density,
        "amount_homogeneity": homogeneity,
        "small_amount_score": small_amt,
    }
    risk = float(np.mean(list(components.values())))

    # Confidence grows with the amount of evidence behind the claim: a
    # six-account cluster is a weaker assertion than a six-hundred-account one
    # at the same score.
    confidence = float(np.clip(np.log1p(n_acc) / np.log1p(500), 0.05, 1.0))

    med_amt = float(member["Amount"].median())
    amt_mean = float(member["Amount"].mean())
    amt_cv = float(member["Amount"].std() / amt_mean) if amt_mean else 0.0

    reasons: List[str] = []
    if fan_in >= 0.8:
        reasons.append(
            f"{n_acc:,} distinct accounts across {n_txn:,} transactions "
            f"({fan_in:.0%} unique) - consistent with single-use accounts"
        )
    if single_use >= 0.8:
        reasons.append(f"{single_use:.0%} of accounts transacted exactly once")
    if density >= 0.3:
        reasons.append(
            f"{n_txn:,} transactions compressed into {span:,} time units"
        )
    if homogeneity >= 0.5:
        reasons.append(
            f"near-uniform amounts (coefficient of variation {amt_cv:.2f})"
        )
    if small_amt >= 0.6:
        reasons.append(
            f"median amount {med_amt:.2f} is far below typical traffic "
            f"- consistent with credential testing"
        )
    if len(cells) > 1:
        reasons.append(
            f"{len(cells)} merchant/channel combinations linked by shared accounts"
        )
    if not reasons:
        reasons.append("group linked by shared merchant, channel and location")

    cluster = RiskCluster(
        cluster_id=f"ring_{w_start:06d}_{serial:03d}",
        window_start=int(w_start),
        window_end=int(w_end),
        n_accounts=n_acc,
        n_transactions=n_txn,
        n_cells=int(len(cells)),
        total_value=float(member["Amount"].sum()),
        merchants=[str(x) for x in merch.index[:5]],
        channels=[str(x) for x in chan.index[:5]],
        locations=[str(x) for x in loc.index[:5]],
        accounts_sample=[str(x) for x in per_account.index[:8]],
        first_seen=int(member[TIME_COL].min()),
        last_seen=int(member[TIME_COL].max()),
        fan_in=fan_in,
        single_use_rate=single_use,
        temporal_density=density,
        amount_homogeneity=homogeneity,
        small_amount_score=small_amt,
        risk_score=risk,
        confidence=confidence,
        reasons=reasons,
        median_amount=med_amt,
        amount_cv=amt_cv,
        time_span=span,
        txn_indices=[int(i) for i in member.index],
    )

    if txn_risk is not None:
        s = txn_risk[member.index.to_numpy()]
        cluster.mean_txn_risk = float(s.mean())
        cluster.high_risk_txn_count = int((s >= 0.5).sum())

    return cluster


def annotate_with_labels(
    clusters: List[RiskCluster], y: np.ndarray, labeled: np.ndarray
) -> List[RiskCluster]:
    """
    Attach confirmed-outcome counts to detected rings.

    Called only during evaluation. Detection has already finished, so nothing
    here can influence what was found.
    """
    for c in clusters:
        idx = np.asarray(c.txn_indices, dtype=int)
        lab = idx[labeled[idx]]
        c.confirmed_labeled = int(len(lab))
        c.confirmed_fraud = int(y[lab].sum()) if len(lab) else 0
    return clusters


def clusters_to_frame(clusters: List[RiskCluster]) -> pd.DataFrame:
    """Tabular view for CLI output and reports."""
    if not clusters:
        return pd.DataFrame()
    df = pd.DataFrame([c.as_dict() for c in clusters])
    df["precision"] = [c.precision for c in clusters]
    return df


def transaction_to_cluster(clusters: List[RiskCluster]) -> Dict[int, str]:
    """Map each transaction to the highest-scoring ring containing it."""
    out: Dict[int, str] = {}
    best: Dict[int, float] = {}
    for c in clusters:
        for i in c.txn_indices:
            if c.risk_score > best.get(i, -1.0):
                best[i] = c.risk_score
                out[i] = c.cluster_id
    return out



"""
Turn raw transactions into features.

The rule: a transaction only sees the past.

We walk through transactions in time order. For each one we write its features
first, then add it to the running totals. So row 10 is built from rows 0 to 9
and never from row 11.

This matters. In real life a merchant scoring a payment knows what happened
before it and nothing after. If we used a normal groupby over the whole file,
next month traffic would leak into this month features and every score would
look better than it really is.

Two groups of features come out:

base
    Speed, amounts, and history. No fraud labels are read. This is what the
    tabular model sees.

risk
    Counts of confirmed fraud near this transaction, using only outcomes that
    were already known. This is what the graph model sees on top of base.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from ml.config import (
    CONFIG,
    ENTITY_COLS,
    LABEL_COL,
    LABEL_FRAUD,
    LABEL_UNKNOWN,
    TIME_COL,
    Config,
)

# Counterpart relations used for windowed distinct-count ("fan") features.
# Read as: for this entity, how many distinct <counterpart>s has it touched
# inside the window. Fan-in on a merchant is the main ring signal: many
# different accounts converging on one merchant in a short burst.
FAN_RELATIONS: List[Tuple[str, str]] = [
    ("Source", "Target"),    # one account spraying across merchants
    ("Source", "Type"),      # one account cycling payment channels
    ("Target", "Source"),    # many accounts converging on one merchant
    ("Target", "Type"),      # merchant accepting via many channels
    ("Type", "Source"),      # one channel used by many accounts
    ("Type", "Target"),      # one channel funnelling to many merchants
    ("Location", "Source"),  # many accounts from one location
]


# Accumulators


class EntityHistory:
    """
    Past-only history for one entity value (one card, one merchant, ...).

    Times are appended in non-decreasing order, so ``times`` stays sorted and a
    window boundary can be found by binary search. Prefix sums over amount and
    amount-squared then give windowed count / sum / mean / std in O(log n)
    without rescanning the window.
    """

    __slots__ = ("times", "cum_amt", "cum_amt2", "first_time", "last_time", "n")

    def __init__(self) -> None:
        self.times: List[int] = []
        self.cum_amt: List[float] = [0.0]
        self.cum_amt2: List[float] = [0.0]
        self.first_time: int = -1
        self.last_time: int = -1
        self.n: int = 0

    def add(self, t: int, amount: float) -> None:
        if self.n == 0:
            self.first_time = t
        self.times.append(t)
        self.cum_amt.append(self.cum_amt[-1] + amount)
        self.cum_amt2.append(self.cum_amt2[-1] + amount * amount)
        self.last_time = t
        self.n += 1

    def window(self, t: int, span: int) -> Tuple[int, float, float, float]:
        """Return (count, sum, mean, std) over ``(t - span, t]`` of past rows."""
        lo = bisect_left(self.times, t - span)
        cnt = self.n - lo
        if cnt <= 0:
            return 0, 0.0, 0.0, 0.0
        s = self.cum_amt[self.n] - self.cum_amt[lo]
        s2 = self.cum_amt2[self.n] - self.cum_amt2[lo]
        mean = s / cnt
        var = max(s2 / cnt - mean * mean, 0.0)
        return cnt, s, mean, math.sqrt(var)

    def lifetime(self) -> Tuple[int, float, float, float]:
        """Return (count, sum, mean, std) over all past rows."""
        if self.n == 0:
            return 0, 0.0, 0.0, 0.0
        s = self.cum_amt[self.n]
        s2 = self.cum_amt2[self.n]
        mean = s / self.n
        var = max(s2 / self.n - mean * mean, 0.0)
        return self.n, s, mean, math.sqrt(var)


class SlidingDistinct:
    """
    Number of distinct counterpart values an entity touched inside a window.

    A deque plus a multiset gives amortised O(1) maintenance: expire entries
    that fell out of the window, then read ``len(counter)``. Recomputing the
    distinct count by rescanning the window instead would be quadratic on hub
    entities. One merchant here carries over eight thousand transactions.
    """

    __slots__ = ("span", "queues", "counts")

    def __init__(self, span: int) -> None:
        self.span = span
        self.queues: Dict[str, deque] = defaultdict(deque)
        self.counts: Dict[str, Counter] = defaultdict(Counter)

    def _expire(self, key: str, t: int) -> None:
        q = self.queues[key]
        c = self.counts[key]
        cutoff = t - self.span
        while q and q[0][0] < cutoff:
            _, val = q.popleft()
            c[val] -= 1
            if c[val] <= 0:
                del c[val]

    def query(self, key: str, t: int) -> int:
        if key not in self.queues:
            return 0
        self._expire(key, t)
        return len(self.counts[key])

    def add(self, key: str, t: int, val: str) -> None:
        self.queues[key].append((t, val))
        self.counts[key][val] += 1


class RiskCounter:
    """
    Past-only counts of confirmed outcomes per entity, with disclosure lag.

    A label becomes usable only after ``lag`` time units have passed, modelling
    the delay between a fraudulent transaction and the chargeback that confirms
    it. Pending labels sit in a queue and are folded into the running counts
    once their disclosure time is reached.
    """

    __slots__ = ("lag", "pending", "n_labeled", "n_fraud", "fraud_amount")

    def __init__(self, lag: int = 0) -> None:
        self.lag = lag
        self.pending: deque = deque()  # (disclosure_time, key, label, amount)
        self.n_labeled: Counter = Counter()
        self.n_fraud: Counter = Counter()
        self.fraud_amount: Dict[str, float] = defaultdict(float)

    def advance(self, t: int) -> None:
        """Fold in every label whose disclosure time has arrived."""
        while self.pending and self.pending[0][0] <= t:
            _, key, label, amount = self.pending.popleft()
            self.n_labeled[key] += 1
            if label == LABEL_FRAUD:
                self.n_fraud[key] += 1
                self.fraud_amount[key] += amount

    def observe(self, t: int, key: str, label: int, amount: float) -> None:
        """Record a confirmed outcome, to become visible at ``t + lag``."""
        if label == LABEL_UNKNOWN:
            return
        self.pending.append((t + self.lag, key, label, amount))

    def stats(self, key: str, prior_rate: float, prior_strength: float):
        """Return (n_labeled, n_fraud, smoothed_rate, fraud_amount)."""
        n = self.n_labeled.get(key, 0)
        f = self.n_fraud.get(key, 0)
        rate = (f + prior_rate * prior_strength) / (n + prior_strength)
        return n, f, rate, self.fraud_amount.get(key, 0.0)


# Helpers


def _entropy(counter: Counter) -> float:
    """Shannon entropy of a value distribution, in nats."""
    total = sum(counter.values())
    if total <= 0:
        return 0.0
    ent = 0.0
    for v in counter.values():
        p = v / total
        ent -= p * math.log(p + 1e-12)
    return ent


def _safe_z(x: float, mean: float, std: float) -> float:
    """Z-score that degrades gracefully when history is thin or constant."""
    if std < 1e-9:
        return 0.0 if abs(x - mean) < 1e-9 else math.copysign(1.0, x - mean) * 5.0
    return float(np.clip((x - mean) / std, -20.0, 20.0))


# Main pass


@dataclass
class FeatureBundle:
    """Output of the causal pass."""

    base: pd.DataFrame          # label-free behavioural / velocity features
    risk: pd.DataFrame          # leak-free neighbourhood risk features
    base_columns: List[str]
    risk_columns: List[str]

    @property
    def all_columns(self) -> List[str]:
        return self.base_columns + self.risk_columns

    def joined(self) -> pd.DataFrame:
        return pd.concat([self.base, self.risk], axis=1)


class CausalFeatureState:
    """
    The accumulators behind the causal pass, as a reusable object.

    Two methods, always in this order:

        emit(t, amount, entities)     features from the past only
        update(t, amount, entities, label)   this row becomes part of the past

    Splitting them is what makes causality structural rather than a rule
    someone has to remember. A row cannot influence its own features because
    ``emit`` runs before ``update`` touches anything.

    The batch pass loops over these two calls. The API warms one state over
    the historical stream, then calls ``emit`` for a transaction that is not in
    the file at all, which is how a new transaction gets scored with the same
    code that produced the training features.
    """

    def __init__(self, cfg: Config = CONFIG):
        fcfg = cfg.features
        self.cfg = cfg
        self.windows = list(fcfg.velocity_windows)
        self.ent_cols = list(fcfg.velocity_entities)
        self.prior_strength = fcfg.risk_prior_strength

        self.hist: Dict[str, Dict[str, EntityHistory]] = {
            c: defaultdict(EntityHistory) for c in self.ent_cols
        }
        self.fans: Dict[Tuple[str, str, int], SlidingDistinct] = {
            (e, cp, w): SlidingDistinct(w)
            for (e, cp) in FAN_RELATIONS
            for w in self.windows
        }
        # Lifetime distinct counterparts, and the payment-channel mix per
        # account used for the trading-entropy shift (the STAN idea).
        self.lifetime_distinct: Dict[Tuple[str, str], Dict[str, set]] = {
            (e, cp): defaultdict(set) for (e, cp) in FAN_RELATIONS
        }
        self.type_mix: Dict[str, Counter] = defaultdict(Counter)
        self.risk_counters: Dict[str, RiskCounter] = {
            c: RiskCounter(lag=fcfg.label_lag_steps) for c in ENTITY_COLS
        }

        # Running prior: the fraud rate confirmed so far overall.
        self.seen_labeled = 0
        self.seen_fraud = 0
        self.past_amounts: List[float] = []
        self.n_seen = 0

        self.base_columns, self.risk_columns, self.fanin_col = _column_layout(
            self.ent_cols, self.windows
        )
        self.bidx = {c: i for i, c in enumerate(self.base_columns)}
        self.ridx = {c: i for i, c in enumerate(self.risk_columns)}
        self._fanin_w = self.windows[min(2, len(self.windows) - 1)]

    def emit(
        self, t: int, amount: float, ent: Dict[str, str]
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Features for a transaction at time ``t``, from the past only."""
        row_b = np.zeros(len(self.base_columns), dtype=np.float32)
        row_r = np.zeros(len(self.risk_columns), dtype=np.float32)
        self.emit_into(row_b, row_r, t, amount, ent)
        return row_b, row_r

    def emit_into(
        self,
        row_b: np.ndarray,
        row_r: np.ndarray,
        t: int,
        amount: float,
        ent: Dict[str, str],
    ) -> None:
        """As ``emit``, writing into buffers the caller owns."""
        t = int(t)
        amt = float(amount)
        bidx, ridx = self.bidx, self.ridx
        windows = self.windows

        for c in ENTITY_COLS:
            self.risk_counters[c].advance(t)

        # base: transaction intrinsics
        row_b[bidx["amount"]] = amt
        row_b[bidx["log_amount"]] = math.log1p(amt)
        cents = round((amt - math.floor(amt)) * 100)
        row_b[bidx["amount_cents"]] = cents
        row_b[bidx["is_round_amount"]] = 1.0 if cents == 0 else 0.0
        row_b[bidx["time_index"]] = t
        if self.past_amounts:
            recent = self.past_amounts[-5000:]
            row_b[bidx["amount_rank_global"]] = (
                bisect_left(sorted(recent), amt)
                / min(len(self.past_amounts), 5000)
            )

        # base: per-entity history
        for e in self.ent_cols:
            h = self.hist[e][ent[e]]
            cnt, _, mean, std = h.lifetime()
            row_b[bidx[f"{e}_txn_count"]] = cnt
            row_b[bidx[f"{e}_is_new"]] = 1.0 if cnt == 0 else 0.0
            row_b[bidx[f"{e}_age"]] = (t - h.first_time) if cnt else 0.0
            row_b[bidx[f"{e}_gap_since_last"]] = (t - h.last_time) if cnt else -1.0
            row_b[bidx[f"{e}_amt_mean_hist"]] = mean
            row_b[bidx[f"{e}_amt_std_hist"]] = std
            row_b[bidx[f"{e}_amt_z"]] = _safe_z(amt, mean, std) if cnt >= 2 else 0.0
            for w in windows:
                wc, ws, wm, _ = h.window(t, w)
                row_b[bidx[f"{e}_cnt_w{w}"]] = wc
                row_b[bidx[f"{e}_amt_sum_w{w}"]] = ws
                row_b[bidx[f"{e}_amt_mean_w{w}"]] = wm

        # base: fan / distinct counterparts
        for e, cp in FAN_RELATIONS:
            key = ent[e]
            row_b[bidx[f"{e}_distinct_{cp}_lifetime"]] = len(
                self.lifetime_distinct[(e, cp)].get(key, ())
            )
            for w in windows:
                row_b[bidx[f"{e}_distinct_{cp}_w{w}"]] = self.fans[(e, cp, w)].query(
                    key, t
                )

        src, tgt, typ = ent["Source"], ent["Target"], ent["Type"]

        row_b[bidx["Source_new_Target"]] = (
            0.0 if tgt in self.lifetime_distinct[("Source", "Target")].get(src, ()) else 1.0
        )
        row_b[bidx["Source_new_Type"]] = (
            0.0 if typ in self.lifetime_distinct[("Source", "Type")].get(src, ()) else 1.0
        )

        # Trading entropy over the account's payment-channel mix, and how much
        # this transaction shifts it. A sudden change of channel mix is a
        # classic account-takeover / ring-onboarding signal (STAN, AAAI 2020).
        mix = self.type_mix[src]
        ent_before = _entropy(mix)
        mix_after = mix.copy()
        mix_after[typ] += 1
        row_b[bidx["Source_type_entropy"]] = ent_before
        row_b[bidx["Source_type_entropy_shift"]] = _entropy(mix_after) - ent_before

        # Fan-in ratio: distinct accounts per transaction on this merchant in
        # the window. Near 1.0 means every transaction came from a different
        # account. That is the shape of a ring, not of repeat customers.
        fw = self._fanin_w
        tgt_cnt_w = row_b[bidx[f"Target_cnt_w{fw}"]]
        tgt_src_w = row_b[bidx[f"Target_distinct_Source_w{fw}"]]
        row_b[bidx[self.fanin_col]] = tgt_src_w / tgt_cnt_w if tgt_cnt_w > 0 else 0.0

        # Burst ratio: short-window rate against the entity's own long-window
        # rate, normalised by window length. Values well above 1 mean the
        # entity is currently far busier than it usually is.
        for e in ("Source", "Target"):
            short = row_b[bidx[f"{e}_cnt_w{windows[0]}"]]
            long = row_b[bidx[f"{e}_cnt_w{windows[-1]}"]]
            scale = windows[-1] / windows[0]
            row_b[bidx[f"burst_ratio_{e}"]] = (short * scale) / long if long > 0 else 0.0

        # risk: leak-free neighbourhood
        prior = (self.seen_fraud / self.seen_labeled) if self.seen_labeled > 0 else 0.0
        row_r[ridx["global_prior_rate"]] = prior
        rates = []
        frauds_total = 0.0
        for e in ENTITY_COLS:
            nl, nf, rate, famt = self.risk_counters[e].stats(
                ent[e], prior, self.prior_strength
            )
            row_r[ridx[f"{e}_known_outcomes"]] = nl
            row_r[ridx[f"{e}_known_frauds"]] = nf
            row_r[ridx[f"{e}_risk_rate"]] = rate
            row_r[ridx[f"{e}_fraud_amount"]] = famt
            rates.append(rate)
            frauds_total += nf
        row_r[ridx["neighbourhood_risk_max"]] = max(rates)
        row_r[ridx["neighbourhood_risk_mean"]] = sum(rates) / len(rates)
        row_r[ridx["neighbourhood_known_frauds"]] = frauds_total

    def update(
        self,
        t: int,
        amount: float,
        ent: Dict[str, str],
        label: int = LABEL_UNKNOWN,
        label_usable: bool = True,
    ) -> None:
        """Fold this transaction into the accumulators. Call after ``emit``."""
        t = int(t)
        amt = float(amount)

        for e in self.ent_cols:
            self.hist[e][ent[e]].add(t, amt)
        for e, cp in FAN_RELATIONS:
            key, val = ent[e], ent[cp]
            self.lifetime_distinct[(e, cp)][key].add(val)
            for w in self.windows:
                self.fans[(e, cp, w)].add(key, t, val)
        self.type_mix[ent["Source"]][ent["Type"]] += 1
        self.past_amounts.append(amt)
        self.n_seen += 1

        lab = int(label)
        if lab != LABEL_UNKNOWN and label_usable:
            for e in ENTITY_COLS:
                self.risk_counters[e].observe(t, ent[e], lab, amt)
            self.seen_labeled += 1
            if lab == LABEL_FRAUD:
                self.seen_fraud += 1

    def frames(
        self, row_b: np.ndarray, row_r: np.ndarray
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Wrap one emitted pair of vectors as single-row frames."""
        return (
            pd.DataFrame([row_b], columns=self.base_columns),
            pd.DataFrame([row_r], columns=self.risk_columns),
        )


def _column_layout(
    ent_cols: List[str], windows: List[int]
) -> Tuple[List[str], List[str], str]:
    """Names and order of every emitted feature. One definition, used twice."""
    base_cols: List[str] = [
        "amount",
        "log_amount",
        "amount_cents",
        "is_round_amount",
        "amount_rank_global",
        "time_index",
    ]
    for e in ent_cols:
        base_cols += [
            f"{e}_txn_count",
            f"{e}_is_new",
            f"{e}_age",
            f"{e}_gap_since_last",
            f"{e}_amt_mean_hist",
            f"{e}_amt_std_hist",
            f"{e}_amt_z",
        ]
        for w in windows:
            base_cols += [f"{e}_cnt_w{w}", f"{e}_amt_sum_w{w}", f"{e}_amt_mean_w{w}"]
    for e, cp in FAN_RELATIONS:
        base_cols += [f"{e}_distinct_{cp}_lifetime"]
        for w in windows:
            base_cols += [f"{e}_distinct_{cp}_w{w}"]

    # Window used for the merchant fan-in ratio: a mid-length window, long
    # enough to contain a burst but short enough not to average it away.
    fanin_w = windows[min(2, len(windows) - 1)]
    fanin_col = f"Target_fanin_ratio_w{fanin_w}"
    base_cols += [
        "Source_new_Target",
        "Source_new_Type",
        "Source_type_entropy",
        "Source_type_entropy_shift",
        fanin_col,
        "burst_ratio_Source",
        "burst_ratio_Target",
    ]

    risk_cols: List[str] = []
    for e in ENTITY_COLS:
        risk_cols += [
            f"{e}_known_outcomes",
            f"{e}_known_frauds",
            f"{e}_risk_rate",
            f"{e}_fraud_amount",
        ]
    risk_cols += [
        "neighbourhood_risk_max",
        "neighbourhood_risk_mean",
        "neighbourhood_known_frauds",
        "global_prior_rate",
    ]
    return base_cols, risk_cols, fanin_col


def build_causal_features(
    df: pd.DataFrame,
    cfg: Config = CONFIG,
    train_mask: np.ndarray | None = None,
    verbose: bool = True,
) -> FeatureBundle:
    """
    Run the single causal pass and return both feature families.

    Arguments:
    df
        Full transaction frame, sorted by ``Time`` with a dense index.
    train_mask
        Optional restriction on which rows' confirmed outcomes may enter the
        risk counters. ``None`` is the normal setting, and the one the pipeline
        uses. It lets every confirmed outcome count once it is in the past,
        which is what a live system actually knows. Passing an
        explicit mask is used by the tests to prove the pass is causal.

        Causality does not depend on this argument. It is enforced by
        ``CausalFeatureState``: a row's features are emitted before that row
        touches any accumulator, so no row can ever influence itself or
        anything earlier.
    """
    n = len(df)
    state = CausalFeatureState(cfg)

    times = df[TIME_COL].to_numpy()
    amounts = df["Amount"].to_numpy(dtype=float)
    labels = df[LABEL_COL].to_numpy()
    ent_values = {c: df[c].to_numpy() for c in ENTITY_COLS}

    if train_mask is None:
        train_mask = np.ones(n, dtype=bool)

    base_out = np.zeros((n, len(state.base_columns)), dtype=np.float32)
    risk_out = np.zeros((n, len(state.risk_columns)), dtype=np.float32)

    if verbose:
        print(f"[features] causal pass over {n:,} transactions "
              f"({len(state.base_columns)} base + "
              f"{len(state.risk_columns)} risk features)")

    for i in range(n):
        t = int(times[i])
        amt = float(amounts[i])
        ent = {c: ent_values[c][i] for c in ENTITY_COLS}

        state.emit_into(base_out[i], risk_out[i], t, amt, ent)

        # ================================================================
        # Everything above read only the past. Now the current row updates
        # the accumulators so it becomes "past" for row i+1.
        # ================================================================
        state.update(t, amt, ent, int(labels[i]), bool(train_mask[i]))

        if verbose and (i + 1) % 20000 == 0:
            print(f"[features]   {i + 1:,}/{n:,}")

    base_df = pd.DataFrame(base_out, columns=state.base_columns, index=df.index)
    risk_df = pd.DataFrame(risk_out, columns=state.risk_columns, index=df.index)

    if verbose:
        print(f"[features] done: base={base_df.shape}, risk={risk_df.shape}")

    return FeatureBundle(
        base=base_df,
        risk=risk_df,
        base_columns=state.base_columns,
        risk_columns=state.risk_columns,
    )

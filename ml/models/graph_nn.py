"""
Model B: a small graph neural network.

For every transaction it mixes the transaction own features with the average
features of its neighbours, once per relation:

    new = act( W_self * own + sum over relations of W_rel * neighbour average )

Because edges only point from older to newer, stacking layers widens how far
back a transaction can look, never forward.

Notes:

- Plain PyTorch with sparse matrix products. DGL is not needed, so this runs
  on any CPU.
- Full batch. 77,881 nodes and about 278,000 edges fit in memory easily.
- Feature scaling uses training rows only.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import scipy.sparse as sp
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.metrics import average_precision_score

from ml.config import CONFIG, Config


def set_seed(seed: int) -> None:
    """Pin every source of randomness the graph model touches."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)


def _to_torch_sparse(a: sp.csr_matrix) -> torch.Tensor:
    coo = a.tocoo()
    idx = torch.from_numpy(np.vstack([coo.row, coo.col])).long()
    val = torch.from_numpy(coo.data.astype(np.float32))
    return torch.sparse_coo_tensor(idx, val, coo.shape).coalesce()


class RelationalLayer(nn.Module):
    """One self-transform plus one linear map per relation."""

    def __init__(self, in_dim: int, out_dim: int, relations: List[str]):
        super().__init__()
        self.relations = relations
        self.self_lin = nn.Linear(in_dim, out_dim)
        self.rel_lin = nn.ModuleDict(
            {r: nn.Linear(in_dim, out_dim, bias=False) for r in relations}
        )

    def forward(self, h: torch.Tensor, adj: Dict[str, torch.Tensor]) -> torch.Tensor:
        out = self.self_lin(h)
        for r in self.relations:
            out = out + self.rel_lin[r](torch.sparse.mm(adj[r], h))
        return out


class RelationalGNN(nn.Module):
    def __init__(
        self,
        in_dim: int,
        hidden_dim: int,
        relations: List[str],
        n_layers: int = 2,
        dropout: float = 0.2,
    ):
        super().__init__()
        self.dropout = dropout
        dims = [in_dim] + [hidden_dim] * n_layers
        self.layers = nn.ModuleList(
            [RelationalLayer(dims[i], dims[i + 1], relations) for i in range(n_layers)]
        )
        self.norms = nn.ModuleList([nn.LayerNorm(hidden_dim) for _ in range(n_layers)])
        self.head = nn.Linear(hidden_dim, 1)

    def forward(self, x: torch.Tensor, adj: Dict[str, torch.Tensor]) -> torch.Tensor:
        h = x
        for layer, norm in zip(self.layers, self.norms):
            h = layer(h, adj)
            h = norm(h)
            h = F.relu(h)
            h = F.dropout(h, p=self.dropout, training=self.training)
        return self.head(h).squeeze(-1)


@dataclass
class GraphModel:
    """A fitted graph model plus the scaling contract its inputs must satisfy."""

    state_dict: dict
    feature_names: List[str]
    relations: List[str]
    in_dim: int
    hidden_dim: int
    n_layers: int
    dropout: float
    mean: np.ndarray
    scale: np.ndarray
    best_epoch: int
    best_val_pr_auc: float
    history: List[dict]

    def _module(self) -> RelationalGNN:
        net = RelationalGNN(
            self.in_dim, self.hidden_dim, self.relations, self.n_layers, self.dropout
        )
        net.load_state_dict(self.state_dict)
        net.eval()
        return net

    def scale_features(self, X: pd.DataFrame) -> np.ndarray:
        missing = [c for c in self.feature_names if c not in X.columns]
        if missing:
            raise KeyError(f"missing {len(missing)} features, e.g. {missing[:5]}")
        arr = X[self.feature_names].to_numpy(dtype=np.float32)
        arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
        return (arr - self.mean) / self.scale

    def predict_proba(
        self, X: pd.DataFrame, adj: Dict[str, sp.csr_matrix]
    ) -> np.ndarray:
        """
        Score every node in the graph.

        The graph model is transductive over the transaction graph: scoring a
        node requires its neighbourhood, so the whole node set is scored in one
        pass and callers slice out the rows they want.
        """
        net = self._module()
        x = torch.from_numpy(self.scale_features(X))
        t_adj = {r: _to_torch_sparse(adj[r]) for r in self.relations}
        with torch.no_grad():
            logits = net(x, t_adj)
            return torch.sigmoid(logits).numpy()

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(self.__dict__, path)
        return path

    @staticmethod
    def load(path: Path) -> "GraphModel":
        return GraphModel(**torch.load(Path(path), weights_only=False))


def train_graph_model(
    X: pd.DataFrame,
    y: np.ndarray,
    adj: Dict[str, sp.csr_matrix],
    train_mask: np.ndarray,
    val_mask: np.ndarray,
    cfg: Config = CONFIG,
    verbose: bool = True,
) -> GraphModel:
    """
    Fit the graph model full-batch, early-stopping on validation PR-AUC.

    ``train_mask`` and ``val_mask`` pick which nodes count towards the loss
    and towards model choice. Every node still passes messages, which is
    fine here because those messages only carry past-only features and
    training-window labels.
    """
    gcfg = cfg.gnn
    set_seed(gcfg.seed)

    relations = list(adj.keys())
    feature_names = list(X.columns)

    raw = X.to_numpy(dtype=np.float32)
    raw = np.nan_to_num(raw, nan=0.0, posinf=0.0, neginf=0.0)
    mean = raw[train_mask].mean(axis=0)
    scale = raw[train_mask].std(axis=0)
    scale[scale < 1e-6] = 1.0
    x = torch.from_numpy((raw - mean) / scale)

    t_adj = {r: _to_torch_sparse(adj[r]) for r in relations}
    y_t = torch.from_numpy(y.astype(np.float32))
    tr_idx = torch.from_numpy(np.where(train_mask)[0]).long()
    va_idx = torch.from_numpy(np.where(val_mask)[0]).long()

    pos = float(y[train_mask].sum())
    neg = float(train_mask.sum() - pos)
    pos_weight = torch.tensor([neg / pos if pos > 0 else 1.0], dtype=torch.float32)

    net = RelationalGNN(
        x.shape[1], gcfg.hidden_dim, relations, gcfg.n_layers, gcfg.dropout
    )
    opt = torch.optim.AdamW(net.parameters(), lr=gcfg.lr, weight_decay=gcfg.weight_decay)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    if verbose:
        n_par = sum(p.numel() for p in net.parameters())
        print(
            f"[graph-nn] {x.shape[0]:,} nodes x {x.shape[1]} features, "
            f"{len(relations)} relations, {n_par:,} parameters"
        )
        print(
            f"[graph-nn] train nodes={int(train_mask.sum()):,} "
            f"val nodes={int(val_mask.sum()):,} pos_weight={pos_weight.item():.2f}"
        )

    best_score = -np.inf
    best_state: Optional[dict] = None
    best_epoch = -1
    history: List[dict] = []
    patience = 0

    y_val_np = y[val_mask]

    for epoch in range(gcfg.max_epochs):
        net.train()
        opt.zero_grad()
        logits = net(x, t_adj)
        loss = loss_fn(logits[tr_idx], y_t[tr_idx])
        loss.backward()
        opt.step()

        net.eval()
        with torch.no_grad():
            ev = net(x, t_adj)
            val_scores = torch.sigmoid(ev[va_idx]).numpy()
        val_pr = (
            float(average_precision_score(y_val_np, val_scores))
            if 0 < y_val_np.sum() < len(y_val_np)
            else float("nan")
        )
        history.append(
            {"epoch": epoch, "train_loss": float(loss.item()), "val_pr_auc": val_pr}
        )

        if val_pr > best_score:
            best_score = val_pr
            best_state = {k: v.detach().clone() for k, v in net.state_dict().items()}
            best_epoch = epoch
            patience = 0
        else:
            patience += 1
            if patience >= gcfg.early_stopping_patience:
                if verbose:
                    print(f"[graph-nn] early stop at epoch {epoch}")
                break

        if verbose and epoch % 25 == 0:
            print(
                f"[graph-nn]   epoch {epoch:3d} loss={loss.item():.4f} "
                f"val PR-AUC={val_pr:.4f}"
            )

    if verbose:
        print(f"[graph-nn] best epoch {best_epoch} val PR-AUC={best_score:.4f}")

    return GraphModel(
        state_dict=best_state if best_state is not None else net.state_dict(),
        feature_names=feature_names,
        relations=relations,
        in_dim=x.shape[1],
        hidden_dim=gcfg.hidden_dim,
        n_layers=gcfg.n_layers,
        dropout=gcfg.dropout,
        mean=mean,
        scale=scale,
        best_epoch=best_epoch,
        best_val_pr_auc=float(best_score),
        history=history,
    )

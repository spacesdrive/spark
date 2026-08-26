"""
Decision log.

Every decision is written as one JSON object on one line. The format is
boring on purpose: you may need to explain a decision months later, and
line-delimited JSON is readable without this codebase.

The log only ever appends. There is no update or delete, because a log you can
rewrite is not a log.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

DEFAULT_LOG = Path("reports") / "decisions.jsonl"


class AuditLog:
    """Append-only JSONL decision log."""

    def __init__(self, path: Path = DEFAULT_LOG):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, decision: Dict) -> Dict:
        """
        Append one decision.

        Only useful fields are kept: which transaction, what was decided, why,
        and by which model version. The
        raw feature vector is not written: it is large, it is reproducible
        from the artifact fingerprint, and storing it would turn the audit log
        into a copy of the payment data.
        """
        entry = {
            "logged_utc": datetime.now(timezone.utc).isoformat(),
            "transaction_id": decision.get("transaction_id"),
            "time": decision.get("time"),
            "amount": decision.get("amount"),
            "source": decision.get("source"),
            "target": decision.get("target"),
            "location": decision.get("location"),
            "payment_type": decision.get("payment_type"),
            "risk_score": decision.get("risk_score"),
            "decision": decision.get("decision"),
            "mode": decision.get("mode"),
            "path": decision.get("path"),
            "model_version": decision.get("model_version"),
            "channel_scores": decision.get("channel_scores"),
            "reasons": decision.get("reasons"),
            "cluster_id": decision.get("cluster_id"),
            "latency_ms": decision.get("latency_ms"),
        }
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=float) + "\n")
        return entry

    def record_many(self, decisions: Iterable[Dict]) -> int:
        n = 0
        with open(self.path, "a", encoding="utf-8") as fh:
            for d in decisions:
                fh.write(json.dumps(d, default=float) + "\n")
                n += 1
        return n

    def read(self, limit: Optional[int] = None,
             transaction_id: Optional[str] = None) -> List[Dict]:
        """Most recent entries first."""
        if not self.path.exists():
            return []
        rows: List[Dict] = []
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a truncated final line must not lose the rest
                if transaction_id and rec.get("transaction_id") != transaction_id:
                    continue
                rows.append(rec)
        rows.reverse()
        return rows[:limit] if limit else rows

    def stats(self) -> Dict:
        """Decision mix, for the operator view."""
        rows = self.read()
        if not rows:
            return {"total": 0}
        scores = [r["risk_score"] for r in rows if r.get("risk_score") is not None]
        lat = [r["latency_ms"] for r in rows if r.get("latency_ms") is not None]
        out = {
            "total": len(rows),
            "approve": sum(1 for r in rows if r.get("decision") == "APPROVE"),
            "review": sum(1 for r in rows if r.get("decision") == "REVIEW"),
            "block": sum(1 for r in rows if r.get("decision") == "BLOCK"),
            "cold_start_path": sum(1 for r in rows if r.get("path") == "COLD_START"),
            "mean_risk_score": (sum(scores) / len(scores)) if scores else 0.0,
        }
        if lat:
            out["mean_latency_ms"] = sum(lat) / len(lat)
        return out

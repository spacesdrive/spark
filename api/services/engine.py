"""
One loaded scoring engine, shared by the whole process.

Loading the models, replaying the feature stream and caching the graph
activations takes a few seconds. Doing that per request would be absurd, so it
happens once and every request borrows the result.

This wraps ``spark.risk.engine.ScoringEngine``. It does not reimplement any
scoring logic, so the API and the command line always agree.
"""

from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional

from api.config.settings import settings

_lock = threading.Lock()
_state: Dict[str, object] = {"engine": None, "scorer": None, "error": None,
                             "load_seconds": None}


def artifacts_present(artifact_dir: Optional[str] = None) -> bool:
    d = Path(artifact_dir or settings.artifact_dir)
    return (d / "model_metadata.json").exists()


def read_metadata(artifact_dir: Optional[str] = None) -> Optional[dict]:
    """Model metadata without loading the models themselves."""
    p = Path(artifact_dir or settings.artifact_dir) / "model_metadata.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def read_evaluation() -> Optional[dict]:
    """The held-out evaluation report, if the evaluation has been run."""
    from ml.config import REPORT_DIR

    p = Path(REPORT_DIR) / "evaluation.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def read_latency() -> Optional[dict]:
    from ml.config import REPORT_DIR

    p = Path(REPORT_DIR) / "latency.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def load(force: bool = False) -> None:
    """Load the engine and the online scorer. Safe to call from many threads."""
    with _lock:
        if _state["engine"] is not None and not force:
            return
        if not artifacts_present():
            _state["error"] = (
                "No trained model found. Run: python -m spark.models.train"
            )
            return
        t0 = time.perf_counter()
        try:
            from ml.serving.online import OnlineScorer
            from spark.risk.engine import ScoringEngine

            engine = ScoringEngine(
                artifact_dir=settings.artifact_dir,
                mode="balanced",
                with_explainer=True,
                verbose=False,
            )
            _state["engine"] = engine
            _state["scorer"] = OnlineScorer(engine, verbose=False)
            _state["error"] = None
        except Exception as exc:  # noqa: BLE001 - surfaced through /api/health
            _state["error"] = f"{type(exc).__name__}: {exc}"
            _state["engine"] = None
            _state["scorer"] = None
        _state["load_seconds"] = round(time.perf_counter() - t0, 2)


# Custom models, loaded on demand
#
# Each loaded engine holds its models plus a warm feature state, which is the
# expensive part. On a small machine two of those is already most of the
# memory, so the cache is deliberately tiny and evicts the least recently used
# entry rather than growing. The built-in engine above is separate and always
# resident, because almost every request wants it.

_custom_lock = threading.Lock()
_custom: "OrderedDict[str, dict]" = OrderedDict()
MAX_CACHED_CUSTOM_ENGINES = 1


def load_custom(artifact_dir: str) -> dict:
    """
    Load, or reuse, the engine for one custom model.

    Returns a dict with ``engine``, ``scorer`` and ``error``. A model that
    fails to load reports the failure rather than falling back to the built-in
    one, because silently scoring with a different model than the caller asked
    for would be worse than an error.
    """
    key = str(Path(artifact_dir).resolve())
    with _custom_lock:
        if key in _custom:
            _custom.move_to_end(key)
            return _custom[key]

    if not artifacts_present(key):
        entry = {"engine": None, "scorer": None,
                 "error": "That model's files are missing."}
    else:
        t0 = time.perf_counter()
        try:
            from ml.serving.online import OnlineScorer
            from spark.risk.engine import ScoringEngine

            eng = ScoringEngine(artifact_dir=key, mode="balanced",
                                with_explainer=True, verbose=False)
            entry = {"engine": eng, "scorer": OnlineScorer(eng, verbose=False),
                     "error": None,
                     "load_seconds": round(time.perf_counter() - t0, 2)}
        except Exception as exc:  # noqa: BLE001 - reported to the caller
            entry = {"engine": None, "scorer": None,
                     "error": f"{type(exc).__name__}: {exc}"}

    with _custom_lock:
        _custom[key] = entry
        _custom.move_to_end(key)
        while len(_custom) > MAX_CACHED_CUSTOM_ENGINES:
            _custom.popitem(last=False)
    return entry


def get_engine():
    """The loaded engine, loading it first if needed."""
    if _state["engine"] is None:
        load()
    return _state["engine"]


def get_scorer():
    """The online scorer, loading it first if needed."""
    if _state["scorer"] is None:
        load()
    return _state["scorer"]


def status() -> dict:
    """What the health endpoint reports about the model."""
    meta = read_metadata()
    loaded = _state["engine"] is not None
    return {
        "loaded": loaded,
        "available": artifacts_present(),
        "error": _state["error"],
        "load_seconds": _state["load_seconds"],
        "model_version": (meta or {}).get("model_version"),
        "trained_at": (meta or {}).get("created_utc"),
    }


# What the model selector shows


def builtin_models() -> List[dict]:
    """
    The models that ship with the project.

    Only what actually exists is listed. There is one trained hybrid model, so
    there is one entry. The three operating points are not separate models,
    they are thresholds on the same model, and the API exposes them as modes.
    """
    meta = read_metadata()
    if meta is None:
        return []

    evaluation = read_evaluation() or {}
    test_row = next(
        (r for r in evaluation.get("ranking_by_split", []) if r["split"] == "test"),
        None,
    )
    channels = meta.get("channels", [])
    return [
        {
            "id": "hybrid-v1",
            "name": "Hybrid V1",
            "version": meta.get("model_version", "spark-hybrid-v1"),
            "kind": "builtin",
            "status": "ready",
            "icon": "/brand/spark-mark.png",
            "description": (
                "The trained Spark model. A gradient boosted tree and a "
                "relational graph network, combined with two label-free "
                "scores and calibrated on validation data."
            ),
            "components": channels,
            "supports_transaction": True,
            "supports_dataset": True,
            "supports_custom": False,
            "input_format": "csv",
            "modes": sorted(meta.get("thresholds", {}).keys()),
            "trained_at": meta.get("created_utc"),
            "training_rows": next(
                (
                    s["rows"]
                    for s in meta.get("dataset", {}).get("splits", [])
                    if s["split"] == "train"
                ),
                None,
            ),
            "held_out_pr_auc": (test_row or {}).get("pr_auc"),
            "owner": "spark",
        }
    ]

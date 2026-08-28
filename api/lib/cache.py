"""
A small read-through cache backed by Upstash Redis.

What is cached: responses that are expensive to build and identical for
everyone, such as the evaluation reports assembled from the artifacts on disk.
Those are recomputed on every request today and never change between
deployments, which makes them the only thing here worth caching.

What is deliberately not cached:

* anything belonging to an organization. A cache keyed carelessly is how one
  tenant ends up reading another's data, and the speed gained is not worth
  that class of bug.
* transaction scores. They depend on the feature state, which moves.
* anything a signed-in user sees that differs per user.

Failure policy: a cache is an optimisation, never a dependency. Every error,
timeout and malformed reply is swallowed and treated as a miss, so Spark keeps
serving correctly when Upstash is slow, unreachable or misconfigured. The only
thing a broken cache costs is the speed it was added to provide.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable, Optional

import httpx

from api.config.settings import settings

log = logging.getLogger("spark.cache")

#: Requests are made with a short timeout. Waiting on a slow cache is worse
#: than missing it, because the work it was avoiding is usually faster.
TIMEOUT_SECONDS = 2.0

#: One pooled client, reused for every call. A fresh TLS handshake per request
#: costs more than every operation this cache performs put together: measured
#: from the server, a new connection took 57 to 127 ms while a reused one is a
#: single round trip.
_client_lock = threading.Lock()
_client: Optional[httpx.Client] = None


def _http() -> httpx.Client:
    global _client
    with _client_lock:
        if _client is None:
            _client = httpx.Client(
                timeout=TIMEOUT_SECONDS,
                limits=httpx.Limits(max_keepalive_connections=8, max_connections=16),
                headers={"Content-Type": "application/json"},
            )
        return _client

_stats = {"hits": 0, "misses": 0, "errors": 0, "skips": 0}
_stats_lock = threading.Lock()

#: After repeated failures the cache stops being called for a while, so an
#: unreachable Upstash costs one timeout a minute rather than one per request.
_breaker = {"failures": 0, "open_until": 0.0, "disabled_reason": ""}
_BREAKER_THRESHOLD = 3
_BREAKER_SECONDS = 60.0


def _disable(reason: str) -> None:
    """
    Stop using the cache for the rest of the process.

    Used for failures that retrying cannot fix. A token without write
    permission is the motivating case: every request would otherwise pay a
    network round trip to be told "no" again, which is strictly worse than
    having no cache at all.
    """
    if not _breaker["disabled_reason"]:
        _breaker["disabled_reason"] = reason
        log.warning("cache disabled for this process: %s", reason)


def configured() -> bool:
    return bool(settings.upstash_redis_rest_url and settings.upstash_redis_rest_token)


def _breaker_open() -> bool:
    return bool(_breaker["disabled_reason"]) or time.monotonic() < _breaker["open_until"]


def _record(success: bool) -> None:
    if success:
        _breaker["failures"] = 0
        return
    _breaker["failures"] += 1
    if _breaker["failures"] >= _BREAKER_THRESHOLD:
        _breaker["open_until"] = time.monotonic() + _BREAKER_SECONDS
        log.warning(
            "Upstash unreachable, pausing cache use for %ss", int(_BREAKER_SECONDS)
        )


def _call(command: list[str]) -> Optional[Any]:
    """
    Send one Redis command over the Upstash REST API.

    Returns None for every failure, which the callers treat as a miss.
    """
    if not configured() or _breaker_open():
        return None

    try:
        response = _http().post(
            settings.upstash_redis_rest_url.rstrip("/"),
            content=json.dumps(command),
            headers={"Authorization": f"Bearer {settings.upstash_redis_rest_token}"},
        )
        body = response.json() if response.content else None
        _record(True)
        if isinstance(body, dict) and "error" in body:
            _note_error(str(body["error"]))
            return None
        return body.get("result") if isinstance(body, dict) else None
    except (httpx.HTTPError, OSError, ValueError, TimeoutError) as exc:
        _record(False)
        with _stats_lock:
            _stats["errors"] += 1
        # Deliberately not the token or the URL, which would put a credential
        # into the log file.
        log.debug("cache unavailable: %s", type(exc).__name__)
        return None


def _note_error(message: str) -> None:
    """Record a Redis-level error, and give up permanently on a hopeless one."""
    with _stats_lock:
        _stats["errors"] += 1
    if "NOPERM" in message or "WRONGPASS" in message or "NOAUTH" in message:
        _disable(
            "the Upstash token is missing permissions Spark needs. A read-only "
            "token cannot store anything, so caching stays off."
        )
    else:
        log.debug("cache command rejected: %s", message[:120])


def _key(name: str) -> str:
    """
    Namespaced by model version, so a redeploy with a new model cannot serve
    the previous model's numbers out of the cache.
    """
    return f"spark:{settings.environment}:{_model_version()}:{name}"


_version_cache: dict[str, str] = {}


def _model_version() -> str:
    if "v" not in _version_cache:
        try:
            from api.services import engine as engine_state

            meta = engine_state.read_metadata() or {}
            _version_cache["v"] = str(meta.get("model_version") or "none")
        except Exception:  # noqa: BLE001 - version is only a cache namespace
            _version_cache["v"] = "none"
    return _version_cache["v"]


def get_json(name: str) -> Optional[Any]:
    raw = _call(["GET", _key(name)])
    if raw is None:
        with _stats_lock:
            _stats["misses"] += 1
        return None
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return None
    with _stats_lock:
        _stats["hits"] += 1
    return value


def set_json(name: str, value: Any, ttl_seconds: int) -> None:
    try:
        payload = json.dumps(value, default=str)
    except (TypeError, ValueError):
        return
    _call(["SET", _key(name), payload, "EX", str(int(ttl_seconds))])


def cached(name: str, ttl_seconds: int, build: Callable[[], Any]) -> Any:
    """
    Return the cached value for ``name``, or build it and store it.

    ``build`` is always called on a miss, so a cache that is switched off or
    broken changes nothing except how long the request takes.
    """
    if not configured():
        with _stats_lock:
            _stats["skips"] += 1
        return build()

    hit = get_json(name)
    if hit is not None:
        return hit

    value = build()
    set_json(name, value, ttl_seconds)
    return value


def invalidate(*names: str) -> None:
    """Drop specific entries, for when the thing behind them has changed."""
    for name in names:
        _call(["DEL", _key(name)])


def stats() -> dict:
    """Cache counters, for the health endpoint. No credential is included."""
    with _stats_lock:
        counters = dict(_stats)
    total = counters["hits"] + counters["misses"]
    return {
        "configured": configured(),
        "paused": _breaker_open(),
        "disabled_reason": _breaker["disabled_reason"] or None,
        **counters,
        "hit_rate": round(counters["hits"] / total, 3) if total else None,
    }


def ping() -> dict:
    """Check the cache is actually reachable, for the health endpoint."""
    if not configured():
        return {"ok": False, "reason": "not_configured"}
    started = time.perf_counter()
    result = _call(["PING"])
    if result is None:
        return {"ok": False, "reason": "unreachable"}
    return {"ok": True, "latency_ms": round((time.perf_counter() - started) * 1000, 1)}


def pipeline(commands: list[list[str]]) -> Optional[list]:
    """
    Send several Redis commands in one round trip.

    Two commands over one connection cost about as much as one, and half as
    much as two separate calls, which matters when this sits in front of every
    rate limited request.
    """
    if not configured() or _breaker_open():
        return None
    try:
        response = _http().post(
            settings.upstash_redis_rest_url.rstrip("/") + "/pipeline",
            content=json.dumps(commands),
            headers={"Authorization": f"Bearer {settings.upstash_redis_rest_token}"},
        )
        body = response.json() if response.content else None
        _record(True)
        if not isinstance(body, list):
            return None
        for item in body:
            if isinstance(item, dict) and "error" in item:
                _note_error(str(item["error"]))
                return None
        return [item.get("result") if isinstance(item, dict) else None for item in body]
    except (httpx.HTTPError, OSError, ValueError, TimeoutError) as exc:
        _record(False)
        with _stats_lock:
            _stats["errors"] += 1
        log.debug("cache pipeline unavailable: %s", type(exc).__name__)
        return None


def incr_with_expiry(key: str, window_seconds: int) -> Optional[int]:
    """
    Increment a counter and make sure it expires. Returns the new count.

    ``EXPIRE ... NX`` sets the lifetime only when the key does not already have
    one, so the window starts at the first request and is not pushed forward by
    every later one. Without NX a client sending continuously would keep
    resetting its own window and never be limited.

    None means the cache could not be reached, and the caller falls back.
    """
    result = pipeline([
        ["INCR", key],
        ["EXPIRE", key, str(int(window_seconds)), "NX"],
    ])
    if not result or result[0] is None:
        return None
    try:
        return int(result[0])
    except (TypeError, ValueError):
        return None

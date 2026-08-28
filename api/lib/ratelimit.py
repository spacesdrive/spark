"""
Rate limiting.

A fixed window counter. It prefers Redis and falls back to memory.

Redis is the correct home for this: an in-memory counter is reset by every
deploy and is not shared between worker processes, so two workers each allow
the full limit. When Upstash is configured and writable, the counter lives
there and both problems go away.

The fallback is not a formality. If Redis is unreachable, or the token cannot
write, the in-memory counter takes over immediately. Rate limiting continuing
imperfectly is much better than either failing open, which removes the
protection, or failing closed, which takes the site down because a cache is
unwell.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Dict, Tuple

from api.types.errors import RateLimited

_WINDOW = 60.0

_counts: Dict[str, Tuple[float, int]] = defaultdict(lambda: (0.0, 0))
_lock = threading.Lock()


def _check_memory(key: str, limit: int) -> None:
    now = time.time()
    window_start = now - (now % _WINDOW)
    with _lock:
        start, count = _counts[key]
        if start != window_start:
            start, count = window_start, 0
        count += 1
        _counts[key] = (start, count)
    if count > limit:
        raise RateLimited(int(window_start + _WINDOW - now) + 1, limit)


def check(key: str, limit: int) -> None:
    """Count one request against ``key`` and raise if it is over the limit."""
    from api.lib import cache

    now = time.time()
    window_start = int(now - (now % _WINDOW))
    # The window is part of the key, so a counter cannot outlive its window
    # even if the expiry is somehow missed.
    count = cache.incr_with_expiry(
        f"spark:rl:{key}:{window_start}", int(_WINDOW) + 5
    )
    if count is None:
        _check_memory(key, limit)
        return
    if count > limit:
        raise RateLimited(int(window_start + _WINDOW - now) + 1, limit)


def reset() -> None:
    """Clear all counters. Used by the tests."""
    with _lock:
        _counts.clear()

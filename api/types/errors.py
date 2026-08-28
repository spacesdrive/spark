"""
Exceptions raised by one layer and handled by another.

They live here rather than beside the code that raises them so that a handler
can catch one without importing the whole service.
"""

from __future__ import annotations


class RateLimited(Exception):
    """Too many requests. Carries the seconds until the window resets."""

    def __init__(self, retry_after: int, limit: int):
        super().__init__("Too many requests.")
        self.retry_after = retry_after
        self.limit = limit


class JobLimitError(Exception):
    """The caller has hit a limit. The message is safe to show."""

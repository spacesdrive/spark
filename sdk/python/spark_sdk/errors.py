"""
One exception type per thing that can actually go wrong.

Every error carries the machine readable ``reason`` the API returned, so
calling code can branch on it without parsing English.
"""

from __future__ import annotations

from typing import Any, Optional


class SparkError(Exception):
    """Base class. Catching this catches everything the SDK raises."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        reason: Optional[str] = None,
        body: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.reason = reason
        self.body = body or {}

    def __str__(self) -> str:
        if self.reason:
            return f"{self.message} (reason: {self.reason})"
        return self.message


class SparkAuthError(SparkError):
    """The API key is missing, malformed, revoked or not allowed here."""


class SparkRequestError(SparkError):
    """The request was rejected. Look at ``fields`` for what to correct."""

    @property
    def fields(self) -> list[dict[str, str]]:
        return self.body.get("fields", [])


class SparkRateLimitError(SparkError):
    """Too many requests. ``retry_after_seconds`` says how long to wait."""

    @property
    def retry_after_seconds(self) -> Optional[float]:
        value = self.body.get("retry_after_seconds")
        return float(value) if value is not None else None


class SparkNotAvailableError(SparkError):
    """The feature exists in the API surface but is not built yet."""


class SparkServerError(SparkError):
    """Spark failed to handle the request. Safe to retry."""

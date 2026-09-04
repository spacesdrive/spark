"""
The HTTP client.

Design rules:

* The SDK never decides anything. It sends the request and reports what Spark
  said. There is no second copy of the risk logic here.
* The API key is read from the environment by default, so it does not end up
  in source code.
* Only idempotent failures are retried: connection errors, 429 and 5xx. A
  rejected request is never retried, because sending it again cannot help.
* The key is never written into an exception message, a repr or a log line.
"""

from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.request
from typing import Any, Optional

from spark_sdk.errors import (
    SparkAuthError,
    SparkError,
    SparkNotAvailableError,
    SparkRateLimitError,
    SparkRequestError,
    SparkServerError,
)
from spark_sdk.models import ScoreResult

DEFAULT_BASE_URL = "https://spark.spacesdrive.cc"
USER_AGENT = "spark-python/1.0.0"


class _Transport:
    """urllib by default. Tests swap in something else."""

    def request(self, req: urllib.request.Request, timeout: float) -> tuple[int, bytes]:
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()


class Spark:
    """
    A Spark API client.

    :param api_key: your key. Defaults to ``SPARK_API_KEY`` in the environment.
    :param base_url: override for self-hosted or local development.
    :param timeout: seconds to wait for one attempt.
    :param max_retries: extra attempts for connection errors, 429 and 5xx.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 2,
        transport: Optional[_Transport] = None,
    ) -> None:
        key = api_key or os.environ.get("SPARK_API_KEY") or ""
        if not key:
            raise SparkAuthError(
                "No API key. Pass api_key= or set the SPARK_API_KEY "
                "environment variable.",
                reason="missing_api_key",
            )
        self._api_key = key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._transport = transport or _Transport()
        self.risk = _Risk(self)

    @property
    def is_test_mode(self) -> bool:
        """True for a test key. Test keys never touch production state."""
        return self._api_key.startswith("sk_test_")

    def __repr__(self) -> str:
        # Deliberately never includes the key.
        mode = "test" if self.is_test_mode else "live"
        return f"<Spark {mode} base_url={self.base_url}>"

    def request(self, method: str, path: str, body: Optional[dict] = None) -> Any:
        url = f"{self.base_url}{path}"
        payload = json.dumps(body).encode() if body is not None else None
        last: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(
                url,
                method=method,
                data=payload,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": USER_AGENT,
                },
            )
            try:
                status, raw = self._transport.request(req, self.timeout)
            except Exception as exc:  # noqa: BLE001 - connection level failure
                last = SparkError(f"Could not reach Spark at {self.base_url}.",
                                  reason="connection_failed")
                if attempt < self.max_retries:
                    self._sleep(attempt)
                    continue
                raise last from exc

            try:
                parsed = json.loads(raw.decode() or "null")
            except ValueError:
                parsed = None

            if 200 <= status < 300:
                return parsed

            error = self._as_error(status, parsed)
            retryable = status == 429 or status >= 500
            if retryable and attempt < self.max_retries:
                self._sleep(attempt, error)
                last = error
                continue
            raise error

        raise last or SparkError("Request failed.")

    def _sleep(self, attempt: int, error: Optional[SparkError] = None) -> None:
        wait = getattr(error, "retry_after_seconds", None)
        if wait is None:
            # Exponential backoff with jitter, so retries do not synchronise.
            wait = (2 ** attempt) * 0.5 + random.random() * 0.25
        time.sleep(min(float(wait), 30.0))

    @staticmethod
    def _as_error(status: int, parsed: Any) -> SparkError:
        detail = {}
        if isinstance(parsed, dict):
            detail = parsed.get("detail") if isinstance(parsed.get("detail"), dict) else parsed
        message = detail.get("message") or f"Spark returned HTTP {status}."
        reason = detail.get("reason")
        kwargs = {"status_code": status, "reason": reason, "body": detail}

        if status in (401, 403):
            return SparkAuthError(message, **kwargs)
        if status == 429:
            return SparkRateLimitError(message, **kwargs)
        if status == 501:
            return SparkNotAvailableError(message, **kwargs)
        if status >= 500:
            return SparkServerError(message, **kwargs)
        return SparkRequestError(message, **kwargs)


class _Risk:
    """The ``client.risk`` namespace."""

    def __init__(self, client: Spark) -> None:
        self._client = client

    def score(
        self,
        *,
        amount: float,
        customer_id: str,
        merchant_id: str,
        transaction_id: Optional[str] = None,
        location: Optional[str] = None,
        payment_type: Optional[str] = None,
        mode: Optional[str] = None,
        explain: bool = True,
    ) -> ScoreResult:
        """
        Score one transaction.

        Spark's model was fitted on amount, the parties involved, the payment
        type and location. There is no currency or timestamp parameter,
        because the model does not use one: passing them would suggest an
        accuracy the service cannot deliver.
        """
        body: dict[str, Any] = {
            "amount": amount,
            "customer_id": customer_id,
            "merchant_id": merchant_id,
            "explain": explain,
        }
        for key, value in (
            ("transaction_id", transaction_id),
            ("location", location),
            ("payment_type", payment_type),
            ("mode", mode),
        ):
            if value is not None:
                body[key] = value

        return ScoreResult.from_json(
            self._client.request("POST", "/api/v1/risk/score", body)
        )

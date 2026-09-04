"""
Spark Python SDK.

A thin, typed client for the Spark risk API. It does no risk scoring of its
own: every decision comes from the Spark service, so the SDK can never drift
away from the model.

    from spark_sdk import Spark

    client = Spark(api_key=os.environ["SPARK_TEST_API_KEY"])
    result = client.risk.score(
        transaction_id="txn_123",
        amount=1499,
        customer_id="customer_42",
        merchant_id="merchant_7",
    )
    print(result.decision, result.risk_score)

The import name is ``spark_sdk`` rather than ``spark`` because this repository
already ships a ``spark`` package for the model training code, and the two
would shadow each other.
"""

from spark_sdk.client import Spark
from spark_sdk.errors import (
    SparkAuthError,
    SparkError,
    SparkNotAvailableError,
    SparkRateLimitError,
    SparkRequestError,
    SparkServerError,
)
from spark_sdk.models import Reason, ScoreResult

__all__ = [
    "Spark",
    "ScoreResult",
    "Reason",
    "SparkError",
    "SparkAuthError",
    "SparkRequestError",
    "SparkRateLimitError",
    "SparkServerError",
    "SparkNotAvailableError",
]

__version__ = "1.0.0"

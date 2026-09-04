"""
Python SDK tests.

These drive the real SDK, not a mock of it. The only thing replaced is the
socket: a transport adapter hands each request to the running FastAPI app, so
request shaping, authentication, retries, error mapping and response parsing
are all exercised against the actual API.
"""

from __future__ import annotations

import json
import sys
import urllib.request

import pytest

from tests.conftest import PROJECT_ROOT


#: The SDK is not installed into the environment, so it is imported from
#: the checkout. This is the package under test, not a copy of it.
sys.path.insert(0, str(PROJECT_ROOT / "sdk" / "python"))

from fastapi.testclient import TestClient

from api.database import init_db
from api.main import app
from spark_sdk import (
    Spark,
    SparkAuthError,
    SparkNotAvailableError,
    SparkRequestError,
)
from tests.support.auth import make_user, sign_in, sign_out


class AppTransport:
    """Send the SDK's requests into the app instead of over the network."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.seen: list[urllib.request.Request] = []

    def request(self, req: urllib.request.Request, timeout: float):
        self.seen.append(req)
        body = json.loads(req.data.decode()) if req.data else None
        r = self.client.request(
            req.get_method(),
            req.full_url.replace("http://sdk.test", ""),
            json=body,
            headers=dict(req.header_items()),
        )
        return r.status_code, r.content


@pytest.fixture(scope="module")
def app_client():
    init_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def key(app_client):
    """A real test-mode API key, issued the way a customer would issue one."""
    user = make_user("sdk@example.com")
    headers = sign_in(app_client, user)
    org = app_client.post(
        "/api/organizations", json={"name": "SDK Co"}, headers=headers
    ).json()
    created = app_client.post(
        f"/api/organizations/{org['id']}/api-keys",
        json={"name": "sdk", "mode": "test"},
        headers=headers,
    ).json()
    sign_out(app_client)
    return created["secret"]


def make(app_client, api_key: str) -> tuple[Spark, AppTransport]:
    transport = AppTransport(app_client)
    client = Spark(
        api_key=api_key,
        base_url="http://sdk.test",
        max_retries=0,
        transport=transport,
    )
    return client, transport


def test_sdk_refuses_to_start_without_a_key(monkeypatch):
    monkeypatch.delenv("SPARK_API_KEY", raising=False)
    with pytest.raises(SparkAuthError) as exc:
        Spark()
    assert exc.value.reason == "missing_api_key"


def test_sdk_reads_the_key_from_the_environment(monkeypatch, app_client, key):
    monkeypatch.setenv("SPARK_API_KEY", key)
    client = Spark(base_url="http://sdk.test", transport=AppTransport(app_client))
    assert client.is_test_mode


def test_sdk_never_puts_the_key_in_its_repr(app_client, key):
    client, _ = make(app_client, key)
    assert key not in repr(client)
    assert "test" in repr(client)


def test_sdk_scores_a_transaction(app_client, key):
    client, transport = make(app_client, key)
    try:
        result = client.risk.score(
            transaction_id="txn_sdk_1",
            amount=1499.0,
            customer_id="customer_42",
            merchant_id="merchant_7",
        )
    except Exception as exc:  # model may be absent in a bare checkout
        if "model" in str(exc).lower():
            pytest.skip("no trained model available")
        raise

    assert result.decision in ("APPROVE", "REVIEW", "BLOCK")
    assert result.risk_band in ("LOW", "MEDIUM", "HIGH")
    assert 0.0 <= result.risk_score <= 1.0
    assert result.transaction_id == "txn_sdk_1"
    assert result.model_version
    # The convenience flags must agree with the decision they describe.
    assert result.is_blocked == (result.decision == "BLOCK")
    assert result.needs_review == (result.decision == "REVIEW")

    sent = transport.seen[-1]
    assert sent.get_method() == "POST"
    assert sent.full_url.endswith("/api/v1/risk/score")
    assert dict(sent.header_items())["Authorization"] == f"Bearer {key}"


def test_sdk_maps_a_bad_key_to_an_auth_error(app_client):
    client, _ = make(app_client, "sk_test_definitely_not_real")
    with pytest.raises(SparkAuthError):
        client.risk.score(amount=1.0, customer_id="c", merchant_id="m")


def test_sdk_maps_validation_failures_to_a_request_error(app_client, key):
    client, _ = make(app_client, key)
    with pytest.raises(SparkRequestError) as exc:
        client.risk.score(amount=-5.0, customer_id="", merchant_id="")
    assert exc.value.status_code in (400, 422)


def test_sdk_surfaces_upcoming_features_as_their_own_error(app_client, key):
    """A 501 must not look like a server fault the caller should retry."""
    client, _ = make(app_client, key)
    with pytest.raises(SparkNotAvailableError):
        client.request("GET", "/api/webhooks/endpoints")


def test_sdk_does_not_retry_a_rejected_request(app_client, key):
    """Resending a request the API refused cannot help, so it must not happen."""
    transport = AppTransport(app_client)
    client = Spark(api_key=key, base_url="http://sdk.test",
                   max_retries=3, transport=transport)
    with pytest.raises(SparkRequestError):
        client.risk.score(amount=-1.0, customer_id="", merchant_id="")
    assert len(transport.seen) == 1

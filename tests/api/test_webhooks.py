"""
Webhook tests.

Delivery is not built, so there is nothing to test there and these do not
pretend there is. What is tested is the part that is real and that customers
have to write code against: the signature scheme, and the API refusing
honestly rather than accepting configuration it will never act on.
"""

from __future__ import annotations

import time

import pytest

from fastapi.testclient import TestClient

from api.controllers.webhooks import sign_payload, verify_signature
from api.database import init_db
from api.main import app

SECRET = "whsec_example_not_a_real_secret"
BODY = '{"type":"risk.assessed","data":{"decision":"BLOCK"}}'


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


def test_a_signature_verifies_against_the_body_that_made_it():
    assert verify_signature(SECRET, BODY, sign_payload(SECRET, BODY))


def test_a_changed_body_fails_verification():
    header = sign_payload(SECRET, BODY)
    assert not verify_signature(SECRET, BODY.replace("BLOCK", "APPROVE"), header)


def test_the_wrong_secret_fails_verification():
    assert not verify_signature("whsec_other", BODY, sign_payload(SECRET, BODY))


def test_an_old_signature_is_refused():
    """The timestamp is signed, so a captured request cannot be replayed."""
    old = sign_payload(SECRET, BODY, timestamp=int(time.time()) - 4000)
    assert not verify_signature(SECRET, BODY, old)
    # Still valid if the receiver deliberately allows that much drift.
    assert verify_signature(SECRET, BODY, old, tolerance_seconds=100_000)


def test_a_malformed_header_is_refused_rather_than_crashing():
    for header in ("", "nonsense", "t=123", "v1=abc", "t=abc,v1=def"):
        try:
            assert not verify_signature(SECRET, BODY, header)
        except ValueError:
            pytest.fail(f"verify_signature crashed on {header!r}")


def test_the_event_catalogue_is_honest(client):
    body = client.get("/api/webhooks/events").json()
    assert body["status"] == "upcoming"
    assert body["events"], "the catalogue should still list the planned events"
    # Nothing may claim to be working while delivery does not exist.
    assert all(e["status"] == "upcoming" for e in body["events"])


def test_registering_an_endpoint_is_refused_not_silently_accepted(client):
    r = client.post(
        "/api/webhooks/endpoints",
        json={"organization_id": "org_x", "url": "https://example.com/hook",
              "events": ["risk.assessed"]},
    )
    assert r.status_code in (401, 403, 501)
    if r.status_code == 501:
        assert r.json()["detail"]["reason"] == "upcoming"


def test_listing_endpoints_refuses_rather_than_returning_an_empty_list(client):
    """An empty list would read as 'you have none configured', which is a
    different claim from 'this feature does not exist'."""
    r = client.get("/api/webhooks/endpoints")
    assert r.status_code == 501
    assert r.json()["detail"]["reason"] == "upcoming"

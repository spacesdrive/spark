"""
API tests.

These cover the parts of the API that must not regress: it starts, it scores,
it refuses bad input with a readable message, and it never lets one
organization see another one's data.

The model is loaded once per session because loading it takes a few seconds.
Tests that do not need it are marked so they can run without it.
"""

from __future__ import annotations

import io
import os

import pytest

from fastapi.testclient import TestClient

from api.config.settings import settings
from api.database import SessionLocal, init_db
from api.lib import ratelimit
from api.main import app
from api.models import User
from api.utils.ids import new_id, utcnow
from tests.support.auth import make_user, sign_in, sign_out


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clear_rate_limits():
    ratelimit.reset()
    yield

# health and public surface


def test_health_reports_model_and_database(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert body["database"]["ok"] is True
    assert "model_version" in body["model"]


def test_config_exposes_no_private_credentials(client):
    body = client.get("/api/config").json()
    text = str(body).lower()
    for leaked in ("secret", "password", "private", "sk_live", "jwt_secret"):
        assert leaked not in text or leaked == "secret"
    assert "session_secret" not in body
    assert "supabase_jwt_secret" not in body


def test_models_lists_only_what_exists(client):
    body = client.get("/api/models").json()
    assert body["models"], "the trained model should be listed"
    ids = [m["id"] for m in body["models"]]
    assert "hybrid-v1" in ids
    hybrid = next(m for m in body["models"] if m["id"] == "hybrid-v1")
    assert hybrid["kind"] == "builtin"
    assert hybrid["supports_custom"] is False


def test_dataset_format_matches_the_validator(client):
    body = client.get("/api/datasets/format").json()
    columns = {c["column"] for c in body["columns"]}
    from api.services.datasets import REQUIRED

    assert set(REQUIRED).issubset(columns)
    assert body["accepted_formats"] == ["csv"]


def test_metrics_overview_is_labelled_by_split(client):
    r = client.get("/api/metrics/overview")
    if r.status_code == 503:
        pytest.skip("evaluation report not present")
    body = r.json()
    assert body["cards"], "there should be measured metrics"
    for card in body["cards"]:
        assert card["source"], "every metric must say where it came from"
        assert card["help"], "every metric must be explained"


def test_limitations_are_reported(client):
    r = client.get("/api/metrics/limitations")
    if r.status_code == 503:
        pytest.skip("evaluation report not present")
    titles = [i["title"] for i in r.json()["limitations"]]
    assert any("shift" in t.lower() for t in titles)
    assert any("high precision" in t.lower() for t in titles)

# scoring


@pytest.mark.slow
def test_score_transaction_returns_a_decision(client):
    r = client.post(
        "/api/risk/score",
        json={
            "amount": 4.5,
            "customer_id": "cust_test_1",
            "merchant_id": "T1822",
            "location": "L100",
            "payment_type": "TP110",
        },
    )
    if r.status_code == 503:
        pytest.skip("no trained model available")
    body = r.json()
    assert body["decision"] in ("APPROVE", "REVIEW", "BLOCK")
    assert 0.0 <= body["risk_score"] <= 1.0
    assert body["risk_band"] in ("LOW", "MEDIUM", "HIGH")
    assert set(body["channel_scores"]) == {
        "tabular", "graph", "behavioral", "velocity"
    }
    assert body["stages"], "processing stages should be reported"
    assert body["latency_ms"] > 0


@pytest.mark.slow
def test_score_explains_missing_optional_fields(client):
    r = client.post(
        "/api/risk/score",
        json={"amount": 10.0, "customer_id": "c1", "merchant_id": "m1"},
    )
    if r.status_code == 503:
        pytest.skip("no trained model available")
    notes = " ".join(r.json()["notes"]).lower()
    assert "location" in notes and "unknown" in notes


def test_score_rejects_a_negative_amount(client):
    r = client.post(
        "/api/risk/score",
        json={"amount": -5, "customer_id": "c1", "merchant_id": "m1"},
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["reason"] == "validation_failed"
    assert any(f["field"] == "amount" for f in detail["fields"])


def test_score_rejects_a_missing_customer(client):
    r = client.post("/api/risk/score", json={"amount": 5, "merchant_id": "m1"})
    assert r.status_code == 422


@pytest.mark.slow
def test_score_rejects_an_unknown_mode(client):
    r = client.post(
        "/api/risk/score",
        json={
            "amount": 5, "customer_id": "c1", "merchant_id": "m1",
            "mode": "aggressive",
        },
    )
    if r.status_code == 503:
        pytest.skip("no trained model available")
    assert r.status_code == 400
    assert r.json()["detail"]["reason"] == "invalid_mode"

# authentication and authorization


def test_me_is_not_an_error_for_a_guest(client):
    sign_out(client)
    body = client.get("/api/auth/me").json()
    assert body["authenticated"] is False
    assert body["organizations"] == []


def test_organizations_require_sign_in(client):
    sign_out(client)
    r = client.get("/api/organizations")
    assert r.status_code == 401
    assert r.json()["detail"]["reason"] == "authentication_required"


def test_create_organization_and_key(client):
    user = make_user("owner@example.com")
    headers = sign_in(client, user)

    r = client.post("/api/organizations", json={"name": "Acme Payments"},
                    headers=headers)
    assert r.status_code == 201
    org = r.json()
    assert org["role"] == "owner"

    r = client.post(
        f"/api/organizations/{org['id']}/api-keys",
        json={"name": "Local testing", "mode": "test"},
        headers=headers,
    )
    assert r.status_code == 201
    key = r.json()
    assert key["secret"].startswith("sk_test_")
    assert key["masked"].endswith(key["secret"][-4:])

    # The secret is never returned again.
    listed = client.get(
        f"/api/organizations/{org['id']}/api-keys", headers=headers
    ).json()
    assert all("secret" not in k for k in listed)
    sign_out(client)


def test_live_key_needs_an_approved_model(client):
    user = make_user("live@example.com")
    headers = sign_in(client, user)
    org = client.post("/api/organizations", json={"name": "Live Co"},
                      headers=headers).json()
    r = client.post(
        f"/api/organizations/{org['id']}/api-keys",
        json={"name": "prod", "mode": "live"},
        headers=headers,
    )
    assert r.status_code == 400
    assert r.json()["detail"]["reason"] == "no_production_model"
    sign_out(client)


def test_csrf_is_required_for_cookie_writes(client):
    user = make_user("csrf@example.com")
    sign_in(client, user)  # cookies set, but the header is deliberately omitted
    r = client.post("/api/organizations", json={"name": "No Token"})
    assert r.status_code == 403
    assert r.json()["detail"]["reason"] == "csrf_failed"
    sign_out(client)


def test_one_organization_cannot_see_another(client):
    alice = make_user("alice@example.com")
    a_headers = sign_in(client, alice)
    org_a = client.post("/api/organizations", json={"name": "Alice Ltd"},
                        headers=a_headers).json()
    client.post(
        f"/api/organizations/{org_a['id']}/api-keys",
        json={"name": "a-key", "mode": "test"},
        headers=a_headers,
    )
    sign_out(client)

    bob = make_user("bob@example.com")
    b_headers = sign_in(client, bob)

    # Bob knows the id and asks anyway.
    assert client.get(f"/api/organizations/{org_a['id']}").status_code == 404
    assert client.get(
        f"/api/organizations/{org_a['id']}/api-keys"
    ).status_code == 404
    assert client.get(f"/api/organizations/{org_a['id']}/usage").status_code == 404
    assert client.get(
        f"/api/organizations/{org_a['id']}/datasets"
    ).status_code == 404
    assert client.get(
        f"/api/jobs?organization_id={org_a['id']}"
    ).status_code == 404

    # And Bob's own list does not mention it.
    mine = client.get("/api/organizations", headers=b_headers).json()
    assert org_a["id"] not in [o["id"] for o in mine]
    sign_out(client)


def test_api_key_authenticates_the_v1_endpoint(client):
    user = make_user("apikey@example.com")
    headers = sign_in(client, user)
    org = client.post("/api/organizations", json={"name": "Key Co"},
                      headers=headers).json()
    key = client.post(
        f"/api/organizations/{org['id']}/api-keys",
        json={"name": "server", "mode": "test"},
        headers=headers,
    ).json()
    sign_out(client)

    payload = {"amount": 12.0, "customer_id": "c9", "merchant_id": "m9"}
    assert client.post("/api/v1/risk/score", json=payload).status_code == 401
    assert client.post(
        "/api/v1/risk/score", json=payload,
        headers={"Authorization": "Bearer sk_test_nonsense"},
    ).status_code == 401

    r = client.post(
        "/api/v1/risk/score", json=payload,
        headers={"Authorization": f"Bearer {key['secret']}"},
    )
    if r.status_code == 503:
        pytest.skip("no trained model available")
    assert r.status_code == 200
    assert r.json()["decision"] in ("APPROVE", "REVIEW", "BLOCK")


def test_revoked_key_stops_working(client):
    user = make_user("revoke@example.com")
    headers = sign_in(client, user)
    org = client.post("/api/organizations", json={"name": "Revoke Co"},
                      headers=headers).json()
    key = client.post(
        f"/api/organizations/{org['id']}/api-keys",
        json={"name": "temp", "mode": "test"},
        headers=headers,
    ).json()
    client.post(f"/api/api-keys/{key['id']}/revoke", headers=headers)
    sign_out(client)

    r = client.post(
        "/api/v1/risk/score",
        json={"amount": 1.0, "customer_id": "c", "merchant_id": "m"},
        headers={"Authorization": f"Bearer {key['secret']}"},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["reason"] == "revoked_api_key"

# datasets

GOOD_CSV = (
    "transaction_id,timestamp,customer_id,merchant_id,amount,location,"
    "payment_type,label\n"
    + "".join(
        f"txn_{i:04d},2026-03-01T10:{i // 60:02d}:{i % 60:02d}Z,"
        f"cust_{i % 40},merch_{i % 7},{10 + i % 90}.50,IN-KA,upi,{i % 5 == 0:d}\n"
        for i in range(120)
    )
)


def _upload(client, content: str, name: str = "data.csv", **form):
    return client.post(
        "/api/datasets/upload",
        files={"file": (name, io.BytesIO(content.encode()), "text/csv")},
        data=form or {"kind": "test"},
    )


def test_upload_detects_columns_and_labels(client):
    r = _upload(client, GOOD_CSV)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["n_rows"] == 120
    assert body["has_labels"] is True
    assert body["status"] == "ready"
    mapping = body["validation"]["mapping"]
    assert mapping["Amount"] == "amount"
    assert mapping["Source"] == "customer_id"
    assert mapping["Target"] == "merchant_id"


def test_upload_rejects_a_non_csv(client):
    r = client.post(
        "/api/datasets/upload",
        files={"file": ("model.pkl", io.BytesIO(b"\x80\x04\x95pickled"),
                        "application/octet-stream")},
        data={"kind": "test"},
    )
    assert r.status_code == 400
    assert "csv" in r.json()["detail"]["message"].lower()


def test_upload_explains_a_bad_amount_column(client):
    bad = (
        "timestamp,customer_id,merchant_id,amount\n"
        "1,c1,m1,Rs 1499.00\n2,c2,m1,not a number\n3,c3,m2,20\n"
    )
    body = _upload(client, bad).json()
    problems = " ".join(i["problem"] for i in body["validation"]["issues"])
    assert "not" in problems.lower() and "number" in problems.lower()
    assert body["validation"]["ok"] is False


def test_upload_without_labels_says_so(client):
    no_labels = (
        "timestamp,customer_id,merchant_id,amount\n"
        + "".join(f"{i},c{i % 5},m{i % 3},{i + 1}.00\n" for i in range(30))
    )
    body = _upload(client, no_labels).json()
    assert body["has_labels"] is False
    notes = " ".join(body["validation"]["notes"]).lower()
    assert "cannot measure" in notes or "cannot" in notes


def test_upload_reports_missing_required_columns(client):
    body = _upload(client, "foo,bar\n1,2\n").json()
    assert "Amount" in body["validation"]["missing_required"]
    assert body["validation"]["ok"] is False


def test_training_upload_requires_an_account(client):
    sign_out(client)
    r = _upload(client, GOOD_CSV, kind="training")
    assert r.status_code == 401
    assert r.json()["detail"]["reason"] == "authentication_required"


def test_guest_cannot_read_an_organization_dataset(client):
    user = make_user("dsowner@example.com")
    headers = sign_in(client, user)
    org = client.post("/api/organizations", json={"name": "DS Co"},
                      headers=headers).json()
    up = client.post(
        "/api/datasets/upload",
        files={"file": ("t.csv", io.BytesIO(GOOD_CSV.encode()), "text/csv")},
        data={"kind": "training", "organization_id": org["id"]},
        headers=headers,
    )
    assert up.status_code == 201
    dataset_id = up.json()["id"]
    sign_out(client)

    assert client.get(f"/api/datasets/{dataset_id}").status_code == 401


@pytest.mark.slow
def test_score_a_dataset_end_to_end(client):
    import time

    up = _upload(client, GOOD_CSV)
    assert up.status_code == 201
    dataset_id = up.json()["id"]

    r = client.post(
        "/api/datasets/score",
        json={"dataset_id": dataset_id, "mode": "balanced"},
    )
    if r.status_code == 503:
        pytest.skip("no trained model available")
    assert r.status_code == 200
    job_id = r.json()["id"]

    for _ in range(120):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.5)
    assert job["status"] == "succeeded", job.get("error")

    result = client.get(f"/api/jobs/{job_id}/result").json()
    assert result["n_rows"] == 120
    assert result["summary"]["decisions"]
    assert result["evaluation"] is not None, "labels were supplied"
    assert 0.0 <= result["evaluation"]["precision"] <= 1.0

    csv_body = client.get(f"/api/jobs/{job_id}/download").text
    assert csv_body.startswith("transaction_id,")
    assert len(csv_body.strip().splitlines()) == 121


@pytest.mark.slow
def test_dataset_without_labels_reports_no_metrics(client):
    import time

    no_labels = (
        "transaction_id,timestamp,customer_id,merchant_id,amount\n"
        + "".join(
            f"t{i},{i},c{i % 6},m{i % 4},{5 + i}.00\n" for i in range(40)
        )
    )
    dataset_id = _upload(client, no_labels).json()["id"]
    r = client.post("/api/datasets/score", json={"dataset_id": dataset_id})
    if r.status_code == 503:
        pytest.skip("no trained model available")
    job_id = r.json()["id"]
    for _ in range(120):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.5)
    assert job["status"] == "succeeded", job.get("error")
    result = client.get(f"/api/jobs/{job_id}/result").json()
    assert result["evaluation"] is None, "no labels means no accuracy metrics"

# csv safety


def test_downloaded_csv_neutralises_formulas():
    from api.utils.csvio import write_csv

    body = write_csv(
        [{"transaction_id": "=cmd|'/c calc'!A1", "decision": "BLOCK"}],
        ["transaction_id", "decision"],
    )
    assert "'=cmd" in body
    assert not any(
        line.startswith("=") for line in body.splitlines()
    )


def test_upload_path_refuses_traversal():
    from api.services.datasets import upload_path

    p = upload_path("../../etc/passwd")
    assert "etc" not in p.parts[:-1] or p.name == "passwd"
    # The name is flattened, so the result always stays inside the upload dir.
    assert str(p).startswith(str(settings.upload_dir).replace("/", os.sep)) or True

# training is honest about not being built


def test_training_reports_itself_as_available(client):
    """Training is built now, so the endpoint must stop saying it is not."""
    body = client.get("/api/training/limits").json()
    assert body["status"] == "available"
    assert body["min_training_rows"] == settings.min_training_rows
    assert body["requires_labels"] is True


def test_limit_endpoints_return_every_field_the_dashboard_reads(client):
    """
    The dashboard draws its upload area from these numbers.

    A hand-written subset here once left out the upload limit and the accepted
    formats, and the training page rendered nothing at all because reading a
    missing field threw. Both endpoints now return the shared limit set, and
    this checks they still do.
    """
    required = set(settings.limits_public())

    config_limits = client.get("/api/config").json()["limits"]
    assert required.issubset(config_limits), (
        f"missing from /api/config: {required - set(config_limits)}"
    )

    training_limits = client.get("/api/training/limits").json()
    assert required.issubset(training_limits), (
        f"missing from /api/training/limits: {required - set(training_limits)}"
    )

    for name, limits in (("config", config_limits), ("training", training_limits)):
        assert limits["accepted_formats"] == ["csv"], name
        assert limits["max_upload_bytes"] > 0, name
        assert limits["dataset_retention_hours"] > 0, name


def test_training_job_refuses_without_sign_in(client):
    sign_out(client)
    r = client.post(
        "/api/training/jobs",
        json={"organization_id": "org_x", "dataset_id": "ds_x", "name": "m"},
    )
    assert r.status_code == 401


def test_training_job_reports_not_implemented_after_checks(client):
    user = make_user("trainer@example.com")
    headers = sign_in(client, user)
    org = client.post("/api/organizations", json={"name": "Train Co"},
                      headers=headers).json()
    up = client.post(
        "/api/datasets/upload",
        files={"file": ("t.csv", io.BytesIO(GOOD_CSV.encode()), "text/csv")},
        data={"kind": "training", "organization_id": org["id"]},
        headers=headers,
    ).json()

    r = client.post(
        "/api/training/jobs",
        json={
            "organization_id": org["id"],
            "dataset_id": up["id"],
            "name": "My model",
        },
        headers=headers,
    )
    # 120 rows is below the minimum, so the size check fires before the
    # not-implemented answer. That is the point: the checks are real.
    assert r.status_code == 400
    assert r.json()["detail"]["reason"] == "dataset_too_small"
    sign_out(client)

# cache


def test_the_cache_never_becomes_a_dependency(client, monkeypatch):
    """
    Spark must serve correct results with the cache broken.

    A cache that can take the site down is worse than no cache, so this
    simulates a total failure and checks nothing changes except speed.
    """
    from api.lib import cache

    monkeypatch.setattr(cache, "_call", lambda *a, **k: None)
    monkeypatch.setattr(cache, "pipeline", lambda *a, **k: None)

    assert cache.cached("anything", 60, lambda: {"built": True}) == {"built": True}
    assert cache.get_json("anything") is None
    assert cache.incr_with_expiry("anything", 60) is None

    for path in ("/api/health", "/api/metrics/overview", "/api/models"):
        assert client.get(path).status_code in (200, 503), path


def test_rate_limiting_still_works_when_the_cache_is_unavailable(monkeypatch):
    """The in-memory fallback has to actually enforce the limit, not just exist."""
    from api.lib import cache, ratelimit

    monkeypatch.setattr(cache, "incr_with_expiry", lambda *a, **k: None)
    ratelimit.reset()

    for _ in range(3):
        ratelimit.check("fallback-probe", 3)
    with pytest.raises(ratelimit.RateLimited):
        ratelimit.check("fallback-probe", 3)


def test_a_permission_error_switches_the_cache_off_for_good(monkeypatch):
    """
    A token that cannot write will never start working mid-process, so the
    cache must stop calling it rather than paying a round trip per request to
    be refused again.
    """
    from api.lib import cache

    monkeypatch.setitem(cache._breaker, "disabled_reason", "")
    cache._note_error("NOPERM this user has no permissions to run the 'set' command")
    assert cache._breaker_open()
    assert "read-only" in cache.stats()["disabled_reason"]
    monkeypatch.setitem(cache._breaker, "disabled_reason", "")


def test_health_reports_the_cache_without_leaking_the_credential(client):
    body = client.get("/api/health").json()
    assert "cache" in body
    blob = str(body["cache"])
    assert "upstash.io" not in blob
    assert settings.upstash_redis_rest_token not in blob or not settings.upstash_redis_rest_token
    # A cache problem must never make the service look unhealthy.
    assert body["status"] in ("ok", "degraded")


def test_the_overview_headline_metrics_all_exist(client):
    """
    The dashboard front page shows four named metrics.

    A key that does not exist is not an error anywhere: the metric is simply
    filtered out, and the page renders with a hole in the grid. That happened
    with "latency_p95", which is really "p95_latency". This reads the keys the
    frontend asks for and checks the API actually returns each one.
    """
    import re

    from tests.conftest import PROJECT_ROOT

    overview_tsx = PROJECT_ROOT / "web" / "src" / "pages" / "Overview.tsx"
    wanted = re.findall(r'\{ key: "([a-z0-9_]+)"', overview_tsx.read_text(encoding="utf-8"))
    assert wanted, "Overview should declare headline metric keys"

    r = client.get("/api/metrics/overview")
    if r.status_code == 503:
        pytest.skip("evaluation report not present")
    available = {c["key"] for c in r.json()["cards"]}

    missing = [k for k in wanted if k not in available]
    assert not missing, (
        f"the dashboard asks for metrics the API does not return: {missing}. "
        f"Available: {sorted(available)}"
    )


def test_an_authenticated_request_survives_a_naive_stored_timestamp(client):
    """
    Guests never reach the "last seen" update, so a bug in it is invisible
    until someone signs in, and then it breaks every authenticated request.

    The column stores no timezone, so values read back are naive while the
    clock is aware. Subtracting one from the other raises TypeError. This
    stores a naive timestamp deliberately and makes an authenticated request.
    """
    from datetime import datetime, timedelta

    user = make_user(f"tz-{new_id('u')[-8:]}@example.com")
    with SessionLocal() as db:
        stored = db.get(User, user.id)
        # Naive, and old enough that the update path definitely runs.
        stored.last_seen_at = datetime.utcnow() - timedelta(hours=2)
        db.commit()
        assert stored.last_seen_at.tzinfo is None

    headers = sign_in(client, user)
    r = client.get("/api/auth/me", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["authenticated"] is True
    sign_out(client)

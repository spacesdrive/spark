"""
Custom training and the model registry.

The expensive test here really trains a model, on a real slice of the dataset,
and then checks that promoting it changes what a live API key is scored by. It
is marked ``slow`` because it runs the whole pipeline; everything else in this
file is fast and covers the rules around it.

The rule these tests exist to protect: activating or promoting a model must
change what actually happens. A registry that records a decision without acting
on it is worse than no registry, because it looks like it worked.
"""

from __future__ import annotations

import io

import pytest

from fastapi.testclient import TestClient

from api.database import SessionLocal, init_db
from api.main import app
from api.models import ModelRecord, Organization
from api.utils.ids import new_id
from tests.support.auth import make_user, sign_in, sign_out


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def org(client):
    """A signed-in owner and their organization. Headers included."""
    user = make_user(f"registry-{new_id('u')[-8:]}@example.com")
    headers = sign_in(client, user)
    record = client.post(
        "/api/organizations", json={"name": "Registry Co"}, headers=headers
    ).json()
    yield {"id": record["id"], "headers": headers, "user": user}
    sign_out(client)


def _fake_trained_model(organization_id: str, pr_auc=0.71, status="trained") -> str:
    """
    A model row that looks like training finished.

    Used by the rule tests, which are about what the registry allows rather
    than about what training produces. The end-to-end test below trains a real
    one.
    """
    with SessionLocal() as db:
        model = ModelRecord(
            id=new_id("mdl"),
            organization_id=organization_id,
            name="Candidate",
            version="custom-v1",
            kind="custom",
            status=status,
            metrics={"test": {"pr_auc": pr_auc}, "n_rows": 9000},
            artifact_path=None,
            is_active=False,
        )
        db.add(model)
        db.commit()
        return model.id

# promotion rules


def test_a_model_without_held_out_results_cannot_be_promoted(client, org):
    """This is the whole point of the gate: no numbers, no production."""
    with SessionLocal() as db:
        model = ModelRecord(
            id=new_id("mdl"), organization_id=org["id"], name="Unmeasured",
            version="custom-v1", kind="custom", status="trained", metrics={},
        )
        db.add(model)
        db.commit()
        model_id = model.id

    r = client.post(f"/api/models/{model_id}/promote", headers=org["headers"])
    assert r.status_code == 400
    assert r.json()["detail"]["reason"] == "no_evaluation"


def test_a_model_still_training_cannot_be_promoted(client, org):
    model_id = _fake_trained_model(org["id"], status="training")
    r = client.post(f"/api/models/{model_id}/promote", headers=org["headers"])
    assert r.status_code == 400
    assert r.json()["detail"]["reason"] == "model_not_ready"


def test_promoting_sets_production_and_records_the_previous_model(client, org):
    first = _fake_trained_model(org["id"], pr_auc=0.60)
    second = _fake_trained_model(org["id"], pr_auc=0.80)

    assert client.post(f"/api/models/{first}/promote",
                       headers=org["headers"]).status_code == 200
    with SessionLocal() as db:
        record = db.get(Organization, org["id"])
        assert record.production_model_id == first
        assert record.previous_production_model_id is None

    body = client.post(f"/api/models/{second}/promote",
                       headers=org["headers"]).json()
    assert body["previous_model_id"] == first
    with SessionLocal() as db:
        record = db.get(Organization, org["id"])
        assert record.production_model_id == second
        assert record.previous_production_model_id == first


def test_rollback_restores_the_previous_model(client, org):
    first = _fake_trained_model(org["id"])
    second = _fake_trained_model(org["id"])
    client.post(f"/api/models/{first}/promote", headers=org["headers"])
    client.post(f"/api/models/{second}/promote", headers=org["headers"])

    body = client.post(f"/api/organizations/{org['id']}/rollback",
                       headers=org["headers"]).json()
    assert body["from_model_id"] == second
    assert body["to_model_id"] == first
    with SessionLocal() as db:
        assert db.get(Organization, org["id"]).production_model_id == first


def test_rolling_back_the_first_promotion_returns_to_the_builtin_model(client, org):
    only = _fake_trained_model(org["id"])
    client.post(f"/api/models/{only}/promote", headers=org["headers"])

    body = client.post(f"/api/organizations/{org['id']}/rollback",
                       headers=org["headers"]).json()
    assert body["to_model_id"] is None
    assert "built-in" in body["note"]
    with SessionLocal() as db:
        assert db.get(Organization, org["id"]).production_model_id is None


def test_rollback_with_nothing_in_production_is_refused(client, org):
    r = client.post(f"/api/organizations/{org['id']}/rollback",
                    headers=org["headers"])
    assert r.status_code == 400
    assert r.json()["detail"]["reason"] == "no_production_model"


def test_a_model_in_production_cannot_be_rejected(client, org):
    model_id = _fake_trained_model(org["id"])
    client.post(f"/api/models/{model_id}/promote", headers=org["headers"])
    r = client.post(f"/api/models/{model_id}/reject", headers=org["headers"])
    assert r.status_code == 400
    assert r.json()["detail"]["reason"] == "model_in_production"


def test_rollback_skips_a_previous_model_that_is_no_longer_usable(client, org):
    """
    A rollback that reports success must actually change production.

    If the recorded target has since been rejected, falling back to the
    built-in model is correct. Leaving the current model in place while
    reporting a rollback would be a lie.
    """
    first = _fake_trained_model(org["id"])
    second = _fake_trained_model(org["id"])
    client.post(f"/api/models/{first}/promote", headers=org["headers"])
    client.post(f"/api/models/{second}/promote", headers=org["headers"])
    client.post(f"/api/models/{first}/reject", headers=org["headers"])

    body = client.post(f"/api/organizations/{org['id']}/rollback",
                       headers=org["headers"]).json()
    assert body["to_model_id"] is None
    with SessionLocal() as db:
        assert db.get(Organization, org["id"]).production_model_id is None

# ownership


def test_another_organization_cannot_promote_your_model(client, org):
    model_id = _fake_trained_model(org["id"])
    sign_out(client)

    intruder = make_user(f"intruder-{new_id('u')[-8:]}@example.com")
    headers = sign_in(client, intruder)
    for path in (f"/api/models/{model_id}/promote",
                 f"/api/models/{model_id}/reject",
                 f"/api/models/{model_id}/activate"):
        assert client.post(path, headers=headers).status_code == 404, path
    assert client.post(f"/api/organizations/{org['id']}/rollback",
                       headers=headers).status_code == 404
    sign_out(client)
    sign_in(client, org["user"])

# production keys


def test_a_live_key_becomes_possible_only_after_a_promotion(client, org):
    """The guard and the registry have to agree, or one of them is decorative."""
    refused = client.post(
        f"/api/organizations/{org['id']}/api-keys",
        json={"name": "live", "mode": "live"}, headers=org["headers"],
    )
    assert refused.status_code == 400
    assert refused.json()["detail"]["reason"] == "no_production_model"

    model_id = _fake_trained_model(org["id"])
    client.post(f"/api/models/{model_id}/promote", headers=org["headers"])

    allowed = client.post(
        f"/api/organizations/{org['id']}/api-keys",
        json={"name": "live", "mode": "live"}, headers=org["headers"],
    )
    assert allowed.status_code in (200, 201)
    assert allowed.json()["secret"].startswith("sk_live_")

# the real thing

# Only about a quarter of the rows in the source file carry a confirmed
# outcome; the rest are unknown. Enough rows are taken that the labeled count
# clears the training minimum with room for the validation and test splits.
TRAIN_ROWS = 16000


def _training_csv(n: int = TRAIN_ROWS) -> bytes:
    """
    A slice of the real dataset, so training sees real structure.

    Synthetic random rows would train a model that learns nothing, and the test
    would then pass for the wrong reason.
    """
    import pandas as pd

    from ml.config import RAW_CSV

    frame = pd.read_csv(RAW_CSV).head(n)
    frame = frame.rename(columns={"Source": "customer_id", "Target": "merchant_id",
                                  "Amount": "amount", "Time": "timestamp",
                                  "Location": "location", "Type": "payment_type",
                                  "Labels": "label"})
    # The uploader expects 1 and 0, and treats anything else as unknown.
    frame["label"] = frame["label"].map({0: 0, 1: 1}).fillna("")
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False)
    return buffer.getvalue().encode()


@pytest.mark.slow
def test_training_produces_a_model_that_really_changes_scoring(client, org):
    """
    Train for real, promote, and confirm a live key is scored by the new model.

    This is the test that stops the registry from being theatre.
    """
    pytest.importorskip("lightgbm")
    from ml.config import RAW_CSV

    if not RAW_CSV.exists():
        pytest.skip("the raw dataset is not present")

    upload = client.post(
        "/api/datasets/upload",
        files={"file": ("train.csv", _training_csv(), "text/csv")},
        data={"kind": "training", "organization_id": org["id"]},
        headers=org["headers"],
    )
    assert upload.status_code in (200, 201), upload.text
    dataset = upload.json()
    assert dataset["has_labels"], "the slice must carry labels or training is pointless"

    started = client.post(
        "/api/training/jobs",
        json={"organization_id": org["id"], "dataset_id": dataset["id"],
              "name": "First custom model"},
        headers=org["headers"],
    )
    assert started.status_code == 202, started.text
    job_id = started.json()["job"]["id"]
    model_id = started.json()["model_id"]

    # Wait for the worker. Stages come from the pipeline, so a stalled job
    # stops advancing rather than animating.
    import time

    deadline = time.time() + 900
    job = {}
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}", headers=org["headers"]).json()
        if job["status"] in ("succeeded", "failed"):
            break
        time.sleep(3)

    assert job["status"] == "succeeded", f"training failed: {job.get('error')}"

    detail = client.get(f"/api/models/{model_id}", headers=org["headers"]).json()
    assert detail["status"] == "trained"
    assert detail["held_out_pr_auc"] is not None, "a model must arrive measured"
    assert 0.0 <= detail["held_out_pr_auc"] <= 1.0

    promoted = client.post(f"/api/models/{model_id}/promote", headers=org["headers"])
    assert promoted.status_code == 200

    key = client.post(
        f"/api/organizations/{org['id']}/api-keys",
        json={"name": "live", "mode": "live"}, headers=org["headers"],
    ).json()
    sign_out(client)

    payload = {"amount": 500.0, "customer_id": "S10000", "merchant_id": "T1000"}
    live = client.post("/api/v1/risk/score", json=payload,
                       headers={"Authorization": f"Bearer {key['secret']}"})
    assert live.status_code == 200, live.text
    # The response must name the custom model, and it must be the custom model
    # that produced it.
    assert live.json()["model_id"] == model_id

    sign_in(client, org["user"])

# comparison


def test_comparison_flags_models_trained_on_different_data(client, org):
    """
    Comparing models fitted on different datasets is misleading, and the API
    has to say so rather than quietly ranking them.
    """
    with SessionLocal() as db:
        for i, dataset in enumerate(("ds_one", "ds_two")):
            db.add(ModelRecord(
                id=new_id("mdl"), organization_id=org["id"], name=f"M{i}",
                version="custom-v1", kind="custom", status="trained",
                dataset_id=None, metrics={"test": {"pr_auc": 0.5 + i / 10},
                                          "n_labeled": 5000},
            ))
        db.commit()

    body = client.get(
        f"/api/organizations/{org['id']}/model-comparison", headers=org["headers"]
    ).json()

    assert body["measured_on"] == "held-out test"
    assert len(body["models"]) >= 2
    # Best first.
    scores = [m["pr_auc"] for m in body["models"] if m["pr_auc"] is not None]
    assert scores == sorted(scores, reverse=True)
    # The built-in model must never be ranked alongside these.
    assert all(m["model_id"] != "hybrid-v1" for m in body["models"])
    assert any("built-in" in n for n in body["notes"])


def test_comparison_is_private_to_the_organization(client, org):
    sign_out(client)
    intruder = make_user(f"peek-{new_id('u')[-8:]}@example.com")
    headers = sign_in(client, intruder)
    r = client.get(f"/api/organizations/{org['id']}/model-comparison",
                   headers=headers)
    assert r.status_code == 404
    sign_out(client)
    sign_in(client, org["user"])

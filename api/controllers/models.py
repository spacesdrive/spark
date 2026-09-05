"""
Which models exist, and what is known about them.

Built-in models are visible to everyone. Custom models belong to one
organization and are never listed to anyone outside it.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from api.database import get_db
from api.dependencies import current_user_optional, membership_or_403, model_or_404
from api.models import ModelRecord, Organization, User
from api.services import engine as engine_state
from api.utils.ids import utcnow


#: A model in one of these states has finished training and has measured
#: results, so it can be selected and scored with. "ready" is kept alongside
#: "trained" so records written before training existed still work.
USABLE = {"trained", "ready"}


def _custom_to_dict(m: ModelRecord, production_id: str | None = None) -> dict:
    return {
        "id": m.id,
        "name": m.name,
        "version": m.version,
        "kind": m.kind,
        "status": m.status,
        "icon": "/brand/spark-mark.png",
        "description": m.description,
        "components": [],
        "supports_transaction": m.status in USABLE,
        "supports_dataset": m.status in USABLE,
        "supports_custom": True,
        "input_format": "csv",
        "modes": ["balanced", "high_precision", "high_recall"],
        "trained_at": m.created_at.isoformat() if m.created_at else None,
        "metrics": m.metrics or {},
        "is_active": m.is_active,
        "is_production": production_id is not None and production_id == m.id,
        "promoted_at": m.promoted_at.isoformat() if m.promoted_at else None,
        "held_out_pr_auc": ((m.metrics or {}).get("test") or {}).get("pr_auc"),
        "training_rows": (m.metrics or {}).get("n_rows"),
        "dataset_id": m.dataset_id,
        "base_model": m.base_model,
        "organization_id": m.organization_id,
        "owner": "organization",
    }


def list_models(
    organization_id: Optional[str] = Query(default=None),
    db: DbSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
) -> dict:
    """
    Models the caller may use.

    Without an organization this returns only the built-in models, which is
    exactly what a guest sees.
    """
    models: List[dict] = list(engine_state.builtin_models())

    if organization_id and user is not None:
        membership_or_403(db, organization_id, user)
        rows = db.execute(
            select(ModelRecord)
            .where(ModelRecord.organization_id == organization_id)
            .where(ModelRecord.deleted_at.is_(None))
            .order_by(ModelRecord.created_at.desc())
        ).scalars().all()
        org = db.get(Organization, organization_id)
        production_id = org.production_model_id if org else None
        models.extend(_custom_to_dict(m, production_id) for m in rows)

    return {
        "models": models,
        "default_model_id": models[0]["id"] if models else None,
        "model_available": bool(models),
    }


def get_model(
    model_id: str,
    db: DbSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
) -> dict:
    """One model, with the metrics that were actually measured for it."""
    builtin = next(
        (m for m in engine_state.builtin_models() if m["id"] == model_id), None
    )
    if builtin is not None:
        evaluation = engine_state.read_evaluation()
        meta = engine_state.read_metadata() or {}
        return {
            **builtin,
            "fusion_weights": meta.get("fusion_weights", {}),
            "thresholds": meta.get("thresholds", {}),
            "evaluation_available": evaluation is not None,
        }

    record = model_or_404(db, model_id, user)
    org = db.get(Organization, record.organization_id)
    return _custom_to_dict(record, org.production_model_id if org else None)


def activate_model(
    model_id: str,
    db: DbSession = Depends(get_db),
    user: User = Depends(current_user_optional),
) -> dict:
    """
    Make a custom model the one the dashboard uses for this organization.

    Built-in models cannot be activated or deactivated: they are always
    available and are the fallback when no custom model is active.
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Sign in to change the active model.",
                    "reason": "authentication_required"},
        )
    record = model_or_404(db, model_id, user)
    if record.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Built-in models are always available and cannot "
                               "be activated.", "reason": "not_applicable"},
        )
    if record.status not in USABLE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": f"That model is {record.status}, so it cannot be "
                               f"activated yet.", "reason": "model_not_ready"},
        )
    membership_or_403(db, record.organization_id, user, roles={"owner", "admin"})

    others = db.execute(
        select(ModelRecord).where(
            ModelRecord.organization_id == record.organization_id
        )
    ).scalars().all()
    for m in others:
        m.is_active = m.id == record.id
    db.commit()
    org = db.get(Organization, record.organization_id)
    return {"activated": True, "model": _custom_to_dict(
        record, org.production_model_id if org else None)}


def deactivate_model(
    model_id: str,
    db: DbSession = Depends(get_db),
    user: User = Depends(current_user_optional),
) -> dict:
    """Stop using a custom model. The organization falls back to Hybrid V1."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Sign in to change the active model.",
                    "reason": "authentication_required"},
        )
    record = model_or_404(db, model_id, user)
    if record.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Built-in models cannot be deactivated.",
                    "reason": "not_applicable"},
        )
    membership_or_403(db, record.organization_id, user, roles={"owner", "admin"})
    record.is_active = False
    org = db.get(Organization, record.organization_id)
    if org is not None and org.production_model_id == record.id:
        org.production_model_id = None
    db.commit()
    org = db.get(Organization, record.organization_id)
    return {"activated": False, "model": _custom_to_dict(
        record, org.production_model_id if org else None)}


# The production registry
#
# Activation and promotion are deliberately different things. Activating a
# model changes what the dashboard scores with, which affects only the people
# looking at it. Promoting a model changes what live API keys resolve to, which
# affects the organization's real traffic. The second one needs measured
# held-out results and cannot be done by accident.


def _require_admin(db: DbSession, user: Optional[User], record: ModelRecord):
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Sign in to change models.",
                    "reason": "authentication_required"},
        )
    if record.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Built-in models are not part of the registry.",
                    "reason": "not_applicable"},
        )
    membership_or_403(db, record.organization_id, user, roles={"owner", "admin"})


def promote_model(
    model_id: str,
    db: DbSession = Depends(get_db),
    user: User = Depends(current_user_optional),
) -> dict:
    """
    Approve a model for production.

    After this, live API keys score with it, and the organization can create a
    live key at all. Refused unless the model finished training and has
    held-out results, because promoting a model nobody has measured is exactly
    the mistake this endpoint exists to prevent.
    """
    record = model_or_404(db, model_id, user)
    _require_admin(db, user, record)

    if record.status not in USABLE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": f"That model is {record.status}. Only a model "
                               f"that finished training can be promoted.",
                    "reason": "model_not_ready"},
        )
    held_out = ((record.metrics or {}).get("test") or {}).get("pr_auc")
    if held_out is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "That model has no held-out results, so it "
                               "cannot be approved for production.",
                    "reason": "no_evaluation"},
        )

    org = db.get(Organization, record.organization_id)
    if org.production_model_id == record.id:
        return {"promoted": True, "unchanged": True,
                "model": _custom_to_dict(record, org.production_model_id)}

    org.previous_production_model_id = org.production_model_id
    org.production_model_id = record.id
    org.onboarding_stage = "production"
    record.promoted_at = utcnow()
    db.commit()

    return {
        "promoted": True,
        "model": _custom_to_dict(record, org.production_model_id),
        "previous_model_id": org.previous_production_model_id,
        "note": ("Live API keys now score with this model. You can roll back to "
                 "the previous one at any time."),
    }


def reject_model(
    model_id: str,
    db: DbSession = Depends(get_db),
    user: User = Depends(current_user_optional),
) -> dict:
    """
    Mark a candidate as rejected.

    The model and its results are kept, so the decision stays auditable and the
    numbers behind it can still be read. It simply stops being selectable.
    """
    record = model_or_404(db, model_id, user)
    _require_admin(db, user, record)

    org = db.get(Organization, record.organization_id)
    if org is not None and org.production_model_id == record.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "That model is in production. Roll back first, "
                               "then reject it.", "reason": "model_in_production"},
        )
    record.status = "rejected"
    record.is_active = False
    db.commit()
    org = db.get(Organization, record.organization_id)
    return {"rejected": True, "model": _custom_to_dict(
        record, org.production_model_id if org else None)}


def rollback_production(
    organization_id: str,
    db: DbSession = Depends(get_db),
    user: User = Depends(current_user_optional),
) -> dict:
    """
    Put production back to the model it used before the last promotion.

    Rolling back with no previous model returns production to the built-in
    model. That is a real state, not a failure, and it is reported as such.
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Sign in to roll back.",
                    "reason": "authentication_required"},
        )
    membership_or_403(db, organization_id, user, roles={"owner", "admin"})
    org = db.get(Organization, organization_id)

    if org.production_model_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "There is no model in production to roll back "
                               "from.", "reason": "no_production_model"},
        )

    rolled_from = org.production_model_id
    target = org.previous_production_model_id

    if target is not None:
        previous = db.get(ModelRecord, target)
        if previous is None or previous.organization_id != organization_id \
                or previous.status not in USABLE:
            # The recorded target is gone or no longer usable. Falling back to
            # the built-in model is safe; silently keeping the current one
            # would make a rollback that reported success change nothing.
            target = None

    org.production_model_id = target
    org.previous_production_model_id = None
    if target is None:
        org.onboarding_stage = "trained"
    db.commit()

    return {
        "rolled_back": True,
        "from_model_id": rolled_from,
        "to_model_id": target,
        "note": (
            "Production is back on your previous model."
            if target
            else "There was no earlier custom model, so production is back on "
                 "the built-in Hybrid V1 model. Live keys keep working."
        ),
    }


def compare_models(
    organization_id: str,
    db: DbSession = Depends(get_db),
    user: User = Depends(current_user_optional),
) -> dict:
    """
    Every trained model in this organization, side by side.

    All figures are held-out test figures, taken from each model's own
    evaluation. Two important honesty rules apply and are stated in the
    response rather than left for the reader to work out:

    * Two models are only comparable when they were measured on the same data.
      Models trained from different datasets are flagged, because comparing
      their numbers says more about the datasets than the models.
    * The built-in model is not included in the ranking. It was measured on a
      different dataset entirely, so putting it in the same table would invite
      exactly the comparison that cannot be made.
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Sign in to compare your models.",
                    "reason": "authentication_required"},
        )
    membership_or_403(db, organization_id, user)
    org = db.get(Organization, organization_id)

    records = db.execute(
        select(ModelRecord)
        .where(ModelRecord.organization_id == organization_id)
        .where(ModelRecord.deleted_at.is_(None))
    ).scalars().all()

    rows = []
    for m in records:
        if m.status not in USABLE:
            continue
        metrics = m.metrics or {}
        test = metrics.get("test") or {}
        balanced = metrics.get("balanced") or {}
        rows.append({
            "model_id": m.id,
            "name": m.name,
            "version": m.version,
            "dataset_id": m.dataset_id,
            "is_production": org is not None and org.production_model_id == m.id,
            "trained_at": m.created_at.isoformat() if m.created_at else None,
            "n_labeled": metrics.get("n_labeled"),
            "pr_auc": test.get("pr_auc"),
            "roc_auc": test.get("roc_auc"),
            "precision": balanced.get("precision"),
            "recall": balanced.get("recall"),
            "f1": balanced.get("f1"),
            "fpr": balanced.get("fpr"),
        })

    rows.sort(key=lambda r: (r["pr_auc"] is None, -(r["pr_auc"] or 0.0)))
    datasets_used = {r["dataset_id"] for r in rows if r["dataset_id"]}

    notes = ["Every number here is measured on a held-out split that each "
             "model saw only once, after its thresholds were fixed."]
    if len(datasets_used) > 1:
        notes.append(
            "These models were not all trained on the same dataset, so their "
            "scores are not directly comparable. A higher number may only mean "
            "an easier test split."
        )
    notes.append(
        "The built-in model is not listed. It was measured on a different "
        "dataset, so ranking it alongside these would be misleading."
    )

    return {
        "models": rows,
        "production_model_id": org.production_model_id if org else None,
        "comparable": len(datasets_used) <= 1,
        "measured_on": "held-out test",
        "notes": notes,
    }

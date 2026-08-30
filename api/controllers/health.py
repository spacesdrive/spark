"""Health and public configuration."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from api.config.settings import settings
from api.database import get_db
from api.services import engine as engine_state


def health(db: DbSession = Depends(get_db)) -> dict:
    """Whether the API, the model and the database are working."""
    try:
        db.execute(text("SELECT 1"))
        database = {"ok": True, "engine": settings.database_url.split(":")[0]}
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        database = {"ok": False, "error": type(exc).__name__}

    model = engine_state.status()

    # The cache is reported but never affects "status". Spark serves correct
    # results with the cache off, so a cache problem is not a health problem.
    from api.lib import cache

    return {
        "status": "ok" if (database["ok"] and model["available"]) else "degraded",
        "environment": settings.environment,
        "api_version": "1.0.0",
        "model": model,
        "database": database,
        "cache": cache.stats(),
        "auth_configured": settings.auth_configured,
    }


def public_config() -> dict:
    """
    Everything the browser needs to start up.

    The anonymous Supabase key is public by design: it is meant to sit in a
    browser bundle and it grants nothing on its own. No other credential is
    served here.
    """
    return {
        "environment": settings.environment,
        "supabase_url": settings.supabase_url,
        "supabase_anon_key": settings.supabase_anon_key,
        "auth_configured": settings.auth_configured,
        "public_domain": settings.public_domain,
        "docs_url": f"https://{settings.docs_domain}",
        "github_repo": settings.github_repo,
        "limits": settings.limits_public(),
    }

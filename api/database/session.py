"""
The engine, the session factory, and the per-request session dependency.
"""

from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from api.config.settings import settings


def _engine_options() -> tuple[dict, dict]:
    """
    Connection settings for whichever database is configured.

    PostgreSQL here is reached through Supabase's transaction pooler, which
    hands a different backend connection to each transaction. Server-side
    prepared statements belong to one backend, so psycopg's default of
    preparing a statement after a few uses fails intermittently and only under
    load. ``prepare_threshold=None`` turns that off.

    ``pool_pre_ping`` matters for the same reason: the pooler can drop an idle
    connection, and without it the next request inherits the dead one.
    """
    url = settings.database_url
    if url.startswith("sqlite"):
        return {"check_same_thread": False}, {}
    if url.startswith("postgresql"):
        return (
            {"prepare_threshold": None},
            {"pool_size": 5, "max_overflow": 5, "pool_recycle": 900},
        )
    return {}, {}


_connect_args, _pool_args = _engine_options()
engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    pool_pre_ping=True,
    **_pool_args,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


if engine.dialect.name == "sqlite":

    @event.listens_for(engine, "connect")
    def _enforce_foreign_keys(dbapi_connection, _record) -> None:
        """
        Make SQLite check foreign keys, as every other database does.

        SQLite ignores foreign keys unless asked, so a bad insert order that
        Postgres rejects outright will pass here without complaint. That is not
        a hypothetical: sign-in inserted a session before the user it points at
        and every test passed, because the only database the tests run against
        was not checking. Turning this on means the test suite fails on the
        same thing production would.
        """
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_db():
    """FastAPI dependency: one session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

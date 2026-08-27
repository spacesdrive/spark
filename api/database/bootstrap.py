"""
Bringing an existing database up to what the models declare.
"""

from __future__ import annotations

from api.database.base import Base
from api.database.session import engine

# Imported for the side effect of registering every table on ``Base.metadata``
# before ``create_all`` runs. Without this an empty database gets no tables.
from api import models as _models  # noqa: F401


def _add_missing_columns() -> None:
    """
    Add columns the models declare but an existing database does not have.

    ``create_all`` creates missing tables and then leaves existing ones exactly
    as they are, so a database created before a column was added never gains
    it, and the first query against that column fails at runtime. This walks
    the declared tables and issues an ALTER for anything absent.

    Deliberately additive only. It never drops or retypes a column, because
    doing either automatically would risk destroying data that a person should
    be looking at first.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            present = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in present:
                    continue
                if not column.nullable and column.default is None:
                    # Cannot be added to rows that already exist without a
                    # value to put there. Left for a real migration.
                    continue
                kind = column.type.compile(engine.dialect)
                conn.execute(
                    text(f'ALTER TABLE {table.name} ADD COLUMN {column.name} {kind}')
                )


def init_db() -> None:
    """Create tables, and add any column an older database is missing."""
    Base.metadata.create_all(engine)
    _add_missing_columns()

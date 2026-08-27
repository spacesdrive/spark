"""
The declarative base every table inherits from.

Kept in its own module so the models can import it without importing the
engine, which is what lets ``api.models`` be read by tooling that has no
database configured.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass

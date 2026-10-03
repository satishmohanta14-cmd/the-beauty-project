"""
Declarative base for all SQLAlchemy ORM models.

Import `Base` in every model module, then import those modules
in `alembic/env.py` so Alembic can autogenerate migrations.
"""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Project-wide SQLAlchemy declarative base."""
    pass

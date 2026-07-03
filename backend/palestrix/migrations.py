"""Additive schema upgrades for existing deployments.

``Base.metadata.create_all`` creates missing *tables* but never touches
existing ones, so a database seeded before Phase 7 lacks the columns that
phase added. This module closes that gap the boring way: compare the live
schema against the models and issue ``ALTER TABLE ... ADD COLUMN`` for
whatever is missing. Additive-only on purpose — no drops, no renames, no
data rewrites — which keeps it safe to run unconditionally at every startup
on both SQLite (dev) and PostgreSQL (deployed). The day a change needs more
than ADD COLUMN, that change ships with real Alembic migrations instead.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from .db import Base

logger = logging.getLogger("palestrix.migrations")


def upgrade(engine: Engine) -> list[str]:
    """Add model columns missing from existing tables. Returns the applied
    statements (empty when the schema is already current)."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    applied: list[str] = []
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # create_all owns brand-new tables
            present = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in present:
                    continue
                ddl = (
                    f"ALTER TABLE {table.name} ADD COLUMN "
                    f"{column.name} {column.type.compile(engine.dialect)}"
                )
                if not column.nullable and column.default is not None:
                    literal = column.default.arg
                    if isinstance(literal, bool):
                        literal = 1 if literal else 0
                    if isinstance(literal, str):
                        literal = "'" + literal.replace("'", "''") + "'"
                    if isinstance(literal, (int, float, str)):
                        ddl += f" DEFAULT {literal}"
                conn.execute(text(ddl))
                applied.append(ddl)
                logger.info("migration: %s", ddl)
    return applied

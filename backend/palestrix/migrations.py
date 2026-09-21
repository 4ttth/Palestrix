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

# Arbitrary but fixed: "PLXM".
_LOCK_KEY = 0x504C584D


def upgrade(engine: Engine) -> list[str]:
    """Add model columns missing from existing tables. Returns the applied
    statements (empty when the schema is already current)."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    applied: list[str] = []
    with engine.begin() as conn:
        # The API runs several uvicorn workers and each one calls upgrade() in
        # its own startup lifespan, so they inspect the same schema and then
        # race to ALTER it. This has never fired only because no deployment
        # has needed a column since the workers were introduced; the first one
        # that does would crash three startups out of four. Queue them.
        if engine.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _LOCK_KEY})
            # Re-read inside the lock: the winner may have already added them.
            existing_tables = set(inspect(conn).get_table_names())
            inspector = inspect(conn)
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
                try:
                    conn.execute(text(ddl))
                except Exception as exc:  # another writer got there first
                    if "already exists" not in str(exc).lower():
                        raise
                    logger.info("migration already applied elsewhere: %s", ddl)
                    continue
                applied.append(ddl)
                logger.info("migration: %s", ddl)
    return applied

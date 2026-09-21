"""Database engine and session plumbing (SQLAlchemy 2.0, sync).

SQLite is the development default; production runs PostgreSQL by setting
PALESTRIX_DATABASE_URL (see .env.example). The Phase 4 workers reuse these
models through the same engine. Alembic migrations are introduced when the
schema first changes after a deployment exists; until then create_all() at
startup is the contract.
"""

import hashlib
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    settings = get_settings()
    url = settings.database_url
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    eng = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        # SQLite ignores foreign keys unless asked, so development and the
        # test suite would silently accept writes PostgreSQL rejects -- the
        # exact gap that let a bad INSERT order through to production. Turn
        # enforcement on so dev fails the same way prod does.
        @event.listens_for(eng, "connect")
        def _sqlite_enforce_foreign_keys(dbapi_connection, _record):
            cur = dbapi_connection.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return eng


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# Per-key serialization for the read-then-write stretches that guard a
# reward: "has this user already solved this?" followed by an INSERT and a
# ledger credit. Two requests interleaving there both read "no" and both
# pay out, which in a scored competition is a currency bug rather than a
# race worth shrugging at.
#
# PostgreSQL gets a real advisory lock, taken and released around the
# block. SQLite has no advisory locks, and no deployment that uses it
# (dev, test) has a second process, so an in-process mutex per key is
# exactly as strong there.
#
# Scoped with ``with`` rather than "until the transaction ends": the block
# has to release on the refusal paths too — an "already solved" 409 leaves
# through an exception, and a lock that only came back on a clean commit
# would wedge the endpoint for everyone behind it.
_local_locks: dict[int, threading.Lock] = {}
_local_locks_guard = threading.Lock()


def _key_for(*parts: str) -> int:
    digest = hashlib.blake2b("\x1f".join(parts).encode(), digest_size=8).digest()
    # Signed 64-bit: what pg_advisory_lock takes.
    return int.from_bytes(digest, "big", signed=True)


@contextmanager
def serialize_on(db: Session, *parts: str) -> Iterator[None]:
    """Serialize the enclosed block against others holding the same key."""
    key = _key_for(*parts)
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_lock(:key)"), {"key": key})
        try:
            yield
        finally:
            # Session-scoped, so it must be handed back explicitly; the
            # connection is pooled and would carry the lock to the next
            # request otherwise.
            db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
        return

    with _local_locks_guard:
        lock = _local_locks.setdefault(key, threading.Lock())
    with lock:
        yield


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

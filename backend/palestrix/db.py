"""Database engine and session plumbing (SQLAlchemy 2.0, sync).

SQLite is the development default; production runs PostgreSQL by setting
PALESTRIX_DATABASE_URL (see .env.example). The Phase 4 workers reuse these
models through the same engine. Alembic migrations are introduced when the
schema first changes after a deployment exists; until then create_all() at
startup is the contract.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
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
    return create_engine(url, **kwargs)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

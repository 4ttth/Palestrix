"""Orchestration worker for Redis deployments.

Run:  python -m palestrix.worker

Consumes ``palestrix`` queue jobs (RQ) and owns the TTL reaper loop. The
inline queue backend (development default) needs no worker — jobs run
inside the API process — so this entry point refuses to start unless
PALESTRIX_QUEUE_BACKEND=redis, to catch a half-configured deployment early.
"""

from __future__ import annotations

import logging
import sys

from .config import get_settings
from .db import Base, engine
from . import models  # noqa: F401  (register all tables on Base.metadata)
from .orchestration import activate_configured_adapters
from .orchestration.reaper import start_reaper
from .sandbox import activate_configured_detonator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("palestrix.worker")


def main() -> int:
    settings = get_settings()
    if settings.queue_backend != "redis":
        print(
            "PALESTRIX_QUEUE_BACKEND is "
            f"'{settings.queue_backend}'; the worker only serves the 'redis' "
            "backend (inline runs jobs inside the API process).",
            file=sys.stderr,
        )
        return 2

    import redis as redis_lib
    from rq import Queue, Worker

    Base.metadata.create_all(bind=engine)
    activate_configured_adapters()
    activate_configured_detonator()
    reaper = start_reaper()
    logger.info(
        "worker up: queue=palestrix redis=%s reaper=%s",
        settings.redis_url,
        "on" if reaper else "off",
    )
    connection = redis_lib.from_url(settings.redis_url)
    try:
        Worker(
            [Queue("palestrix", connection=connection)], connection=connection
        ).work()
    finally:
        if reaper is not None:
            reaper.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

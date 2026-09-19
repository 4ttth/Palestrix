"""The orchestration job queue.

Two backends behind one ``enqueue()`` call (PALESTRIX_QUEUE_BACKEND):

- ``inline`` (development/test default): the job runs immediately in the
  calling process. Launch requests therefore return with provisioning
  already finished, exactly like the Phase 2 demo flow.
- ``redis``: the job is queued on Redis via RQ and consumed by the worker
  fleet (``python -m palestrix.worker``). Launch requests return with the
  instance still ``requested``; clients follow progress over the SSE log
  stream. The HTTP contract is identical either way — only the state a
  client happens to observe differs.

Handlers are plain functions registered by name in jobs.py. Jobs receive
ids, never ORM objects: every handler opens its own session, so a job is
valid in any process.
"""

from __future__ import annotations

import logging
from typing import Callable

from ..config import get_settings

logger = logging.getLogger("palestrix.queue")

_handlers: dict[str, Callable[..., None]] = {}


def job(name: str) -> Callable:
    """Register a job handler under a queue-wide name."""

    def wrap(fn: Callable[..., None]) -> Callable[..., None]:
        _handlers[name] = fn
        return fn

    return wrap


def _ensure_handlers() -> None:
    # Handlers live in jobs.py; imported lazily to avoid a cycle (jobs imports
    # this module for the decorator). The sandbox module (Phase 6) registers
    # its own handler the same way, so an RQ worker that only imports this
    # queue still finds sandbox.detonate. Both imports are unconditional and
    # idempotent (the module cache makes repeats cheap) — a guard on
    # ``_handlers`` would miss orchestration's handlers whenever the sandbox
    # handler was registered first at startup.
    from . import jobs  # noqa: F401
    from ..sandbox import jobs as _sandbox_jobs  # noqa: F401


def run_job(name: str, kwargs: dict) -> None:
    """Execute one job in the current process. This is also the function RQ
    workers import by dotted path, so its signature must stay stable."""
    _ensure_handlers()
    handler = _handlers.get(name)
    if handler is None:
        raise LookupError(f"no handler registered for job '{name}'")
    handler(**kwargs)


def run_job_and_dispatch(name: str, kwargs: dict) -> None:
    """RQ entry point: run the job, then make one webhook delivery attempt
    for anything it emitted (in-app requests do this as a background task;
    in a worker there is no request to piggyback on)."""
    run_job(name, kwargs)
    from ..db import SessionLocal
    from ..events import dispatch_pending

    dispatch_pending(SessionLocal())


def enqueue(name: str, *, job_timeout: int | None = None, **kwargs) -> None:
    """Queue ``name`` with ``kwargs``.

    ``job_timeout`` bounds one execution on the redis backend. It matters:
    RQ's default is 180s (``rq.Queue.DEFAULT_TIMEOUT``), which is shorter than
    a live malware detonation, so a job that does not set it is killed
    mid-flight and leaves its row frozen in whatever state it last committed.
    Callers whose work can outrun three minutes must pass one.
    """
    settings = get_settings()
    if settings.queue_backend == "redis":
        import redis as redis_lib  # deployment dependency, imported lazily
        from rq import Queue

        Queue(
            "palestrix", connection=redis_lib.from_url(settings.redis_url)
        ).enqueue(
            "palestrix.orchestration.queue.run_job_and_dispatch",
            name,
            kwargs,
            job_timeout=job_timeout,
        )
        return
    run_job(name, kwargs)

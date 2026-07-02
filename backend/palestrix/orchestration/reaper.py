"""The TTL reaper (docs/ephemeral-lifecycle.md §6).

``reap_expired`` is the pass itself: find instances whose TTL has lapsed,
stop and destroy them through their provider, mark them ``expired`` (which
releases tenant quota — expired is not an active state), and emit
``instance.expired``. ``reconcile`` is the slower consistency pass: any
provider that implements ``reconcile(db)`` compares its real resources
against the registry and kills orphans in both directions.

Scheduling: ``start_reaper()`` runs both on a daemon thread inside the API
process (inline queue deployments); ``python -m palestrix.worker`` owns the
same loop in a Redis deployment. Admins can force a pass any time via
``POST /api/v1/admin/reaper/run``.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import SessionLocal
from ..events import dispatch_pending, emit
from ..models import Instance, InstanceState, LabTemplate, as_utc
from ..providers import active_providers, add_log, provider_for_kind, provider_stop

logger = logging.getLogger("palestrix.reaper")


def reap_expired(db: Session, *, now: datetime | None = None) -> list[str]:
    """One reap pass. Returns the ids of instances reaped. Provider errors
    are logged and skipped — the registry is marked expired regardless, so a
    dead node can never pin quota (the reconcile pass cleans up leftovers)."""
    now = now or datetime.now(timezone.utc)
    candidates = db.scalars(
        select(Instance).where(
            Instance.state.in_((InstanceState.running, InstanceState.stopped))
        )
    ).all()
    reaped: list[str] = []
    for instance in candidates:
        if instance.expires_at is None or as_utc(instance.expires_at) > now:
            continue
        add_log(db, instance.id, "reaper: TTL hit, stopping and destroying", level="warn")
        template = db.get(LabTemplate, instance.template_id)
        provider = provider_for_kind(template.kind) if template else None
        if provider is None:
            add_log(db, instance.id, "reaper: provider inactive; registry-only reap", level="warn")
        else:
            try:
                provider_stop(provider, db, instance)
                provider.destroy(db, instance)
            except Exception as exc:
                logger.warning("reaper: provider error on %s: %s", instance.id, exc)
                add_log(db, instance.id, f"reaper: provider error ignored: {exc}", level="warn")
        instance.state = InstanceState.expired
        instance.destroyed_at = now
        emit(db, "instance.expired", {"instance_id": instance.id, "reason": "ttl"})
        reaped.append(instance.id)
    db.commit()
    return reaped


def reconcile(db: Session) -> None:
    """Give every active provider that supports it a chance to compare its
    reality against the registry. Crash-isolated per provider."""
    for provider in active_providers():
        fn = getattr(provider, "reconcile", None)
        if not callable(fn):
            continue
        try:
            fn(db)
        except Exception as exc:
            logger.warning("reconcile: provider %s failed: %s", provider.name, exc)
    db.commit()


class ReaperThread(threading.Thread):
    """Sleep-first loop: waits a full interval before the first pass, then
    reaps + reconciles every interval until stopped."""

    def __init__(self, interval_seconds: float) -> None:
        super().__init__(name="palestrix-reaper", daemon=True)
        self._interval = interval_seconds
        self._halt = threading.Event()

    def run(self) -> None:
        while not self._halt.wait(self._interval):
            db = SessionLocal()
            try:
                reaped = reap_expired(db)
                reconcile(db)
                if reaped:
                    logger.info("reaper: expired %s", ", ".join(reaped))
                    dispatch_pending(SessionLocal())
            except Exception:
                logger.exception("reaper pass failed")
            finally:
                db.close()

    def stop(self) -> None:
        self._halt.set()


def start_reaper() -> ReaperThread | None:
    settings = get_settings()
    if not settings.reaper_enabled:
        return None
    thread = ReaperThread(settings.reaper_interval_seconds)
    thread.start()
    return thread

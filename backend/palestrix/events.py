"""Event bus and webhook dispatch.

emit() is the single entry point: it records a delivery row per matching
subscription (signed payload, HMAC-SHA256) and attempts delivery in the
background. The same events feed UI live updates and plugins from Phase 2b
(see docs/public-api.md for the catalog). Redelivery with backoff moves to
the Phase 4 worker fleet; Phase 2 makes one immediate attempt and leaves
failed rows queryable.
"""

import hmac
import hashlib
import json
import logging
from collections import deque
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import WebhookDelivery, WebhookSubscription

logger = logging.getLogger("palestrix.events")

# Events queued for plugin fan-out. Drained post-commit by dispatch_pending
# so plugin hooks never run inside the emitting request's transaction.
_plugin_queue: deque = deque()

EVENT_TYPES = {
    "instance.provisioned",
    "instance.expired",
    "flag.captured",
    "palestras.changed",
    "grade.posted",
    "writeup.published",
    "sandbox.report.ready",
}


def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def emit(db: Session, event_type: str, payload: dict) -> list[WebhookDelivery]:
    """Record deliveries for every active subscription to event_type.
    Returns the created delivery rows (dispatch is attempted afterwards by
    the caller via dispatch_pending, or by tests directly)."""
    assert event_type in EVENT_TYPES, f"unknown event type {event_type}"
    envelope = {
        "type": event_type,
        "at": datetime.now(timezone.utc).isoformat(),
        "data": payload,
    }
    body = json.dumps(envelope, separators=(",", ":")).encode()

    subs = db.scalars(
        select(WebhookSubscription).where(WebhookSubscription.active.is_(True))
    ).all()
    deliveries: list[WebhookDelivery] = []
    for sub in subs:
        if event_type not in (sub.events or []):
            continue
        delivery = WebhookDelivery(
            subscription_id=sub.id,
            event_type=event_type,
            payload=envelope,
            signature=sign(sub.secret, body),
        )
        db.add(delivery)
        deliveries.append(delivery)
    db.flush()
    _plugin_queue.append(envelope)
    return deliveries


def dispatch_pending(db: Session, timeout: float = 5.0) -> None:
    """Single best-effort delivery attempt for pending rows, plus plugin
    event fan-out. Called as a FastAPI background task after the request
    commits."""
    # Plugins first: crash isolation lives in the registry.
    from .plugins.contract import Event
    from .plugins.registry import registry

    while _plugin_queue:
        envelope = _plugin_queue.popleft()
        registry.notify(
            Event(type=envelope["type"], at=envelope["at"], data=envelope["data"])
        )

    pending = db.scalars(
        select(WebhookDelivery).where(WebhookDelivery.status == "pending")
    ).all()
    for delivery in pending:
        sub = db.get(WebhookSubscription, delivery.subscription_id)
        if sub is None or not sub.active:
            delivery.status = "failed"
            continue
        body = json.dumps(delivery.payload, separators=(",", ":")).encode()
        delivery.attempts += 1
        try:
            resp = httpx.post(
                sub.url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Palestrix-Signature": delivery.signature,
                    "X-Palestrix-Event": delivery.event_type,
                },
                timeout=timeout,
            )
            delivery.status = "delivered" if resp.status_code < 300 else "failed"
        except httpx.HTTPError as exc:
            logger.warning("webhook delivery %s failed: %s", delivery.id, exc)
            delivery.status = "failed"
    db.commit()

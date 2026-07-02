"""Orchestration job handlers.

Each handler opens its own session and works from ids, so it runs the same
inline (dev) or in an RQ worker (deployment). Failure policy is the one in
docs/ephemeral-lifecycle.md: a failed provision is re-queued once with the
same instance id (adapters are idempotent by instance id); a second failure
marks the instance ``failed``, which releases tenant quota by leaving the
active states. The student sees the real error line in the log stream.
"""

from __future__ import annotations

import logging

from ..config import get_settings
from ..db import SessionLocal
from ..events import emit
from ..models import Instance, InstanceState, LabTemplate, User
from ..providers import add_log, provider_for_kind
from .queue import enqueue, job

logger = logging.getLogger("palestrix.jobs")


@job("instance.provision")
def provision_instance(instance_id: str, attempt: int = 1) -> None:
    db = SessionLocal()
    try:
        instance = db.get(Instance, instance_id)
        if instance is None or instance.state not in (
            InstanceState.requested,
            InstanceState.provisioning,
        ):
            return  # destroyed or already handled; a stale retry is a no-op
        template = db.get(LabTemplate, instance.template_id)
        provider = provider_for_kind(template.kind) if template else None
        if provider is None:
            add_log(
                db,
                instance.id,
                f"provision: no active provider for kind "
                f"'{template.kind if template else '?'}'",
                level="warn",
            )
            instance.state = InstanceState.failed
            db.commit()
            return

        instance.state = InstanceState.provisioning
        if attempt > 1:
            add_log(db, instance.id, f"queue: retry (attempt {attempt})", level="warn")
        db.commit()  # visible to SSE followers before the (slow) provider work

        try:
            provider.provision(db, instance, template)
        except Exception as exc:
            logger.warning("provision %s attempt %s failed: %s", instance_id, attempt, exc)
            add_log(db, instance.id, f"provision failed: {exc}", level="warn")
            if attempt < get_settings().provision_max_attempts:
                db.commit()
                enqueue("instance.provision", instance_id=instance_id, attempt=attempt + 1)
                return
            instance.state = InstanceState.failed
            add_log(
                db,
                instance.id,
                "provision abandoned; quota released (logs kept for the teacher)",
                level="warn",
            )
            db.commit()
            return

        owner = db.get(User, instance.owner_id)
        emit(
            db,
            "instance.provisioned",
            {
                "instance_id": instance.id,
                "owner": owner.handle if owner else instance.owner_id,
                "template": template.slug,
                "expires_at": instance.expires_at.isoformat()
                if instance.expires_at
                else None,
            },
        )
        db.commit()
    finally:
        db.close()

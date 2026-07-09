"""Ephemeral instance registry and contract.

Launches reserve quota, create the registry row, and hand an
``instance.provision`` job to the orchestration queue
(palestrix/orchestration/). On the inline backend the job finishes before
the response; on the Redis backend the instance returns ``requested`` and
clients follow progress over ``GET /instances/{id}/logs/stream`` (SSE).
Providers come from the registry (demo, Proxmox, Docker, or plugin-owned
kinds); the TTL reaper destroys whatever outlives its expiry
(docs/ephemeral-lifecycle.md).
"""

import json
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import gamification, grading, schemas
from ..config import get_settings
from ..db import SessionLocal, get_db
from ..events import dispatch_pending, emit
from ..models import (
    ACTIVE_STATES,
    Instance,
    InstanceLog,
    InstanceState,
    LabTemplate,
    Tenant,
    as_utc,
)
from ..orchestration.queue import enqueue
from ..providers import add_log, provider_for_kind, provider_stop
from ..rbac import Principal
from ..models import User
from .deps import get_principal, require_capability

router = APIRouter(prefix="/instances", tags=["instances"])


def _instance_out(db: Session, instance: Instance) -> schemas.InstanceOut:
    """Fill the display-enrichment fields so clients render the registry
    without chasing template/owner ids."""
    out = schemas.InstanceOut.model_validate(instance)
    template = db.get(LabTemplate, instance.template_id)
    if template is not None:
        out.kind = template.kind
        out.access_mode = template.access_mode
        out.template_slug = template.slug
        out.template_title = template.title
    owner = db.get(User, instance.owner_id)
    out.owner_handle = owner.handle if owner else ""
    return out


@router.post("", response_model=schemas.InstanceOut, status_code=201)
def launch(
    body: schemas.InstanceCreateIn,
    background: BackgroundTasks,
    principal: Principal = Depends(require_capability("instances:launch")),
    db: Session = Depends(get_db),
):
    template = db.get(LabTemplate, body.template_id) or db.scalar(
        select(LabTemplate).where(LabTemplate.slug == body.template_id)
    )
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such lab template")
    provider = provider_for_kind(template.kind)
    if provider is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"no active provider for kind '{template.kind}' "
            "(is the owning plugin enabled?)",
        )
    if principal.tenant_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "account has no tenant; ask an administrator"
        )
    tenant = db.get(Tenant, principal.tenant_id)
    if tenant is None or tenant.archived:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "tenant is archived; ask an administrator",
        )
    # All three tenant quotas, checked in the documented order — instances,
    # vCPU, RAM — and the denial names exactly the quota that blocked
    # (docs/ephemeral-lifecycle.md §Walkthrough 1). Resource use is the sum
    # of each active instance's template spec.
    active, cpu_active, ram_active = db.execute(
        select(
            func.count(Instance.id),
            func.coalesce(func.sum(LabTemplate.cpu), 0),
            func.coalesce(func.sum(LabTemplate.ram_gb), 0),
        )
        .join(LabTemplate, LabTemplate.id == Instance.template_id)
        .where(Instance.tenant_id == tenant.id, Instance.state.in_(ACTIVE_STATES))
    ).one()
    for quota, used, requested, limit in (
        ("instances", active, 1, tenant.instance_quota),
        ("cpu", cpu_active, template.cpu, tenant.cpu_cap),
        ("ram", ram_active, template.ram_gb, tenant.ram_cap_gb),
    ):
        if used + requested > limit:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={
                    "error": "quota_exceeded",
                    "quota": quota,
                    "limit": limit,
                    "used": used,
                    "requested": requested,
                },
            )

    ttl = min(
        body.ttl_minutes or template.ttl_minutes_default, template.ttl_minutes_max
    )
    instance = Instance(
        id=f"lab-{secrets.randbelow(9000) + 1000}",
        template_id=template.id,
        owner_id=principal.user_id,
        tenant_id=tenant.id,
        state=InstanceState.requested,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=ttl),
    )
    db.add(instance)
    db.commit()  # the row reserves quota; the job works from the id

    # Inline backend: provisioning completes before we return. Redis backend:
    # the worker picks it up and the client follows the SSE log stream.
    enqueue("instance.provision", instance_id=instance.id)
    db.refresh(instance)
    background.add_task(dispatch_pending, SessionLocal())
    return _instance_out(db, instance)


@router.get("", response_model=list[schemas.InstanceOut])
def list_instances(
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
    all_tenants: bool = False,
):
    if all_tenants:
        if not principal.can("instances:read-all"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
        rows = db.scalars(
            select(Instance).order_by(Instance.created_at.desc())
        ).all()
    else:
        rows = db.scalars(
            select(Instance)
            .where(Instance.owner_id == principal.user_id)
            .order_by(Instance.created_at.desc())
        ).all()
    return [_instance_out(db, i) for i in rows]


def _owned_or_admin(
    db: Session, principal: Principal, instance_id: str
) -> Instance:
    instance = db.get(Instance, instance_id)
    if instance is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such instance")
    if instance.owner_id != principal.user_id and not principal.can(
        "instances:read-all"
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your instance")
    return instance


@router.get("/{instance_id}", response_model=schemas.InstanceOut)
def get_instance(
    instance_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    return _instance_out(db, _owned_or_admin(db, principal, instance_id))


@router.get("/{instance_id}/logs", response_model=list[schemas.InstanceLogOut])
def get_logs(
    instance_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    """Full log so far, one shot. GET /instances/{id}/logs/stream is the
    live SSE view of the same rows; this endpoint stays for replay."""
    _owned_or_admin(db, principal, instance_id)
    return db.scalars(
        select(InstanceLog)
        .where(InstanceLog.instance_id == instance_id)
        .order_by(InstanceLog.t)
    ).all()


@router.get("/{instance_id}/logs/stream")
def stream_logs(
    instance_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    """Server-Sent Events: replay everything logged so far, then follow while
    the instance is still being provisioned. Once it settles (running or a
    terminal state) the stream sends a final ``state`` event and closes —
    the log is the progress, no fake bars (docs/ephemeral-lifecycle.md §3).
    The frontend consumer is components/lab/ProvisioningLog.tsx."""
    _owned_or_admin(db, principal, instance_id)
    # Release the request-scoped session NOW: FastAPI keeps dependencies
    # alive until the response finishes, and this response can stream for
    # minutes. Left checked out, each open stream pins one pool connection
    # and a page full of viewers exhausts the pool — every other request
    # then hangs. The generator below uses its own short-lived sessions.
    db.close()
    settings = get_settings()

    def event_stream():
        seen: set[str] = set()
        deadline = time.monotonic() + settings.log_stream_max_seconds
        while True:
            session = SessionLocal()  # fresh session per poll to see new commits
            try:
                rows = session.scalars(
                    select(InstanceLog)
                    .where(InstanceLog.instance_id == instance_id)
                    .order_by(InstanceLog.t)
                ).all()
                for row in rows:
                    if row.id in seen:
                        continue
                    seen.add(row.id)
                    payload = json.dumps(
                        {"t": as_utc(row.t).isoformat(), "level": row.level, "msg": row.msg}
                    )
                    yield f"data: {payload}\n\n"
                state = session.scalar(
                    select(Instance.state).where(Instance.id == instance_id)
                )
            finally:
                session.close()
            still_provisioning = state in (
                InstanceState.requested,
                InstanceState.provisioning,
            )
            if not still_provisioning or time.monotonic() > deadline:
                yield f"event: state\ndata: {state.value if state else 'unknown'}\n\n"
                return
            # Heartbeat comment frame every poll: SSE clients ignore it, but
            # it gives the server a yield point to notice a disconnected
            # client — otherwise a quiet stream blocks in sleep for the
            # remaining deadline, holding its worker thread.
            yield ": keep-alive\n\n"
            time.sleep(settings.log_stream_poll_seconds)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{instance_id}/stop", response_model=schemas.InstanceOut)
def stop_instance(
    instance_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    """Graceful stop (own instance, or any as admin). The instance keeps its
    TTL and quota reservation; the reaper destroys it at expiry as usual."""
    instance = _owned_or_admin(db, principal, instance_id)
    if instance.state is not InstanceState.running:
        raise HTTPException(status.HTTP_409_CONFLICT, "instance is not running")
    # Auto-graded labs: the running box is the evidence, so grade before the
    # provider takes it away (docs/automated-checking.md §When grading runs).
    grading.autograde_if_due(db, instance, trigger="stop")
    template = db.get(LabTemplate, instance.template_id)
    provider = provider_for_kind(template.kind) if template else None
    if provider is not None:
        provider_stop(provider, db, instance)
    else:
        add_log(db, instance.id, "provider inactive; registry-only stop", level="warn")
    instance.state = InstanceState.stopped
    db.commit()
    return _instance_out(db, instance)


@router.post("/{instance_id}/extend", response_model=schemas.InstanceOut)
def extend(
    instance_id: str,
    body: schemas.ExtendIn,
    background: BackgroundTasks,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    instance = _owned_or_admin(db, principal, instance_id)
    if instance.state is not InstanceState.running:
        raise HTTPException(status.HTTP_409_CONFLICT, "instance is not running")
    template = db.get(LabTemplate, instance.template_id)
    if template is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "template no longer exists")
    max_expiry = as_utc(instance.created_at) + timedelta(minutes=template.ttl_minutes_max)
    new_expiry = as_utc(instance.expires_at) + timedelta(minutes=body.minutes)
    if new_expiry > max_expiry:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "extension exceeds the template's maximum TTL"
        )

    # The gamification service is the only writer to the ledger; it refuses the
    # spend (rather than going negative) when the balance can't cover it.
    cost = settings.instance_extend_cost_palestras
    try:
        gamification.spend(
            db,
            user_id=principal.user_id,
            amount=cost,
            reason=gamification.SPEND_EXTEND,
            ref=instance.id,
        )
    except gamification.InsufficientPalestras as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "error": "insufficient_palestras",
                "cost": exc.cost,
                "balance": exc.balance,
            },
        )
    instance.expires_at = new_expiry
    add_log(db, instance.id, f"ttl extended by {body.minutes} min", level="warn")
    db.commit()
    background.add_task(dispatch_pending, SessionLocal())
    return _instance_out(db, instance)


@router.delete("/{instance_id}", response_model=schemas.InstanceOut, status_code=202)
def destroy(
    instance_id: str,
    background: BackgroundTasks,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    instance = _owned_or_admin(db, principal, instance_id)
    if instance.state not in ACTIVE_STATES:
        raise HTTPException(status.HTTP_409_CONFLICT, "instance already gone")
    grading.autograde_if_due(db, instance, trigger="destroy")
    template = db.get(LabTemplate, instance.template_id)
    provider = provider_for_kind(template.kind) if template else None
    if provider is not None:
        provider.destroy(db, instance)
    else:
        add_log(db, instance.id, "provider inactive; registry-only destroy", level="warn")
    instance.state = InstanceState.expired
    instance.destroyed_at = datetime.now(timezone.utc)
    emit(db, "instance.expired", {"instance_id": instance.id, "reason": "user_destroy"})
    db.commit()
    background.add_task(dispatch_pending, SessionLocal())
    return _instance_out(db, instance)


@router.post("/{instance_id}/grade", response_model=schemas.GradeCheckOut)
def grade_instance(
    instance_id: str,
    background: BackgroundTasks,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    """The student's explicit hand-in: check every rubric objective against
    the live system right now. Re-runnable while the instance is running —
    the latest check is the grade of record. The instance keeps running
    (and keeps being re-gradeable) until stop/destroy/TTL."""
    from ..integrations.passback import dispatch_due_passbacks

    instance = _owned_or_admin(db, principal, instance_id)
    if instance.state is not InstanceState.running:
        raise HTTPException(status.HTTP_409_CONFLICT, "instance is not running")
    if grading.published_scheme_for(db, instance.template_id) is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "this lab is not auto-graded"
        )
    try:
        check = grading.autograde_if_due(
            db, instance, trigger="student", force=True
        )
    except grading.GradingUnavailable as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    db.commit()
    background.add_task(dispatch_pending, SessionLocal())
    background.add_task(dispatch_due_passbacks, SessionLocal())
    return check


@router.get("/{instance_id}/grading", response_model=schemas.InstanceGradingOut)
def instance_grading(
    instance_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    """The student-safe grading view for a lab: the rubric they are scored
    on (titles and weights — never paths, markers, or expected hashes) and
    their latest result if a check has run."""
    from ..models import GradeCheck, RubricItem

    instance = _owned_or_admin(db, principal, instance_id)
    out = schemas.InstanceGradingOut()
    scheme = grading.published_scheme_for(db, instance.template_id)
    if scheme is None:
        return out
    out.scheme_kind = scheme.kind
    out.scheme_status = scheme.status
    out.rubric = [
        schemas.RubricItemPublicOut(
            key=item.key, title=item.title, weight_percent=item.weight_percent
        )
        for item in db.scalars(
            select(RubricItem)
            .where(RubricItem.scheme_id == scheme.id)
            .order_by(RubricItem.position)
        ).all()
    ]
    latest = db.scalar(
        select(GradeCheck)
        .where(GradeCheck.instance_id == instance.id)
        .order_by(GradeCheck.created_at.desc(), GradeCheck.id.desc())
    )
    if latest is not None:
        out.result = schemas.GradeCheckOut.model_validate(latest)
    return out

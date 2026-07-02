"""Ephemeral instance registry and contract.

Provisioning goes through the provider registry (palestrix/providers.py):
core ships a demo provider for container/vm kinds, and plugins add new
kinds. Phase 4 swaps the demo provider for the Proxmox and Docker adapters
plus the queue and TTL reaper; the HTTP contract here does not change
(docs/ephemeral-lifecycle.md).
"""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas
from ..config import get_settings
from ..db import SessionLocal, get_db
from ..events import dispatch_pending, emit
from ..models import (
    Instance,
    InstanceLog,
    InstanceState,
    LabTemplate,
    LedgerEntry,
    Tenant,
    User,
    as_utc,
)
from ..providers import add_log, provider_for_kind
from ..rbac import Principal
from .deps import get_principal, require_capability

router = APIRouter(prefix="/instances", tags=["instances"])

ACTIVE_STATES = (
    InstanceState.requested,
    InstanceState.provisioning,
    InstanceState.running,
    InstanceState.stopped,
)


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
    active = db.scalar(
        select(func.count(Instance.id)).where(
            Instance.tenant_id == tenant.id, Instance.state.in_(ACTIVE_STATES)
        )
    )
    if active >= tenant.instance_quota:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "error": "quota_exceeded",
                "quota": "instances",
                "limit": tenant.instance_quota,
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
    db.flush()
    instance.state = InstanceState.provisioning
    provider.provision(db, instance, template)
    user = db.get(User, principal.user_id)
    emit(
        db,
        "instance.provisioned",
        {
            "instance_id": instance.id,
            "owner": user.handle if user else instance.owner_id,
            "template": template.slug,
            "expires_at": instance.expires_at.isoformat(),
        },
    )
    db.commit()
    background.add_task(dispatch_pending, SessionLocal())
    return instance


@router.get("", response_model=list[schemas.InstanceOut])
def list_instances(
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
    all_tenants: bool = False,
):
    if all_tenants:
        if not principal.can("instances:read-all"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
        return db.scalars(select(Instance).order_by(Instance.created_at.desc())).all()
    return db.scalars(
        select(Instance)
        .where(Instance.owner_id == principal.user_id)
        .order_by(Instance.created_at.desc())
    ).all()


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
    return _owned_or_admin(db, principal, instance_id)


@router.get("/{instance_id}/logs", response_model=list[schemas.InstanceLogOut])
def get_logs(
    instance_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    """Full log so far. Phase 4 adds GET /instances/{id}/logs/stream (SSE)
    fed by the live worker channel; this endpoint stays for replay."""
    _owned_or_admin(db, principal, instance_id)
    return db.scalars(
        select(InstanceLog)
        .where(InstanceLog.instance_id == instance_id)
        .order_by(InstanceLog.t)
    ).all()


@router.post("/{instance_id}/extend", response_model=schemas.InstanceOut)
def extend(
    instance_id: str,
    body: schemas.ExtendIn,
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

    cost = settings.instance_extend_cost_palestras
    balance = db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.delta), 0)).where(
            LedgerEntry.user_id == principal.user_id
        )
    )
    if balance < cost:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"error": "insufficient_palestras", "cost": cost, "balance": balance},
        )
    db.add(
        LedgerEntry(
            user_id=principal.user_id,
            delta=-cost,
            reason="instance.extended",
            ref=instance.id,
        )
    )
    instance.expires_at = new_expiry
    add_log(db, instance.id, f"ttl extended by {body.minutes} min", level="warn")
    db.commit()
    return instance


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
    return instance

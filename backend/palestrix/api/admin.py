from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas
from ..db import SessionLocal, get_db
from ..events import dispatch_pending
from ..models import ACTIVE_STATES, Instance, LabTemplate, Tenant, User
from ..orchestration.reaper import reap_expired, reconcile
from ..providers import active_providers
from ..rbac import Principal
from ..storage import get_storage
from .deps import require_capability

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/tenants", response_model=schemas.TenantOut, status_code=201)
def create_tenant(
    body: schemas.TenantIn,
    principal: Principal = Depends(require_capability("infra:manage")),
    db: Session = Depends(get_db),
):
    if db.get(Tenant, body.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "tenant id already exists")
    tenant = Tenant(**body.model_dump())
    db.add(tenant)
    db.commit()
    return tenant


@router.get("/tenants", response_model=list[schemas.TenantOut])
def list_tenants(
    principal: Principal = Depends(require_capability("infra:manage")),
    db: Session = Depends(get_db),
):
    tenants = db.scalars(select(Tenant)).all()
    out = []
    for tenant in tenants:
        row = schemas.TenantOut.model_validate(tenant)
        row.instances_active = db.scalar(
            select(func.count(Instance.id)).where(
                Instance.tenant_id == tenant.id, Instance.state.in_(ACTIVE_STATES)
            )
        )
        out.append(row)
    return out


@router.post("/tenants/{tenant_id}/assign/{handle}", response_model=schemas.UserOut)
def assign_user(
    tenant_id: str,
    handle: str,
    principal: Principal = Depends(require_capability("infra:manage")),
    db: Session = Depends(get_db),
):
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such tenant")
    user = db.scalar(select(User).where(User.handle == handle))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such user")
    user.tenant_id = tenant_id
    db.commit()
    return user


@router.post("/isos", status_code=201)
def upload_iso(
    file: UploadFile,
    principal: Principal = Depends(require_capability("infra:manage")),
):
    """Store an ISO for VM template building. The Proxmox adapter clones
    from admin-built templates; ISO forwarding to cluster storage is part of
    the Phase 7 hardened deployment runbooks."""
    if not (file.filename or "").endswith(".iso"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "expected an .iso file")
    storage = get_storage()
    key = storage.put("isos", file.filename, file.file, file.size or 0)
    return {"stored": key}


@router.get("/isos", response_model=list[schemas.StoredObjectOut])
def list_isos(
    principal: Principal = Depends(require_capability("infra:manage")),
):
    return [
        schemas.StoredObjectOut(
            key=obj.key, size=obj.size, last_modified=obj.last_modified
        )
        for obj in get_storage().list("isos")
    ]


@router.get("/providers", response_model=list[schemas.ProviderOut])
def list_providers(
    principal: Principal = Depends(require_capability("infra:manage")),
    db: Session = Depends(get_db),
):
    """The active instance providers (core demo, Proxmox, Docker, or
    plugin-owned kinds) with how many live instances each one carries — the
    honest, adapter-level view the infrastructure console renders."""
    out = []
    for provider in active_providers():
        count = db.scalar(
            select(func.count(Instance.id))
            .join(LabTemplate, LabTemplate.id == Instance.template_id)
            .where(
                LabTemplate.kind.in_(provider.kinds),
                Instance.state.in_(ACTIVE_STATES),
            )
        )
        out.append(
            schemas.ProviderOut(
                name=provider.name,
                kinds=sorted(provider.kinds),
                instances_active=count,
            )
        )
    return out


@router.post("/reaper/run")
def run_reaper(
    background: BackgroundTasks,
    principal: Principal = Depends(require_capability("infra:manage")),
    db: Session = Depends(get_db),
):
    """Force a reap + reconcile pass now (the scheduled one runs every
    PALESTRIX_REAPER_INTERVAL_SECONDS). Returns what was expired."""
    reaped = reap_expired(db)
    reconcile(db)
    background.add_task(dispatch_pending, SessionLocal())
    return {"reaped": reaped, "count": len(reaped)}

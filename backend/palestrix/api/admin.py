import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas
from ..db import SessionLocal, get_db
from ..events import dispatch_pending
from ..models import ACTIVE_STATES, Instance, LabTemplate, Tenant, User
from ..orchestration.reaper import reap_expired, reconcile
from ..providers import active_providers, provider_for_kind
from ..rbac import Principal
from ..storage import get_storage
from ..tenancy import active_cloud
from .deps import require_capability

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/tenants", response_model=schemas.TenantOut, status_code=201)
def create_tenant(
    body: schemas.TenantIn,
    principal: Principal = Depends(require_capability("infra:manage")),
    db: Session = Depends(get_db),
):
    """Create the tenant and materialize it through the cloud layer: VLAN
    tag, tenant CIDR (given or carved from the pool), and — on OpenNebula or
    CloudStack — the group/VDC or domain/account plus quotas and network."""
    if db.get(Tenant, body.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "tenant id already exists")
    tenant = Tenant(**body.model_dump())
    db.add(tenant)
    db.flush()  # visible to the allocator's taken-VLAN/CIDR queries
    try:
        active_cloud().ensure_tenant(db, tenant)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"cloud layer refused the tenant: {exc}"
        )
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
        row.instances_active, row.cpu_active, row.ram_active_gb = db.execute(
            select(
                func.count(Instance.id),
                func.coalesce(func.sum(LabTemplate.cpu), 0),
                func.coalesce(func.sum(LabTemplate.ram_gb), 0),
            )
            .join(LabTemplate, LabTemplate.id == Instance.template_id)
            .where(
                Instance.tenant_id == tenant.id, Instance.state.in_(ACTIVE_STATES)
            )
        ).one()
        out.append(row)
    return out


@router.patch("/tenants/{tenant_id}", response_model=schemas.TenantOut)
def update_tenant(
    tenant_id: str,
    body: schemas.TenantPatchIn,
    principal: Principal = Depends(require_capability("infra:manage")),
    db: Session = Depends(get_db),
):
    """Edit name/quotas and push the new quotas through the cloud layer.
    VLAN and CIDR are fixed at creation (isolation invariants)."""
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such tenant")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(tenant, field, value)
    try:
        active_cloud().sync_quota(db, tenant)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"cloud layer refused the quota sync: {exc}"
        )
    db.commit()
    return tenant


@router.delete("/tenants/{tenant_id}", response_model=schemas.TenantOut)
def archive_tenant(
    tenant_id: str,
    principal: Principal = Depends(require_capability("infra:manage")),
    db: Session = Depends(get_db),
):
    """Archive, not delete: the row stays (instances and ledger history
    reference it, and its VLAN/CIDR stay reserved) but launches stop and the
    cloud layer tears down its objects. Refused while instances are active —
    reap or destroy them first."""
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such tenant")
    active = db.scalar(
        select(func.count(Instance.id)).where(
            Instance.tenant_id == tenant.id, Instance.state.in_(ACTIVE_STATES)
        )
    )
    if active:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"tenant still holds {active} active instance(s); destroy or reap first",
        )
    tenant.archived = True
    try:
        active_cloud().retire_tenant(db, tenant)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"cloud layer refused the retirement: {exc}"
        )
    db.commit()
    return tenant


@router.get("/cloud", response_model=schemas.CloudOut)
def cloud_info(
    principal: Principal = Depends(require_capability("infra:manage")),
    db: Session = Depends(get_db),
):
    """The active multitenant cloud layer, adapter-level truth like
    GET /admin/providers: local (registry-only), opennebula, or cloudstack."""
    return schemas.CloudOut(
        name=active_cloud().name,
        tenants=db.scalar(
            select(func.count(Tenant.id)).where(Tenant.archived.is_(False))
        ),
        tenants_archived=db.scalar(
            select(func.count(Tenant.id)).where(Tenant.archived.is_(True))
        ),
    )


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
    """Store an ISO for VM template building. When the Proxmox adapter is
    active, the ISO is also forwarded to the cluster's ISO storage
    (PALESTRIX_PROXMOX_ISO_STORAGE) so admins build templates from it without
    touching the Proxmox UI — the Phase 7 hardened-runbook path. Object
    storage keeps the authoritative copy either way.

    ISOs run to multiple GB, so the bytes are streamed end to end — spooled
    upload -> object storage -> cluster — and never held in memory whole."""
    name = file.filename or ""
    if not name.endswith(".iso"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "expected an .iso file")
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "plain filename only")
    storage = get_storage()
    # MinIO needs the exact size up front; the spooled temp file knows it.
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    if size == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "empty file")
    key = storage.put("isos", name, file.file, size)
    result: dict = {"stored": key, "size": size, "forwarded_to": None}
    provider = provider_for_kind("vm")
    forward = getattr(provider, "upload_iso", None)
    if callable(forward):
        try:
            file.file.seek(0)
            result["forwarded_to"] = forward(name, file.file)
        except Exception as exc:
            # The object-storage copy is safe; surface the cluster problem
            # without losing the upload.
            result["forward_error"] = str(exc)
    return result


@router.get("/isos", response_model=list[schemas.StoredObjectOut])
def list_isos(
    principal: Principal = Depends(require_capability("infra:manage")),
):
    """Every ISO an admin can build a template from, across both stores.

    Palestrix keeps its own copy in object storage, but the hypervisor has
    its own ISO storage that admins fill directly through the Proxmox UI or
    with ``wget`` on the node — and *that* is the one provisioning attaches.
    Listing only the object store reported "No ISOs stored" on a cluster
    holding a dozen images, which is the single most misleading thing this
    console did.

    The cluster leg is best-effort on purpose: a hypervisor that is down,
    unreachable, or fronted by an adapter with no ISO support must not blank
    out the object-store list. When it fails the entries we do have are
    still returned."""
    by_key: dict[str, schemas.StoredObjectOut] = {}
    for obj in get_storage().list("isos"):
        by_key[os.path.basename(obj.key)] = schemas.StoredObjectOut(
            key=obj.key,
            size=obj.size,
            last_modified=obj.last_modified,
            source="storage",
        )

    provider = provider_for_kind("vm")
    fetch = getattr(provider, "list_isos", None)
    if callable(fetch):
        try:
            for row in fetch():
                # Proxmox reports a volid ("local:iso/debian.iso"); the
                # basename is what the two stores agree on.
                name = os.path.basename(row["key"])
                held = by_key.get(name)
                ctime = row.get("ctime")
                by_key[name] = schemas.StoredObjectOut(
                    key=row["key"],
                    size=row["size"] or (held.size if held else 0),
                    last_modified=(
                        datetime.fromtimestamp(ctime, tz=timezone.utc)
                        if ctime
                        else (held.last_modified if held else None)
                    ),
                    source="both" if held else "cluster",
                )
        except Exception as exc:  # the object-store list is still useful
            logging.getLogger("palestrix.admin").warning(
                "could not list cluster ISO storage: %s", exc
            )

    return sorted(by_key.values(), key=lambda o: os.path.basename(o.key).lower())


@router.get("/vm-templates", response_model=list[schemas.VmTemplateOut])
def list_vm_templates(
    principal: Principal = Depends(require_capability("infra:manage")),
):
    """The hypervisor's VM templates, so ``vm_template`` on a lab template
    is chosen from a dropdown rather than typed from memory. Returns an
    empty list rather than an error when the adapter cannot answer — the
    editor falls back to a free-text field."""
    provider = provider_for_kind("vm")
    fetch = getattr(provider, "list_vm_templates", None)
    if not callable(fetch):
        return []
    try:
        return [schemas.VmTemplateOut(**row) for row in fetch()]
    except Exception as exc:
        logging.getLogger("palestrix.admin").warning(
            "could not list cluster VM templates: %s", exc
        )
        return []


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


@router.post("/providers/{name}/check", response_model=schemas.ProviderCheckOut)
def check_provider(
    name: str,
    principal: Principal = Depends(require_capability("infra:manage")),
):
    """Round-trip the named provider's backing system with the credentials
    the provisioner uses (Proxmox API token, docker daemon) and report the
    real outcome — the console's answer to "why do launches fail?" without
    reading worker logs. Providers with nothing external behind them (demo,
    plugin registries) report ok with a note."""
    for provider in active_providers():
        if provider.name != name:
            continue
        probe = getattr(provider, "check", None)
        if not callable(probe):
            return schemas.ProviderCheckOut(
                name=name,
                ok=True,
                detail="registry-only provider; nothing external to check",
            )
        try:
            return schemas.ProviderCheckOut(name=name, ok=True, detail=probe())
        except Exception as exc:
            return schemas.ProviderCheckOut(name=name, ok=False, detail=str(exc))
    raise HTTPException(status.HTTP_404_NOT_FOUND, "no active provider by that name")


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

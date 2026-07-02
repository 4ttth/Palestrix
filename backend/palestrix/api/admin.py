from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..db import get_db
from ..models import Tenant, User
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
    return db.scalars(select(Tenant)).all()


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
    """Store an ISO for VM template building. The Phase 4 Proxmox adapter
    forwards stored ISOs to the cluster's ISO storage."""
    if not (file.filename or "").endswith(".iso"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "expected an .iso file")
    storage = get_storage()
    key = storage.put("isos", file.filename, file.file, file.size or 0)
    return {"stored": key}

import logging

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..db import get_db
from ..models import LabTemplate
from ..providers import known_kinds, provider_for_kind
from ..rbac import Principal
from ..storage import get_storage
from .deps import get_principal, require_capability

router = APIRouter(prefix="/labs", tags=["labs"])


@router.get("/templates", response_model=list[schemas.LabTemplateOut])
def list_templates(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
):
    return db.scalars(select(LabTemplate)).all()


@router.get("/vm-templates", response_model=list[schemas.VmTemplateOut])
def list_vm_templates(
    principal: Principal = Depends(require_capability("courses:write")),
):
    """The hypervisor's bootable VM templates, for the publisher's picker.

    Declared above ``/templates/{...}``-shaped routes for the same reason
    ``/instances/access`` is: FastAPI matches in declaration order.

    Publishing a VM lab means naming a ``vm_template``, which was a
    free-text box whose correct values lived only in a runbook — a typo
    surfaced minutes later as a provisioning failure on a student's screen.
    Gated on ``courses:write`` rather than ``infra:manage`` because the
    teacher publishing the lab is the one who needs it, and the names are
    not sensitive: the same caller may already reference them.

    Returns an empty list rather than an error when the adapter cannot
    answer, so the UI falls back to free text instead of blocking."""
    provider = provider_for_kind("vm")
    fetch = getattr(provider, "list_vm_templates", None)
    if not callable(fetch):
        return []
    try:
        return [schemas.VmTemplateOut(**row) for row in fetch()]
    except Exception as exc:
        logging.getLogger("palestrix.labs").warning(
            "could not list cluster VM templates: %s", exc
        )
        return []


@router.post("/templates", response_model=schemas.LabTemplateOut, status_code=201)
def publish_template(
    principal: Principal = Depends(require_capability("courses:write")),
    db: Session = Depends(get_db),
    slug: str = Form(pattern=r"^[a-z0-9-]+:[0-9.]+$"),
    title: str = Form(min_length=4),
    kind: str = Form(default="container"),
    access_mode: str = Form(default="no-gui", pattern="^(gui|no-gui)$"),
    ttl_minutes_default: int = Form(default=90, ge=15, le=480),
    ttl_minutes_max: int = Form(default=240, ge=15, le=480),
    cpu: int = Form(default=1, ge=1, le=16),
    ram_gb: int = Form(default=1, ge=1, le=64),
    vm_template: str | None = Form(default=None),
    archive: UploadFile | None = None,
):
    """Teacher advanced mode: publish a live environment. Container labs
    carry a Dockerfile/compose archive (stored now, built by the Phase 4
    workers); VM labs reference an admin-built Proxmox template. Additional
    kinds come from plugin-registered providers."""
    active_kinds = known_kinds()
    if kind not in active_kinds:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"unknown lab kind '{kind}'; active kinds: {sorted(active_kinds)}",
        )
    if db.scalar(select(LabTemplate).where(LabTemplate.slug == slug)):
        raise HTTPException(status.HTTP_409_CONFLICT, "slug already published")
    if kind == "container" and archive is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "container labs require a Dockerfile/compose archive",
        )
    if kind == "vm" and not vm_template:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "vm labs require a vm_template"
        )
    archive_key = None
    if archive is not None:
        storage = get_storage()
        archive_key = storage.put(
            "lab-archives",
            f"templates/{slug.replace(':', '_')}/{archive.filename}",
            archive.file,
            archive.size or 0,
        )
    template = LabTemplate(
        slug=slug,
        title=title,
        kind=kind,
        access_mode=access_mode,
        ttl_minutes_default=ttl_minutes_default,
        ttl_minutes_max=max(ttl_minutes_max, ttl_minutes_default),
        cpu=cpu,
        ram_gb=ram_gb,
        archive_key=archive_key,
        vm_template=vm_template,
        owner_id=principal.user_id,
    )
    db.add(template)
    db.commit()
    return template

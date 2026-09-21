from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import academy_gate, gamification, schemas
from ..db import SessionLocal, get_db
from ..events import dispatch_pending
from ..models import Module, ModuleCompletion, Path
from ..rbac import Principal
from .deps import get_principal, require_capability

router = APIRouter(prefix="/academy", tags=["academy"])


@router.get("/paths", response_model=list[schemas.PathOut])
def list_paths(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
):
    return db.scalars(select(Path)).all()


@router.get("/paths/{slug}/modules", response_model=list[schemas.ModuleOut])
def list_modules(
    slug: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    path = db.scalar(select(Path).where(Path.slug == slug))
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such path")
    modules = db.scalars(
        select(Module).where(Module.path_id == path.id).order_by(Module.position)
    ).all()
    done_ids = set(
        db.scalars(
            select(ModuleCompletion.module_id).where(
                ModuleCompletion.user_id == principal.user_id,
                ModuleCompletion.module_id.in_([m.id for m in modules]),
            )
        ).all()
    )
    out = []
    for module in modules:
        row = schemas.ModuleOut.model_validate(module)
        row.completed = module.id in done_ids
        row.has_body = bool(module.body.strip())
        # The list only needs to know whether a gate exists, not the caller's
        # standing against it; that costs a query per module and the reader
        # view answers it properly.
        row.gated = bool(module.lab_slug)
        out.append(row)
    return out


@router.get("/modules/{module_id}", response_model=schemas.ModuleDetailOut)
def read_module(
    module_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    """The lesson itself, plus where the caller stands on its lab.

    Readable by any authenticated principal: lesson bodies are course
    material, not per-user data, and the only caller-specific fields here are
    this caller's own completion and grade.
    """
    module = db.get(Module, module_id)
    if module is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such module")

    row = schemas.ModuleDetailOut.model_validate(module)
    row.has_body = bool(module.body.strip())
    row.gated = bool(module.lab_slug)
    row.completed = (
        db.scalar(
            select(ModuleCompletion).where(
                ModuleCompletion.module_id == module.id,
                ModuleCompletion.user_id == principal.user_id,
            )
        )
        is not None
    )

    gate = academy_gate.status_for(db, module, principal.user_id)
    if module.lab_slug:
        row.lab = schemas.ModuleLabOut(
            slug=module.lab_slug,
            title=gate.lab_title,
            available=gate.lab_available,
            scheme_published=gate.scheme_published,
            pass_percent=gate.pass_percent,
            best_percent=gate.best_percent,
            passed=gate.passed,
        )
    row.gated = gate.required
    if not row.completed:
        row.locked_reason = gate.reason
    return row


@router.post("/modules/{module_id}/complete", status_code=201)
def complete_module(
    module_id: str,
    background: BackgroundTasks,
    principal: Principal = Depends(require_capability("academy:complete")),
    db: Session = Depends(get_db),
):
    """Records completion, then asks the gamification service to award the
    module's Palestras. The service owns the earn rules (student-only, the
    daily cap, the streak checkpoint) and is the only writer to the ledger.

    Refuses with 403 ``lab_not_passed`` when the module names a lab whose
    grading scheme is published and the caller has not cleared it."""
    module = db.get(Module, module_id)
    if module is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such module")
    done = db.scalar(
        select(ModuleCompletion).where(
            ModuleCompletion.module_id == module_id,
            ModuleCompletion.user_id == principal.user_id,
        )
    )
    if done:
        raise HTTPException(status.HTTP_409_CONFLICT, "already completed")

    # A module bound to a lab with published grading is earned, not claimed.
    gate = academy_gate.status_for(db, module, principal.user_id)
    if gate.required and not gate.passed:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            {
                "error": "lab_not_passed",
                "lab": gate.lab_slug,
                "pass_percent": gate.pass_percent,
                "best_percent": gate.best_percent,
                "detail": gate.reason,
            },
        )

    db.add(ModuleCompletion(module_id=module_id, user_id=principal.user_id))
    result = gamification.award(
        db,
        user_id=principal.user_id,
        role=principal.role,
        amount=module.palestras_award,
        reason=gamification.EARN_MODULE,
        ref=module_id,
    )
    gamification.touch_streak(db, principal.user_id, principal.role)
    db.commit()
    background.add_task(dispatch_pending, SessionLocal())
    return {"completed": True, "palestras_awarded": result.posted}

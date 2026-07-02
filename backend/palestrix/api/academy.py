from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import gamification, schemas
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
    return db.scalars(
        select(Module).where(Module.path_id == path.id).order_by(Module.position)
    ).all()


@router.post("/modules/{module_id}/complete", status_code=201)
def complete_module(
    module_id: str,
    background: BackgroundTasks,
    principal: Principal = Depends(require_capability("academy:complete")),
    db: Session = Depends(get_db),
):
    """Records completion, then asks the gamification service to award the
    module's Palestras. The service owns the earn rules (student-only, the
    daily cap, the streak checkpoint) and is the only writer to the ledger."""
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

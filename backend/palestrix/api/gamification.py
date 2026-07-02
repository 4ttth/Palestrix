from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas
from ..db import get_db
from ..models import LedgerEntry
from ..rbac import Principal
from .deps import get_principal

router = APIRouter(prefix="/gamification", tags=["gamification"])


@router.get("/balance", response_model=schemas.BalanceOut)
def balance(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
):
    total = db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.delta), 0)).where(
            LedgerEntry.user_id == principal.user_id
        )
    )
    return schemas.BalanceOut(user_id=principal.user_id, palestras=total)


@router.get("/ledger", response_model=list[schemas.LedgerEntryOut])
def ledger(
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
    limit: int = 50,
):
    """Own ledger only. The ledger is append-only; corrections are new
    compensating entries (Phase 3 adds streaks, caps, and decay rules)."""
    return db.scalars(
        select(LedgerEntry)
        .where(LedgerEntry.user_id == principal.user_id)
        .order_by(LedgerEntry.created_at.desc())
        .limit(min(limit, 200))
    ).all()

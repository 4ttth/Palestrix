"""Gamification read surface: balances, the ledger, the streak, the profile
summary card, and the global leaderboards. Minting and burning happen in the
service (palestrix/gamification.py); this router only reports."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import gamification, schemas
from ..db import get_db
from ..models import LedgerEntry, Streak, User
from ..rbac import Principal
from .deps import get_principal

router = APIRouter(prefix="/gamification", tags=["gamification"])


@router.get("/balance", response_model=schemas.BalanceOut)
def balance(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
):
    return schemas.BalanceOut(
        user_id=principal.user_id,
        palestras=gamification.balance(db, principal.user_id),
    )


@router.get("/ledger", response_model=list[schemas.LedgerEntryOut])
def ledger(
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
    limit: int = 50,
):
    """Own ledger only. The ledger is append-only; corrections are new
    compensating entries, never edits (docs/rbac-matrix.md)."""
    return db.scalars(
        select(LedgerEntry)
        .where(LedgerEntry.user_id == principal.user_id)
        .order_by(LedgerEntry.created_at.desc())
        .limit(min(limit, 200))
    ).all()


@router.get("/summary", response_model=schemas.GamificationSummaryOut)
def summary(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
):
    """The caller's gamification profile card: balance, lifetime totals, streak,
    community score, first bloods, and global rank."""
    user = db.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account no longer exists")
    return gamification.summary(db, user)


@router.get("/streak", response_model=schemas.StreakOut)
def streak(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
):
    """The caller's current streak. Never 404s: an account with no activity yet
    reports a zeroed streak."""
    row = db.get(Streak, principal.user_id)
    if row is None:
        return schemas.StreakOut(
            current_days=0, longest_days=0, last_active_on=None, weeks_paid=0
        )
    return row


@router.get("/leaderboard", response_model=list[schemas.LeaderboardEntryOut])
def leaderboard(
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
    board: str = Query(default="palestras", pattern="^(palestras|community)$"),
    limit: int = 50,
):
    """Global, student-only ranking. ``board=palestras`` (default) ranks by
    lifetime earned Palestras; ``board=community`` ranks by community score.
    Staff never appear — they have no earn path (docs/rbac-matrix.md)."""
    limit = min(max(limit, 1), 200)
    if board == "community":
        return gamification.community_leaderboard(db, limit=limit)
    return gamification.palestras_leaderboard(db, limit=limit)

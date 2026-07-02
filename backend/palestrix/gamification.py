"""The gamification service: the one component allowed to mint or burn
Palestras, and the single home of the balance rules (docs/rbac-matrix.md).

Every other service posts a *request* here with a reason code; nothing else
writes to the ledger. Keeping earn caps, spend checks, streak accrual,
community score, and ranking in one module is what makes the ledger auditable
and the anti-abuse rules impossible to forget at a call site.

Invariants enforced here:
- Earning is student-only. Teachers and admins have no earn path, so
  leaderboards stay student-only (rbac-matrix.md).
- The ledger is append-only. A correction is a new compensating entry, never
  an edit; ``spend`` and ``award`` only ever ``db.add`` rows.
- Per-source daily caps bound how much any one source can pay a user per UTC
  day. Flag awards additionally scale down by prior solve count.
- ``palestras.changed`` fires on every non-zero ledger entry (public-api.md),
  emitted from here so no caller can post currency silently.

Callers commit the transaction and schedule ``events.dispatch_pending`` as a
background task, exactly as they already do for their own emitted events.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .events import emit
from .models import (
    FlagSubmission,
    LedgerEntry,
    Role,
    Streak,
    User,
    Writeup,
    Vote,
    as_utc,
)

# Reason codes: "<domain>.<event>". Earn deltas are positive, spends negative.
# Daily caps key on the reason string (see _DAILY_CAP_ATTR).
EARN_MODULE = "module.completed"
EARN_FLAG = "flag.captured"
EARN_FIRST_BLOOD = "first_blood.bonus"
EARN_WRITEUP = "writeup.published"
EARN_STREAK = "streak.weekly"
SPEND_EXTEND = "instance.extended"
SPEND_HINT = "hint.unlocked"
GRANT = "seed.grant"

# reason -> Settings attribute holding that source's daily cap. Sources absent
# here (first-blood bonuses, streak checkpoints, grants) are naturally rare and
# left uncapped.
_DAILY_CAP_ATTR = {
    EARN_MODULE: "palestras_daily_cap_module",
    EARN_FLAG: "palestras_daily_cap_flag",
    EARN_WRITEUP: "palestras_daily_cap_writeup",
}


class InsufficientPalestras(Exception):
    """Raised by ``spend`` when the balance cannot cover the cost. Carries the
    numbers the API needs for its 409 body."""

    def __init__(self, cost: int, balance: int):
        self.cost = cost
        self.balance = balance
        super().__init__(f"need {cost}, have {balance}")


@dataclass
class AwardResult:
    posted: int  # Palestras actually credited (0 if capped out or not a student)
    capped: bool  # True when the daily cap trimmed the requested amount


# --------------------------------------------------------------------------
# Balances
# --------------------------------------------------------------------------


def balance(db: Session, user_id: str) -> int:
    """Current spendable balance: the sum of every ledger delta."""
    return (
        db.scalar(
            select(func.coalesce(func.sum(LedgerEntry.delta), 0)).where(
                LedgerEntry.user_id == user_id
            )
        )
        or 0
    )


def lifetime_earned(db: Session, user_id: str) -> int:
    """Everything ever earned (positive deltas only). Spending never lowers
    this, so it is the stable basis for ranking."""
    return (
        db.scalar(
            select(func.coalesce(func.sum(LedgerEntry.delta), 0)).where(
                LedgerEntry.user_id == user_id, LedgerEntry.delta > 0
            )
        )
        or 0
    )


def _earned_today(db: Session, user_id: str, reason: str) -> int:
    """Palestras earned from one source since 00:00 UTC today. Summed in Python
    against ``as_utc`` so the cap is correct on SQLite (naive UTC) and Postgres
    (aware) alike."""
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    rows = db.scalars(
        select(LedgerEntry).where(
            LedgerEntry.user_id == user_id,
            LedgerEntry.reason == reason,
            LedgerEntry.delta > 0,
        )
    ).all()
    return sum(r.delta for r in rows if as_utc(r.created_at) >= midnight)


# --------------------------------------------------------------------------
# Mint / burn
# --------------------------------------------------------------------------


def award(
    db: Session,
    *,
    user_id: str,
    role: Role,
    amount: int,
    reason: str,
    ref: str | None = None,
    emit_event: bool = True,
) -> AwardResult:
    """Credit Palestras, honoring the student-only earn path and the source's
    daily cap. Returns how much was actually posted (may be less than
    ``amount``, or 0). Flushes so the balance and any emitted event are
    consistent; the caller owns the commit."""
    if role is not Role.student or amount <= 0:
        return AwardResult(0, False)

    grant = amount
    capped = False
    cap_attr = _DAILY_CAP_ATTR.get(reason)
    if cap_attr:
        cap = getattr(get_settings(), cap_attr)
        if cap and cap > 0:
            remaining = max(0, cap - _earned_today(db, user_id, reason))
            if grant > remaining:
                grant, capped = remaining, True

    if grant <= 0:
        return AwardResult(0, capped)

    db.add(LedgerEntry(user_id=user_id, delta=grant, reason=reason, ref=ref))
    db.flush()
    if emit_event:
        _emit_changed(db, user_id, grant, reason)
    return AwardResult(grant, capped)


def spend(
    db: Session,
    *,
    user_id: str,
    amount: int,
    reason: str,
    ref: str | None = None,
    emit_event: bool = True,
) -> None:
    """Burn Palestras. Raises ``InsufficientPalestras`` if the balance cannot
    cover ``amount`` — the spend is refused, never allowed to go negative."""
    if amount <= 0:
        return
    have = balance(db, user_id)
    if have < amount:
        raise InsufficientPalestras(amount, have)
    db.add(LedgerEntry(user_id=user_id, delta=-amount, reason=reason, ref=ref))
    db.flush()
    if emit_event:
        _emit_changed(db, user_id, -amount, reason)


def _emit_changed(db: Session, user_id: str, delta: int, reason: str) -> None:
    user = db.get(User, user_id)
    emit(
        db,
        "palestras.changed",
        {
            "user": user.handle if user else user_id,
            "delta": delta,
            "reason": reason,
            "balance": balance(db, user_id),
        },
    )


# --------------------------------------------------------------------------
# Flag-capture dynamic scoring
# --------------------------------------------------------------------------


def flag_award(base: int, solves_before: int) -> int:
    """Palestras for a flag capture, scaled down by how many have already
    solved it: the first solver earns the full base, each prior solve shaves
    ``flag_scale_step`` off, never below ``flag_scale_floor`` of the base."""
    if base <= 0:
        return 0
    s = get_settings()
    factor = max(s.flag_scale_floor, 1.0 - solves_before * s.flag_scale_step)
    return round(base * factor)


# --------------------------------------------------------------------------
# Streaks
# --------------------------------------------------------------------------


def touch_streak(
    db: Session, user_id: str, role: Role, when: datetime | None = None
) -> Streak | None:
    """Record one day of qualifying activity and pay the weekly checkpoint when
    a new 7-day multiple is reached. Consecutive days extend the streak; a gap
    of more than a day resets it (and the paid-week counter). Same-day repeats
    are no-ops, so streaks and checkpoints can't be farmed by acting twice.
    Students only — staff have no earn path."""
    if role is not Role.student:
        return None
    today: date = (when or datetime.now(timezone.utc)).date()

    streak = db.get(Streak, user_id)
    if streak is None:
        streak = Streak(user_id=user_id, current_days=0, longest_days=0, weeks_paid=0)
        db.add(streak)

    last = streak.last_active_on
    if last is not None and today <= last:
        return streak  # already counted today (or a backfilled earlier day)

    if last is not None and today == last + timedelta(days=1):
        streak.current_days += 1
    else:
        streak.current_days = 1
        streak.weeks_paid = 0
    streak.last_active_on = today
    streak.longest_days = max(streak.longest_days, streak.current_days)

    due_weeks = streak.current_days // 7
    if due_weeks > streak.weeks_paid:
        bonus = (due_weeks - streak.weeks_paid) * get_settings().streak_weekly_bonus_palestras
        streak.weeks_paid = due_weeks
        award(
            db,
            user_id=user_id,
            role=role,
            amount=bonus,
            reason=EARN_STREAK,
            ref=f"week-{due_weeks}",
        )
    db.flush()
    return streak


# --------------------------------------------------------------------------
# Community score (recency-decayed contribution)
# --------------------------------------------------------------------------


def community_score(db: Session, user_id: str) -> int:
    """A user's community standing: each published writeup is worth a base plus
    its net votes, faded by a half-life so old contributions stop propping up a
    rank (rbac-matrix.md)."""
    s = get_settings()
    now = datetime.now(timezone.utc)
    rows = db.execute(
        select(Writeup.created_at, func.coalesce(func.sum(Vote.value), 0))
        .outerjoin(Vote, Vote.writeup_id == Writeup.id)
        .where(Writeup.author_id == user_id, Writeup.published.is_(True))
        .group_by(Writeup.id)
    ).all()
    total = 0.0
    for created_at, net_votes in rows:
        age_days = max(0.0, (now - as_utc(created_at)).total_seconds() / 86400)
        decay = (
            0.5 ** (age_days / s.community_score_halflife_days)
            if s.community_score_halflife_days > 0
            else 1.0
        )
        total += (s.community_writeup_base_points + max(0, int(net_votes))) * decay
    return round(total)


# --------------------------------------------------------------------------
# Ranking
# --------------------------------------------------------------------------


def palestras_leaderboard(db: Session, limit: int = 50) -> list[dict]:
    """Global student ranking by lifetime earned Palestras. ``delta`` is the
    last 7 days' earnings (recent momentum, mirrors the dashboard board).
    Staff never appear — they have no earn path."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    students = {u.id: u for u in db.scalars(select(User).where(User.role == Role.student)).all()}
    if not students:
        return []
    ids = list(students)

    entries = db.scalars(
        select(LedgerEntry).where(
            LedgerEntry.user_id.in_(ids), LedgerEntry.delta > 0
        )
    ).all()
    lifetime: dict[str, int] = {}
    weekly: dict[str, int] = {}
    for e in entries:
        lifetime[e.user_id] = lifetime.get(e.user_id, 0) + e.delta
        if as_utc(e.created_at) >= week_ago:
            weekly[e.user_id] = weekly.get(e.user_id, 0) + e.delta

    fb = dict(
        db.execute(
            select(FlagSubmission.user_id, func.count())
            .where(
                FlagSubmission.first_blood.is_(True),
                FlagSubmission.user_id.in_(ids),
            )
            .group_by(FlagSubmission.user_id)
        ).all()
    )
    streaks = {
        s.user_id: s.current_days
        for s in db.scalars(select(Streak).where(Streak.user_id.in_(ids))).all()
    }

    rows = [
        {
            "handle": students[uid].handle,
            "score": score,
            "delta": weekly.get(uid, 0),
            "first_bloods": int(fb.get(uid, 0)),
            "streak_days": streaks.get(uid, 0),
        }
        for uid, score in lifetime.items()
        if score > 0
    ]
    rows.sort(key=lambda r: (-r["score"], -r["first_bloods"], r["handle"]))
    for i, row in enumerate(rows[:limit]):
        row["rank"] = i + 1
    return rows[:limit]


def community_leaderboard(db: Session, limit: int = 50) -> list[dict]:
    """Global student ranking by community score."""
    students = db.scalars(select(User).where(User.role == Role.student)).all()
    rows = []
    for u in students:
        score = community_score(db, u.id)
        if score > 0:
            rows.append(
                {
                    "handle": u.handle,
                    "score": score,
                    "delta": 0,
                    "first_bloods": 0,
                    "streak_days": 0,
                }
            )
    rows.sort(key=lambda r: (-r["score"], r["handle"]))
    for i, row in enumerate(rows[:limit]):
        row["rank"] = i + 1
    return rows[:limit]


def rank_of(db: Session, user: User) -> int | None:
    """A student's position on the Palestras leaderboard, or None for staff and
    students who have not earned anything yet."""
    if user.role is not Role.student:
        return None
    for row in palestras_leaderboard(db, limit=1_000_000):
        if row["handle"] == user.handle:
            return row["rank"]
    return None


def summary(db: Session, user: User) -> dict:
    """The gamification profile card for one account: balance, lifetime totals,
    streak, community score, first bloods, and global rank."""
    bal = balance(db, user.id)
    earned = lifetime_earned(db, user.id)
    streak = db.get(Streak, user.id)
    first_bloods = (
        db.scalar(
            select(func.count())
            .select_from(FlagSubmission)
            .where(
                FlagSubmission.user_id == user.id,
                FlagSubmission.first_blood.is_(True),
            )
        )
        or 0
    )
    return {
        "user_id": user.id,
        "handle": user.handle,
        "palestras": bal,
        "lifetime_earned": earned,
        "spent": earned - bal,
        "streak_days": streak.current_days if streak else 0,
        "longest_streak": streak.longest_days if streak else 0,
        "community_score": community_score(db, user.id),
        "first_bloods": int(first_bloods),
        "rank": rank_of(db, user),
    }

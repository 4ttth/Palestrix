import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from .. import gamification, schemas
from ..config import get_settings
from ..db import SessionLocal, get_db, serialize_on
from ..events import dispatch_pending, emit
from ..models import Challenge, CtfEvent, FlagSubmission, Role, Tenant, User, as_utc
from ..rbac import Principal
from ..security import sha256_hex
from .deps import get_principal, require_capability

router = APIRouter(prefix="/compete", tags=["compete"])


def _visible_events(principal: Principal):
    """Which events a caller may see and play.

    An event carries a tenant when it belongs to one class section; those
    are that section's, and nobody else's. A tenant-less event is the
    site-wide arena and is open to everyone. Staff who can author or adjust
    see all of them, because running the arena is their job.
    """
    if principal.can("compete:author") or principal.can("compete:adjust"):
        return None  # no filter
    clauses = [CtfEvent.tenant_id.is_(None)]
    if principal.tenant_id is not None:
        clauses.append(CtfEvent.tenant_id == principal.tenant_id)
    return or_(*clauses)


def _event_or_403(db: Session, principal: Principal, event_id: str) -> CtfEvent:
    event = db.get(CtfEvent, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such event")
    visible = _visible_events(principal)
    if visible is not None and not (
        event.tenant_id is None or event.tenant_id == principal.tenant_id
    ):
        # 404, not 403: whether another section is running an event is not
        # this caller's business either.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such event")
    return event


@router.post("/events", response_model=schemas.CtfEventOut, status_code=201)
def create_event(
    body: schemas.CtfEventIn,
    principal: Principal = Depends(require_capability("compete:author")),
    db: Session = Depends(get_db),
):
    # Same rule as a course: a teacher runs their own section's arena, a
    # superadmin runs any of them or the site-wide one.
    fields = body.model_dump()
    requested_tenant = fields.pop("tenant_id", None)
    if principal.role is Role.superadmin:
        tenant_id = requested_tenant
    else:
        tenant_id = principal.tenant_id
        if requested_tenant is not None and requested_tenant != tenant_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "an event belongs to your own tenant"
            )
    if tenant_id is not None and db.get(Tenant, tenant_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "no such tenant")
    if body.ends_at <= body.starts_at:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "the event ends before it starts"
        )
    event = CtfEvent(**fields, tenant_id=tenant_id, created_by=principal.user_id)
    db.add(event)
    db.commit()
    return event


@router.get("/events", response_model=list[schemas.CtfEventOut])
def list_events(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
):
    query = select(CtfEvent).order_by(CtfEvent.starts_at.desc())
    visible = _visible_events(principal)
    if visible is not None:
        query = query.where(visible)
    return db.scalars(query).all()


@router.post(
    "/events/{event_id}/challenges",
    response_model=schemas.ChallengeOut,
    status_code=201,
)
def create_challenge(
    event_id: str,
    body: schemas.ChallengeIn,
    principal: Principal = Depends(require_capability("compete:author")),
    db: Session = Depends(get_db),
):
    _event_or_403(db, principal, event_id)
    challenge = Challenge(
        event_id=event_id,
        title=body.title,
        category=body.category,
        points=body.points,
        flag_hash=sha256_hex(body.flag.strip()),
        palestras_award=body.palestras_award,
        created_by=principal.user_id,
    )
    db.add(challenge)
    db.commit()
    return schemas.ChallengeOut.model_validate(challenge)


def _challenge_out(
    db: Session, ch: Challenge, principal: Principal
) -> schemas.ChallengeOut:
    solves = db.scalar(
        select(func.count(FlagSubmission.id)).where(
            FlagSubmission.challenge_id == ch.id, FlagSubmission.correct.is_(True)
        )
    )
    fb_row = db.scalar(
        select(FlagSubmission)
        .where(FlagSubmission.challenge_id == ch.id, FlagSubmission.first_blood.is_(True))
    )
    handle = None
    if fb_row:
        user = db.get(User, fb_row.user_id)
        handle = user.handle if user else None
    solved = db.scalar(
        select(FlagSubmission.id).where(
            FlagSubmission.challenge_id == ch.id,
            FlagSubmission.user_id == principal.user_id,
            FlagSubmission.correct.is_(True),
        )
    )
    out = schemas.ChallengeOut.model_validate(ch)
    out.solves = solves
    out.first_blood = handle
    out.first_blood_at = as_utc(fb_row.submitted_at) if fb_row else None
    out.solved = solved is not None
    return out


@router.get("/events/{event_id}/challenges", response_model=list[schemas.ChallengeOut])
def list_challenges(
    event_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    _event_or_403(db, principal, event_id)
    rows = db.scalars(select(Challenge).where(Challenge.event_id == event_id)).all()
    return [_challenge_out(db, ch, principal) for ch in rows]


@router.post("/challenges/{challenge_id}/submit", response_model=schemas.FlagResultOut)
def submit_flag(
    challenge_id: str,
    body: schemas.FlagSubmitIn,
    background: BackgroundTasks,
    principal: Principal = Depends(require_capability("compete:submit")),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    challenge = db.get(Challenge, challenge_id)
    if challenge is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such challenge")

    event = _event_or_403(db, principal, challenge.event_id)
    now = datetime.now(timezone.utc)
    if event and not (as_utc(event.starts_at) <= now <= as_utc(event.ends_at)):
        raise HTTPException(status.HTTP_409_CONFLICT, "event is not running")

    # Everything from "has this user solved it already" through the ledger
    # credit is one critical section, serialized per (challenge, user).
    # Interleaved there, two requests both read "not solved yet", both
    # award, and one capture pays twice — and both can come back first
    # blood. It costs nothing except to a double-submit.
    with serialize_on(db, "compete.submit", challenge_id, principal.user_id):
        already = db.scalar(
            select(FlagSubmission).where(
                FlagSubmission.challenge_id == challenge_id,
                FlagSubmission.user_id == principal.user_id,
                FlagSubmission.correct.is_(True),
            )
        )
        if already:
            raise HTTPException(status.HTTP_409_CONFLICT, "already solved")

        last = db.scalar(
            select(FlagSubmission)
            .where(
                FlagSubmission.challenge_id == challenge_id,
                FlagSubmission.user_id == principal.user_id,
            )
            .order_by(FlagSubmission.submitted_at.desc())
        )
        if last and not last.correct:
            elapsed = (now - as_utc(last.submitted_at)).total_seconds()
            if elapsed < settings.flag_cooldown_seconds:
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "cooldown",
                        "retry_after": int(settings.flag_cooldown_seconds - elapsed),
                    },
                )

        correct = secrets.compare_digest(
            sha256_hex(body.flag.strip()), challenge.flag_hash
        )
        first_blood = False
        solves_before = 0
        if correct:
            solves_before = db.scalar(
                select(func.count(FlagSubmission.id)).where(
                    FlagSubmission.challenge_id == challenge_id,
                    FlagSubmission.correct.is_(True),
                )
            )
            first_blood = solves_before == 0

        submission = FlagSubmission(
            challenge_id=challenge_id,
            user_id=principal.user_id,
            correct=correct,
            first_blood=first_blood,
            submitted_at=now,
        )
        db.add(submission)

        palestras = 0
        if correct:
            # No earning from a challenge you authored (rbac-matrix.md). Authors are
            # staff and cannot submit, but the guard keeps the rule where it reads.
            self_authored = challenge.created_by == principal.user_id
            base = 0 if self_authored else gamification.flag_award(
                challenge.palestras_award, solves_before
            )
            earned = gamification.award(
                db,
                user_id=principal.user_id,
                role=principal.role,
                amount=base,
                reason=gamification.EARN_FLAG,
                ref=challenge_id,
            )
            palestras = earned.posted
            if first_blood and not self_authored:
                bonus = gamification.award(
                    db,
                    user_id=principal.user_id,
                    role=principal.role,
                    amount=settings.first_blood_bonus_palestras,
                    reason=gamification.EARN_FIRST_BLOOD,
                    ref=challenge_id,
                )
                palestras += bonus.posted
            gamification.touch_streak(db, principal.user_id, principal.role)
            user = db.get(User, principal.user_id)
            emit(
                db,
                "flag.captured",
                {
                    "challenge_id": challenge_id,
                    "challenge": challenge.title,
                    "by": user.handle if user else principal.user_id,
                    "first_blood": first_blood,
                    "points": challenge.points,
                },
            )
        db.commit()
    background.add_task(dispatch_pending, SessionLocal())
    return schemas.FlagResultOut(
        correct=correct,
        first_blood=first_blood,
        points=challenge.points if correct else 0,
        palestras=palestras,
    )


@router.get(
    "/events/{event_id}/leaderboard", response_model=list[schemas.LeaderboardRowOut]
)
def leaderboard(
    event_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    _event_or_403(db, principal, event_id)
    rows = db.execute(
        select(
            User.handle,
            func.coalesce(func.sum(Challenge.points), 0).label("score"),
            func.sum(
                case((FlagSubmission.first_blood.is_(True), 1), else_=0)
            ).label("first_bloods"),
        )
        .join(FlagSubmission, FlagSubmission.user_id == User.id)
        .join(Challenge, Challenge.id == FlagSubmission.challenge_id)
        .where(Challenge.event_id == event_id, FlagSubmission.correct.is_(True))
        .group_by(User.handle)
        .order_by(func.sum(Challenge.points).desc())
    ).all()
    return [
        schemas.LeaderboardRowOut(
            rank=i + 1,
            handle=row.handle,
            score=int(row.score or 0),
            first_bloods=int(row.first_bloods or 0),
        )
        for i, row in enumerate(rows)
    ]

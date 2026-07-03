"""The grade-passback queue (docs/integrations-canvas-lms.md §Grade passback).

``queue_grade_passbacks`` runs inside the grading request, right after the
``grade.posted`` event: for every platform link on the course whose student
is identity-mapped and whose assignment has a bound AGS line item (the first
launch of the content link binds it), a queue row is written. Delivery is
asynchronous and at-least-once: ``dispatch_due_passbacks`` makes one attempt
per due row — immediately as a background task after grading, and on every
reaper heartbeat after that — backing off exponentially until
``grade_passback_max_attempts``, then parking the row as ``failed`` where
the teacher's course view surfaces it for a manual retry. Receipts are kept;
grades already passed back are never retracted automatically.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..events import emit
from ..models import (
    Assignment,
    Course,
    ExternalCourseLink,
    ExternalIdentity,
    GradePassback,
    LtiResourceLink,
    Submission,
)
from . import get_platform

logger = logging.getLogger("palestrix.integrations.passback")


def queue_grade_passbacks(
    db: Session, course: Course, assignment: Assignment, submission: Submission
) -> list[GradePassback]:
    """Queue the score for every platform this grade can reach. A regrade
    while the previous row is still pending updates it in place (one score in
    flight per submission per link); after a delivery, a new row is queued —
    the platform keeps its own score history."""
    rows: list[GradePassback] = []
    links = db.scalars(
        select(ExternalCourseLink).where(ExternalCourseLink.course_id == course.id)
    ).all()
    for link in links:
        platform = get_platform(link.platform)
        if platform is None:
            continue  # adapter not configured; nothing to queue against
        resource_link = db.scalar(
            select(LtiResourceLink).where(
                LtiResourceLink.assignment_id == assignment.id,
                LtiResourceLink.link_id == link.id,
                LtiResourceLink.lineitem_url != "",
            )
        )
        if resource_link is None:
            continue  # no launch has bound a grade column for this assignment yet
        identity = db.scalar(
            select(ExternalIdentity).where(
                ExternalIdentity.user_id == submission.user_id,
                ExternalIdentity.platform == link.platform,
                ExternalIdentity.issuer == platform.issuer,
            )
        )
        if identity is None:
            continue  # student never mapped; the roster sync creates the mapping
        pending = db.scalar(
            select(GradePassback).where(
                GradePassback.submission_id == submission.id,
                GradePassback.link_id == link.id,
                GradePassback.status == "pending",
            )
        )
        if pending is not None:
            pending.score_given = submission.grade or 0
            pending.lineitem_url = resource_link.lineitem_url
            pending.next_attempt_at = datetime.now(timezone.utc)
            rows.append(pending)
            continue
        row = GradePassback(
            platform=link.platform,
            link_id=link.id,
            assignment_id=assignment.id,
            submission_id=submission.id,
            user_id=submission.user_id,
            lineitem_url=resource_link.lineitem_url,
            external_user_id=identity.subject,
            score_given=submission.grade or 0,
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def dispatch_due_passbacks(db: Session, *, now: datetime | None = None) -> list[str]:
    """One delivery attempt for every pending row that is due. Commits its
    own work (mirroring events.dispatch_pending) so it can run as a FastAPI
    background task, from the reaper heartbeat, or directly in tests.
    Returns the ids delivered on this pass."""
    now = now or datetime.now(timezone.utc)
    settings = get_settings()
    due = db.scalars(
        select(GradePassback).where(
            GradePassback.status == "pending", GradePassback.next_attempt_at <= now
        )
    ).all()
    delivered: list[str] = []
    for row in due:
        platform = get_platform(row.platform)
        if platform is None:
            continue  # leave queued: the adapter may be configured later
        row.attempts += 1
        try:
            row.receipt = platform.push_grade(row)
        except Exception as exc:
            row.error = str(exc)
            if row.attempts >= settings.grade_passback_max_attempts:
                row.status = "failed"
                logger.warning(
                    "grade passback %s failed permanently after %s attempts: %s",
                    row.id, row.attempts, exc,
                )
            else:
                row.next_attempt_at = now + timedelta(minutes=2**row.attempts)
            continue
        row.status = "delivered"
        row.delivered_at = now
        row.error = None
        emit(
            db,
            "grade.delivered",
            {
                "passback_id": row.id,
                "platform": row.platform,
                "assignment_id": row.assignment_id,
                "submission_id": row.submission_id,
                "score": row.score_given,
                "receipt": row.receipt,
            },
        )
        delivered.append(row.id)
    db.commit()
    return delivered

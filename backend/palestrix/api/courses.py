from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas
from ..db import SessionLocal, get_db
from ..events import dispatch_pending, emit
from ..models import Assignment, Course, Enrollment, Role, Submission, Tenant, User
from ..rbac import Principal
from ..storage import get_storage, safe_filename
from .deps import get_principal, require_capability

router = APIRouter(prefix="/courses", tags=["courses"])


def _course_or_404(db: Session, course_id: str) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such course")
    return course


def _require_course_teacher(principal: Principal, course: Course) -> None:
    if principal.role is Role.superadmin:
        return
    if course.teacher_id != principal.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your course")


def _course_out(db: Session, course: Course) -> schemas.CourseOut:
    out = schemas.CourseOut.model_validate(course)
    out.students = db.scalar(
        select(func.count(Enrollment.id)).where(Enrollment.course_id == course.id)
    )
    out.assignments = db.scalar(
        select(func.count(Assignment.id)).where(Assignment.course_id == course.id)
    )
    return out


def _assignment_out(db: Session, assignment: Assignment) -> schemas.AssignmentOut:
    out = schemas.AssignmentOut.model_validate(assignment)
    out.submissions = db.scalar(
        select(func.count(Submission.id)).where(
            Submission.assignment_id == assignment.id
        )
    )
    out.graded = db.scalar(
        select(func.count(Submission.id)).where(
            Submission.assignment_id == assignment.id, Submission.grade.is_not(None)
        )
    )
    return out


@router.post("", response_model=schemas.CourseOut, status_code=201)
def create_course(
    body: schemas.CourseIn,
    principal: Principal = Depends(require_capability("courses:write")),
    db: Session = Depends(get_db),
):
    # A teacher's course belongs to their own tenant. Taking tenant_id
    # straight off the body let a teacher file a course into another class
    # section (or name a tenant that does not exist, which surfaces as a
    # foreign-key 500). Superadmins place courses anywhere, deliberately.
    fields = body.model_dump()
    requested_tenant = fields.pop("tenant_id", None)
    if principal.role is Role.superadmin:
        tenant_id = requested_tenant
    else:
        tenant_id = principal.tenant_id
        if requested_tenant is not None and requested_tenant != tenant_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "a course belongs to your own tenant",
            )
    if tenant_id is not None and db.get(Tenant, tenant_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "no such tenant")
    course = Course(**fields, tenant_id=tenant_id, teacher_id=principal.user_id)
    db.add(course)
    db.commit()
    return _course_out(db, course)


@router.get("", response_model=list[schemas.CourseOut])
def list_courses(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
):
    if principal.role in (Role.admin, Role.superadmin):
        rows = db.scalars(select(Course)).all()
    elif principal.role is Role.teacher:
        rows = db.scalars(
            select(Course).where(Course.teacher_id == principal.user_id)
        ).all()
    else:
        rows = db.scalars(
            select(Course)
            .join(Enrollment, Enrollment.course_id == Course.id)
            .where(Enrollment.user_id == principal.user_id)
        ).all()
    return [_course_out(db, c) for c in rows]


@router.get("/{course_id}/roster", response_model=list[schemas.RosterRowOut])
def roster(
    course_id: str,
    principal: Principal = Depends(require_capability("courses:write")),
    db: Session = Depends(get_db),
):
    """The teacher's enrollment list for one course."""
    course = _course_or_404(db, course_id)
    _require_course_teacher(principal, course)
    rows = db.execute(
        select(Enrollment, User)
        .join(User, User.id == Enrollment.user_id)
        .where(Enrollment.course_id == course_id)
        .order_by(Enrollment.created_at)
    ).all()
    return [
        schemas.RosterRowOut(
            user_id=user.id,
            handle=user.handle,
            name=user.name,
            email=user.email,
            enrolled_at=enrollment.created_at,
        )
        for enrollment, user in rows
    ]


@router.post("/{course_id}/enrollments", status_code=201)
def enroll_student(
    course_id: str,
    body: schemas.EnrollIn,
    principal: Principal = Depends(require_capability("courses:write")),
    db: Session = Depends(get_db),
):
    """Teacher-driven enrollment by handle (students can also self-enroll
    through POST /{course_id}/enroll)."""
    course = _course_or_404(db, course_id)
    _require_course_teacher(principal, course)
    student = db.scalar(select(User).where(User.handle == body.handle))
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such user")
    if student.role is not Role.student:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "only students can be enrolled"
        )
    exists = db.scalar(
        select(Enrollment).where(
            Enrollment.course_id == course_id, Enrollment.user_id == student.id
        )
    )
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "already enrolled")
    db.add(Enrollment(course_id=course_id, user_id=student.id))
    db.commit()
    return {"enrolled": True, "user_id": student.id}


@router.delete("/{course_id}/enrollments/{user_id}", status_code=204)
def unenroll_student(
    course_id: str,
    user_id: str,
    principal: Principal = Depends(require_capability("courses:write")),
    db: Session = Depends(get_db),
):
    course = _course_or_404(db, course_id)
    _require_course_teacher(principal, course)
    enrollment = db.scalar(
        select(Enrollment).where(
            Enrollment.course_id == course_id, Enrollment.user_id == user_id
        )
    )
    if enrollment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not enrolled")
    db.delete(enrollment)
    db.commit()


@router.post("/{course_id}/enroll", status_code=201)
def enroll(
    course_id: str,
    principal: Principal = Depends(require_capability("courses:enroll")),
    db: Session = Depends(get_db),
):
    _course_or_404(db, course_id)
    exists = db.scalar(
        select(Enrollment).where(
            Enrollment.course_id == course_id, Enrollment.user_id == principal.user_id
        )
    )
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "already enrolled")
    db.add(Enrollment(course_id=course_id, user_id=principal.user_id))
    db.commit()
    return {"enrolled": True}


@router.post(
    "/{course_id}/assignments", response_model=schemas.AssignmentOut, status_code=201
)
def create_assignment(
    course_id: str,
    body: schemas.AssignmentIn,
    principal: Principal = Depends(require_capability("courses:write")),
    db: Session = Depends(get_db),
):
    course = _course_or_404(db, course_id)
    _require_course_teacher(principal, course)
    assignment = Assignment(course_id=course_id, **body.model_dump())
    db.add(assignment)
    db.commit()
    return _assignment_out(db, assignment)


@router.get("/{course_id}/assignments", response_model=list[schemas.AssignmentOut])
def list_assignments(
    course_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    course = _course_or_404(db, course_id)
    if principal.role is Role.student:
        enrolled = db.scalar(
            select(Enrollment).where(
                Enrollment.course_id == course_id,
                Enrollment.user_id == principal.user_id,
            )
        )
        if not enrolled:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "not enrolled")
    elif principal.role is Role.teacher:
        _require_course_teacher(principal, course)
    rows = db.scalars(
        select(Assignment).where(Assignment.course_id == course_id)
    ).all()
    return [_assignment_out(db, a) for a in rows]


@router.post(
    "/{course_id}/assignments/{assignment_id}/attachment",
    response_model=schemas.AssignmentOut,
)
def upload_assignment_file(
    course_id: str,
    assignment_id: str,
    file: UploadFile,
    principal: Principal = Depends(require_capability("courses:write")),
    db: Session = Depends(get_db),
):
    """Basic teacher upload mode: a file asset stored in object storage.
    Live-environment publishing is /labs/templates."""
    course = _course_or_404(db, course_id)
    _require_course_teacher(principal, course)
    assignment = db.get(Assignment, assignment_id)
    if assignment is None or assignment.course_id != course_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such assignment")
    # The client's filename becomes part of the object key, so it is reduced
    # to a single safe segment first — otherwise "../../.." walks out of the
    # bucket on the local backend and out of the prefix on S3.
    key = f"{course_id}/{assignment_id}/{safe_filename(file.filename)}"
    storage = get_storage()
    assignment.storage_key = storage.put(
        "lab-archives", key, file.file, file.size or 0
    )
    db.commit()
    return _assignment_out(db, assignment)


@router.get(
    "/{course_id}/assignments/{assignment_id}/submissions",
    response_model=list[schemas.GradebookRowOut],
)
def gradebook(
    course_id: str,
    assignment_id: str,
    principal: Principal = Depends(require_capability("courses:grade")),
    db: Session = Depends(get_db),
):
    """The teacher's per-assignment gradebook: every submission with its
    grade and, for auto-graded labs, the checker's objective-by-objective
    breakdown behind that grade."""
    from ..models import GradeCheck

    course = _course_or_404(db, course_id)
    _require_course_teacher(principal, course)
    assignment = db.get(Assignment, assignment_id)
    if assignment is None or assignment.course_id != course_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such assignment")
    rows = db.execute(
        select(Submission, User)
        .join(User, User.id == Submission.user_id)
        .where(Submission.assignment_id == assignment_id)
        .order_by(Submission.submitted_at)
    ).all()
    out = []
    for submission, student in rows:
        auto = db.scalar(
            select(GradeCheck)
            .where(GradeCheck.submission_id == submission.id)
            .order_by(GradeCheck.created_at.desc(), GradeCheck.id.desc())
        )
        out.append(
            schemas.GradebookRowOut(
                submission_id=submission.id,
                user_id=student.id,
                handle=student.handle,
                name=student.name,
                grade=submission.grade,
                submitted_at=submission.submitted_at,
                auto=schemas.GradeCheckOut.model_validate(auto) if auto else None,
            )
        )
    return out


@router.post(
    "/{course_id}/assignments/{assignment_id}/submissions",
    response_model=schemas.SubmissionOut,
    status_code=201,
)
def submit(
    course_id: str,
    assignment_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
    text: str | None = None,
):
    if principal.role is not Role.student:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "students submit assignments")
    enrolled = db.scalar(
        select(Enrollment).where(
            Enrollment.course_id == course_id, Enrollment.user_id == principal.user_id
        )
    )
    if not enrolled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not enrolled")
    assignment = db.get(Assignment, assignment_id)
    if assignment is None or assignment.course_id != course_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such assignment")
    existing = db.scalar(
        select(Submission).where(
            Submission.assignment_id == assignment_id,
            Submission.user_id == principal.user_id,
        )
    )
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "already submitted")
    submission = Submission(
        assignment_id=assignment_id, user_id=principal.user_id, text=text
    )
    db.add(submission)
    db.commit()
    return submission


@router.post(
    "/{course_id}/assignments/{assignment_id}/submissions/{submission_id}/grade",
    response_model=schemas.SubmissionOut,
)
def grade(
    course_id: str,
    assignment_id: str,
    submission_id: str,
    body: schemas.GradeIn,
    background: BackgroundTasks,
    principal: Principal = Depends(require_capability("courses:grade")),
    db: Session = Depends(get_db),
):
    course = _course_or_404(db, course_id)
    _require_course_teacher(principal, course)
    submission = db.get(Submission, submission_id)
    if submission is None or submission.assignment_id != assignment_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such submission")
    submission.grade = body.grade
    submission.graded_by = principal.user_id
    student = db.get(User, submission.user_id)
    emit(
        db,
        "grade.posted",
        {
            "submission_id": submission.id,
            "assignment_id": assignment_id,
            "course_id": course_id,
            "student": student.handle if student else submission.user_id,
            "grade": body.grade,
        },
    )
    # Phase 8: grade.posted triggers external passback — the score queues for
    # every linked platform that can receive it (mapped student, bound line
    # item) and is delivered right after this request commits.
    from ..integrations.passback import dispatch_due_passbacks, queue_grade_passbacks

    assignment = db.get(Assignment, assignment_id)
    queued = queue_grade_passbacks(db, course, assignment, submission)
    db.commit()
    background.add_task(dispatch_pending, SessionLocal())
    if queued:
        background.add_task(dispatch_due_passbacks, SessionLocal())
    return submission

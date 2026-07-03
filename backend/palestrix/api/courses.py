from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas
from ..db import SessionLocal, get_db
from ..events import dispatch_pending, emit
from ..models import Assignment, Course, Enrollment, Role, Submission, User
from ..rbac import Principal
from ..storage import get_storage
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
    course = Course(**body.model_dump(), teacher_id=principal.user_id)
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
    key = f"{course_id}/{assignment_id}/{file.filename}"
    storage = get_storage()
    assignment.storage_key = storage.put(
        "lab-archives", key, file.file, file.size or 0
    )
    db.commit()
    return _assignment_out(db, assignment)


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
    db.commit()
    background.add_task(dispatch_pending, SessionLocal())
    return submission

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas
from ..db import SessionLocal, get_db
from ..events import dispatch_pending, emit
from ..models import Comment, User, Vote, Writeup
from ..rbac import Principal
from .deps import get_principal, require_capability

router = APIRouter(prefix="/community", tags=["community"])


def _with_votes(db: Session, writeup: Writeup) -> schemas.WriteupOut:
    votes = db.scalar(
        select(func.coalesce(func.sum(Vote.value), 0)).where(
            Vote.writeup_id == writeup.id
        )
    )
    out = schemas.WriteupOut.model_validate(writeup)
    out.votes = votes
    return out


@router.get("/writeups", response_model=list[schemas.WriteupOut])
def list_writeups(
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
    limit: int = 25,
):
    rows = db.scalars(
        select(Writeup)
        .where(Writeup.published.is_(True))
        .order_by(Writeup.created_at.desc())
        .limit(min(limit, 100))
    ).all()
    return [_with_votes(db, w) for w in rows]


@router.post("/writeups", response_model=schemas.WriteupOut, status_code=201)
def create_writeup(
    body: schemas.WriteupIn,
    background: BackgroundTasks,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    writeup = Writeup(author_id=principal.user_id, **body.model_dump())
    db.add(writeup)
    if writeup.published:
        author = db.get(User, principal.user_id)
        db.flush()
        emit(
            db,
            "writeup.published",
            {
                "writeup_id": writeup.id,
                "title": writeup.title,
                "author": author.handle if author else principal.user_id,
            },
        )
    db.commit()
    background.add_task(dispatch_pending, SessionLocal())
    return _with_votes(db, writeup)


@router.post("/writeups/{writeup_id}/vote", response_model=schemas.WriteupOut)
def vote(
    writeup_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
    value: int = 1,
):
    if value not in (1, -1):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "value is 1 or -1")
    writeup = db.get(Writeup, writeup_id)
    if writeup is None or not writeup.published:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such writeup")
    if writeup.author_id == principal.user_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "no self-votes")
    existing = db.scalar(
        select(Vote).where(
            Vote.writeup_id == writeup_id, Vote.user_id == principal.user_id
        )
    )
    if existing:
        existing.value = value
    else:
        db.add(Vote(writeup_id=writeup_id, user_id=principal.user_id, value=value))
    db.commit()
    return _with_votes(db, writeup)


@router.post(
    "/writeups/{writeup_id}/comments", status_code=201
)
def comment(
    writeup_id: str,
    body: schemas.CommentIn,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    writeup = db.get(Writeup, writeup_id)
    if writeup is None or not writeup.published:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such writeup")
    row = Comment(writeup_id=writeup_id, author_id=principal.user_id, body=body.body)
    db.add(row)
    db.commit()
    return {"id": row.id}


@router.delete("/writeups/{writeup_id}", status_code=204)
def remove_writeup(
    writeup_id: str,
    principal: Principal = Depends(require_capability("community:moderate")),
    db: Session = Depends(get_db),
):
    writeup = db.get(Writeup, writeup_id)
    if writeup is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such writeup")
    writeup.published = False
    db.commit()

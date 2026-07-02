from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import gamification, schemas
from ..db import get_db
from ..models import Role, User
from ..rbac import Principal
from .deps import get_principal, require_capability

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[schemas.UserOut])
def list_users(
    principal: Principal = Depends(require_capability("users:manage")),
    db: Session = Depends(get_db),
):
    return db.scalars(select(User).order_by(User.created_at)).all()


@router.get("/{handle}", response_model=schemas.PublicProfileOut)
def public_profile(
    handle: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.handle == handle))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such user")
    out = schemas.PublicProfileOut.model_validate(user)
    out.community_score = gamification.community_score(db, user.id)
    return out


@router.patch("/{user_id}/role", response_model=schemas.UserOut)
def change_role(
    user_id: str,
    body: schemas.RoleChangeIn,
    principal: Principal = Depends(require_capability("users:manage")),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such user")
    # Admins manage students and teachers; only superadmins touch admin+.
    protected = {Role.admin, Role.superadmin}
    if principal.role is not Role.superadmin and (
        body.role in protected or user.role in protected
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "admin and superadmin roles require superadmin"
        )
    user.role = body.role
    db.commit()
    return user

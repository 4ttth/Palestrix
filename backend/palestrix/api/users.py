from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import gamification, schemas
from ..db import get_db
from ..models import Role, Tenant, User
from ..rbac import Principal
from ..security import hash_password
from .deps import get_principal, require_capability

router = APIRouter(prefix="/users", tags=["users"])

# Roles only a superadmin may hand out or take away.
PROTECTED_ROLES = {Role.admin, Role.superadmin}


@router.get("", response_model=list[schemas.UserOut])
def list_users(
    principal: Principal = Depends(require_capability("users:manage")),
    db: Session = Depends(get_db),
):
    return db.scalars(select(User).order_by(User.created_at)).all()


@router.post("", response_model=schemas.UserOut, status_code=201)
def create_user(
    body: schemas.UserCreateIn,
    principal: Principal = Depends(require_capability("users:manage")),
    db: Session = Depends(get_db),
):
    """Staff-created account: the users console's path to teacher/admin
    accounts (self-registration only ever makes students). Admins create
    students and teachers; admin/superadmin accounts require superadmin."""
    if principal.role is not Role.superadmin and body.role in PROTECTED_ROLES:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "admin and superadmin roles require superadmin"
        )
    taken = db.scalar(
        select(User).where((User.email == body.email) | (User.handle == body.handle))
    )
    if taken:
        raise HTTPException(status.HTTP_409_CONFLICT, "email or handle already in use")
    if body.tenant_id is not None:
        tenant = db.get(Tenant, body.tenant_id)
        if tenant is None or tenant.archived:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "no such active tenant"
            )
    user = User(
        name=body.name,
        handle=body.handle,
        email=body.email,
        role=body.role,
        tenant_id=body.tenant_id,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    return user


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
    if principal.role is not Role.superadmin and (
        body.role in PROTECTED_ROLES or user.role in PROTECTED_ROLES
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "admin and superadmin roles require superadmin"
        )
    user.role = body.role
    db.commit()
    return user


@router.patch("/{user_id}/tenant", response_model=schemas.UserOut)
def change_tenant(
    user_id: str,
    body: schemas.UserTenantIn,
    principal: Principal = Depends(require_capability("users:manage")),
    db: Session = Depends(get_db),
):
    """Assign the user to a tenant (or clear the assignment with null).
    Same effect as POST /admin/tenants/{id}/assign/{handle}, shaped for the
    users console: pick a user, pick a tenant."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such user")
    if body.tenant_id is not None:
        tenant = db.get(Tenant, body.tenant_id)
        if tenant is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no such tenant")
        if tenant.archived:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "tenant is archived; unarchive or pick another"
            )
    user.tenant_id = body.tenant_id
    db.commit()
    return user

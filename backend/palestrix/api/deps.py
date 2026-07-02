"""Request authentication: resolves the caller to a Principal (rbac.py).

Accepted credentials, in precedence order:
1. X-Api-Key: plx_...            (machine, scoped)
2. Authorization: Bearer <jwt>   (session token or client-credentials token)
"""

import jwt as pyjwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ApiKey, OAuthClient, Role, User
from ..rbac import Principal
from ..security import decode_token, sha256_hex


def _unauthorized(detail: str = "not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_principal(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> Principal:
    if x_api_key:
        key = db.scalar(
            select(ApiKey).where(
                ApiKey.key_hash == sha256_hex(x_api_key), ApiKey.revoked.is_(False)
            )
        )
        if key is None:
            raise _unauthorized("invalid API key")
        owner = db.get(User, key.owner_id)
        if owner is None:
            raise _unauthorized("API key owner no longer exists")
        return Principal(
            user_id=owner.id,
            role=owner.role,
            tenant_id=owner.tenant_id,
            kind="api-key",
            scopes=set(key.scopes or []),
        )

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
        try:
            claims = decode_token(token)
        except pyjwt.PyJWTError:
            raise _unauthorized("invalid or expired token")

        if claims.get("typ") == "session":
            user = db.get(User, claims["sub"])
            if user is None:
                raise _unauthorized("account no longer exists")
            return Principal(
                user_id=user.id,
                role=user.role,
                tenant_id=user.tenant_id,
                kind="session",
            )

        if claims.get("typ") == "client":
            client = db.scalar(
                select(OAuthClient).where(OAuthClient.client_id == claims["sub"])
            )
            if client is None:
                raise _unauthorized("client no longer exists")
            owner = db.get(User, client.owner_id)
            if owner is None:
                raise _unauthorized("client owner no longer exists")
            return Principal(
                user_id=owner.id,
                role=owner.role,
                tenant_id=owner.tenant_id,
                kind="client",
                scopes=set(claims.get("scopes", [])),
            )

    raise _unauthorized()


def get_current_user(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
) -> User:
    user = db.get(User, principal.user_id)
    if user is None:
        raise _unauthorized("account no longer exists")
    return user


def require_capability(capability: str):
    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.can(capability):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"requires capability {capability}",
            )
        return principal

    return dependency


def require_role(*roles: Role):
    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"requires role in {[r.value for r in roles]}",
            )
        return principal

    return dependency

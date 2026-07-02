"""Auth: register, password login, WebAuthn ceremonies, API keys, and the
OAuth2 client-credentials token endpoint."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas, webauthn_flow
from ..db import get_db
from ..models import ApiKey, OAuthClient, Role, User, WebAuthnCredential
from ..rbac import Principal, allowed_scopes_for_role
from ..security import (
    create_client_token,
    create_session_token,
    generate_api_key,
    generate_client_secret,
    hash_password,
    sha256_hex,
    verify_password,
)
from .deps import get_current_user, get_principal

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=schemas.TokenOut, status_code=201)
def register(body: schemas.RegisterIn, db: Session = Depends(get_db)):
    taken = db.scalar(
        select(User).where((User.email == body.email) | (User.handle == body.handle))
    )
    if taken:
        raise HTTPException(status.HTTP_409_CONFLICT, "email or handle already in use")
    user = User(
        name=body.name,
        handle=body.handle,
        email=body.email,
        role=Role.student,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    return schemas.TokenOut(
        access_token=create_session_token(user.id, user.role.value, user.tenant_id)
    )


@router.post("/login", response_model=schemas.TokenOut)
def login(body: schemas.LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email))
    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    return schemas.TokenOut(
        access_token=create_session_token(user.id, user.role.value, user.tenant_id)
    )


@router.get("/me", response_model=schemas.UserOut)
def me(user: User = Depends(get_current_user)):
    return user


# -- WebAuthn (passkeys) -------------------------------------------------------


@router.post("/webauthn/register/options")
def webauthn_register_options(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    existing = db.scalars(
        select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)
    ).all()
    return {"options": webauthn_flow.registration_options(user, list(existing))}


@router.post("/webauthn/register/verify", status_code=201)
def webauthn_register_verify(
    body: schemas.WebAuthnVerifyIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        credential = webauthn_flow.verify_registration(user, body.credential)
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"passkey rejected: {exc}")
    db.add(credential)
    db.commit()
    return {"enrolled": True, "credential_id": credential.credential_id}


@router.post("/webauthn/login/options")
def webauthn_login_options(
    body: schemas.WebAuthnLoginOptionsIn, db: Session = Depends(get_db)
):
    user = db.scalar(select(User).where(User.email == body.email))
    if user is None:
        # Same response shape as success to avoid account enumeration.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "passkey login unavailable")
    creds = db.scalars(
        select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)
    ).all()
    if not creds:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "passkey login unavailable")
    return {"options": webauthn_flow.authentication_options(user, list(creds))}


@router.post("/webauthn/login/verify", response_model=schemas.TokenOut)
def webauthn_login_verify(
    body: schemas.WebAuthnVerifyIn,
    email: str,
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "passkey rejected")
    creds = db.scalars(
        select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)
    ).all()
    last_error: Exception | None = None
    for cred in creds:
        try:
            cred.sign_count = webauthn_flow.verify_authentication(
                user, cred, body.credential
            )
            db.commit()
            return schemas.TokenOut(
                access_token=create_session_token(
                    user.id, user.role.value, user.tenant_id
                )
            )
        except Exception as exc:  # try the next enrolled credential
            last_error = exc
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"passkey rejected: {last_error}")


# -- API keys -------------------------------------------------------------------


@router.post("/api-keys", response_model=schemas.ApiKeyCreatedOut, status_code=201)
def create_api_key(
    body: schemas.ApiKeyCreateIn,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    allowed = allowed_scopes_for_role(principal.role)
    illegal = set(body.scopes) - allowed
    if illegal:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"scopes not grantable by your role: {sorted(illegal)}",
        )
    full, prefix, key_hash = generate_api_key()
    key = ApiKey(
        owner_id=principal.user_id,
        name=body.name,
        prefix=prefix,
        key_hash=key_hash,
        scopes=body.scopes,
    )
    db.add(key)
    db.commit()
    return schemas.ApiKeyCreatedOut(
        id=key.id,
        name=key.name,
        prefix=key.prefix,
        scopes=key.scopes,
        revoked=key.revoked,
        created_at=key.created_at,
        key=full,
    )


@router.get("/api-keys", response_model=list[schemas.ApiKeyOut])
def list_api_keys(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
):
    return db.scalars(
        select(ApiKey).where(ApiKey.owner_id == principal.user_id)
    ).all()


@router.delete("/api-keys/{key_id}", status_code=204)
def revoke_api_key(
    key_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    key = db.get(ApiKey, key_id)
    if key is None or key.owner_id != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such key")
    key.revoked = True
    db.commit()


# -- OAuth2 client credentials -----------------------------------------------------


@router.post("/clients", response_model=schemas.OAuthClientCreatedOut, status_code=201)
def create_oauth_client(
    body: schemas.OAuthClientCreateIn,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    allowed = allowed_scopes_for_role(principal.role)
    illegal = set(body.scopes) - allowed
    if illegal:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"scopes not grantable by your role: {sorted(illegal)}",
        )
    secret, secret_hash = generate_client_secret()
    client = OAuthClient(
        client_id=f"plxc_{secret[:8]}",
        secret_hash=secret_hash,
        owner_id=principal.user_id,
        name=body.name,
        scopes=body.scopes,
    )
    db.add(client)
    db.commit()
    return schemas.OAuthClientCreatedOut(
        client_id=client.client_id,
        client_secret=secret,
        name=client.name,
        scopes=client.scopes,
    )


@router.post("/token", response_model=schemas.TokenOut)
def client_credentials_token(
    body: schemas.ClientTokenIn, db: Session = Depends(get_db)
):
    if body.grant_type != "client_credentials":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unsupported grant_type")
    client = db.scalar(
        select(OAuthClient).where(OAuthClient.client_id == body.client_id)
    )
    if client is None or client.secret_hash != sha256_hex(body.client_secret):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid client credentials")
    return schemas.TokenOut(
        access_token=create_client_token(
            client.client_id, client.owner_id, list(client.scopes or [])
        )
    )

"""Auth: register, password login, WebAuthn ceremonies, API keys, and the
OAuth2 client-credentials token endpoint."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas, webauthn_flow
from ..config import get_settings
from ..db import get_db
from ..models import ApiKey, OAuthClient, Role, Tenant, User, WebAuthnCredential
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


def _auto_tenant_id(db: Session) -> str | None:
    """Auto tenancy for self-registration. PALESTRIX_DEFAULT_TENANT_ID wins
    when it names an active tenant; otherwise, when the site has exactly one
    active tenant (the single-class deployment), that one is used. Anything
    else registers unassigned for an admin to place from the users console."""
    settings = get_settings()
    if settings.default_tenant_id:
        tenant = db.get(Tenant, settings.default_tenant_id)
        if tenant is not None and not tenant.archived:
            return tenant.id
    active = db.scalars(select(Tenant).where(Tenant.archived.is_(False)).limit(2)).all()
    if len(active) == 1:
        return active[0].id
    return None


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
        tenant_id=_auto_tenant_id(db),
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


@router.patch("/me", response_model=schemas.UserOut)
def update_me(
    body: schemas.ProfilePatchIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Self-service profile edits. Handle, email, role, and tenant stay
    fixed here — those are identity and access, managed by staff."""
    if body.name is not None:
        user.name = body.name
    db.commit()
    return user


@router.post("/password", status_code=204)
def change_password(
    body: schemas.PasswordChangeIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the account password, proving the current one first. Accounts
    born passkey-only (no password yet) may set one directly."""
    if user.password_hash and not verify_password(
        body.current_password, user.password_hash
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "current password is wrong")
    user.password_hash = hash_password(body.new_password)
    db.commit()


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
    # The assertion names the credential that signed it, so resolve that one
    # rather than trying each enrolled passkey. A loop would consume the
    # single-use challenge on its first miss and fail every account with more
    # than one passkey enrolled.
    credential_id = webauthn_flow.assertion_credential_id(body.credential)
    cred = None
    if credential_id is not None:
        cred = db.scalar(
            select(WebAuthnCredential).where(
                WebAuthnCredential.user_id == user.id,
                WebAuthnCredential.credential_id == credential_id,
            )
        )
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "passkey rejected")
    try:
        cred.sign_count = webauthn_flow.verify_authentication(
            user, cred, body.credential
        )
    except Exception as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, f"passkey rejected: {exc}"
        )
    db.commit()
    return schemas.TokenOut(
        access_token=create_session_token(user.id, user.role.value, user.tenant_id)
    )


@router.get("/webauthn/credentials")
def list_passkeys(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    rows = db.scalars(
        select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)
    ).all()
    return [
        {
            "id": c.id,
            "created_at": c.created_at,
            "transports": list(c.transports or []),
        }
        for c in rows
    ]


@router.delete("/webauthn/credentials/{credential_id}", status_code=204)
def remove_passkey(
    credential_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cred = db.get(WebAuthnCredential, credential_id)
    if cred is None or cred.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such passkey")
    db.delete(cred)
    db.commit()


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

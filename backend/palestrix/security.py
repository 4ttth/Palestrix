"""Credential primitives: password hashing (argon2id), session and
client-credentials JWTs, API keys. WebAuthn ceremonies live in
webauthn_flow.py; who-may-do-what lives in rbac.py."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from .config import get_settings

_ph = PasswordHasher()

ALGORITHM = "HS256"


# -- passwords ---------------------------------------------------------------


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


# -- JWTs --------------------------------------------------------------------


def _encode(claims: dict, ttl_minutes: int) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        **claims,
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
        "iss": "palestrix",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_session_token(user_id: str, role: str, tenant_id: str | None) -> str:
    settings = get_settings()
    return _encode(
        {"sub": user_id, "typ": "session", "role": role, "tenant": tenant_id},
        settings.session_ttl_minutes,
    )


def create_client_token(client_id: str, owner_id: str, scopes: list[str]) -> str:
    settings = get_settings()
    return _encode(
        {"sub": client_id, "typ": "client", "owner": owner_id, "scopes": scopes},
        settings.client_token_ttl_minutes,
    )


def decode_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(
        token, settings.secret_key, algorithms=[ALGORITHM], issuer="palestrix"
    )


# -- API keys and client secrets ----------------------------------------------
# Format: plx_<8 char prefix>_<32 char secret>. Only the sha256 of the full
# key is stored; the prefix column makes lookups and revocation lists legible.


def generate_api_key() -> tuple[str, str, str]:
    """Returns (full_key, prefix, key_hash)."""
    prefix = secrets.token_hex(4)
    secret = secrets.token_urlsafe(24)
    full = f"plx_{prefix}_{secret}"
    return full, f"plx_{prefix}", sha256_hex(full)


def generate_client_secret() -> tuple[str, str]:
    """Returns (secret, secret_hash)."""
    secret = secrets.token_urlsafe(32)
    return secret, sha256_hex(secret)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()

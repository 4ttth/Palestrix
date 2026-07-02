"""WebAuthn (passkey) ceremonies via py_webauthn.

The browser side uses SimpleWebAuthn (Phase 5 wiring): it fetches options
from these helpers, runs navigator.credentials.create()/get(), and posts the
response back for verification.

Challenges are held in an in-process store with a short TTL. That is correct
for a single API process; the multi-process deployment moves this dict to
Redis (same interface) in Phase 4 when Redis arrives for the job queue.
"""

import base64
import time

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import options_to_json
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from .config import get_settings
from .models import User, WebAuthnCredential

_CHALLENGE_TTL = 300  # seconds
_challenges: dict[str, tuple[bytes, float]] = {}


def _remember(key: str, challenge: bytes) -> None:
    now = time.monotonic()
    stale = [k for k, (_, t) in _challenges.items() if now - t > _CHALLENGE_TTL]
    for k in stale:
        _challenges.pop(k, None)
    _challenges[key] = (challenge, now)


def _recall(key: str) -> bytes | None:
    item = _challenges.pop(key, None)
    if item is None:
        return None
    challenge, t = item
    if time.monotonic() - t > _CHALLENGE_TTL:
        return None
    return challenge


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def from_b64url(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


# -- registration -------------------------------------------------------------


def registration_options(user: User, existing: list[WebAuthnCredential]) -> str:
    settings = get_settings()
    options = generate_registration_options(
        rp_id=settings.rp_id,
        rp_name=settings.rp_name,
        user_id=user.id.encode(),
        user_name=user.handle,
        user_display_name=user.name,
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=from_b64url(c.credential_id))
            for c in existing
        ],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    _remember(f"reg:{user.id}", options.challenge)
    return options_to_json(options)


def verify_registration(user: User, credential_json: str) -> WebAuthnCredential:
    settings = get_settings()
    challenge = _recall(f"reg:{user.id}")
    if challenge is None:
        raise ValueError("registration challenge expired or missing")
    verification = verify_registration_response(
        credential=credential_json,
        expected_challenge=challenge,
        expected_origin=settings.origin,
        expected_rp_id=settings.rp_id,
    )
    return WebAuthnCredential(
        user_id=user.id,
        credential_id=b64url(verification.credential_id),
        public_key=b64url(verification.credential_public_key),
        sign_count=verification.sign_count,
    )


# -- authentication ------------------------------------------------------------


def authentication_options(user: User, credentials: list[WebAuthnCredential]) -> str:
    settings = get_settings()
    options = generate_authentication_options(
        rp_id=settings.rp_id,
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=from_b64url(c.credential_id))
            for c in credentials
        ],
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    _remember(f"auth:{user.id}", options.challenge)
    return options_to_json(options)


def verify_authentication(
    user: User, credential: WebAuthnCredential, credential_json: str
) -> int:
    """Returns the new sign count on success; raises on failure."""
    settings = get_settings()
    challenge = _recall(f"auth:{user.id}")
    if challenge is None:
        raise ValueError("authentication challenge expired or missing")
    verification = verify_authentication_response(
        credential=credential_json,
        expected_challenge=challenge,
        expected_origin=settings.origin,
        expected_rp_id=settings.rp_id,
        credential_public_key=from_b64url(credential.public_key),
        credential_current_sign_count=credential.sign_count,
    )
    return verification.new_sign_count

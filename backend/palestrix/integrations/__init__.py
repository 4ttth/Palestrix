"""Phase 8 external-platform integrations (docs/integrations-canvas-lms.md).

PalestrIX integrates outward through one adapter contract: every external
platform implements ``ExternalPlatform``, so adding Moodle or Google
Classroom later follows the exact same path as Canvas LMS, the reference
adapter (``canvas.py``). The registry mirrors the Phase 4 provider, Phase 6
detonator, and Phase 7 cloud registries: nothing is active by default, and
``activate_configured_platforms`` (called from the API lifespan and the
worker) registers whichever adapters the environment configures.

Core-side logic that is the same for every platform lives here, next to the
contract: the signed ``state`` tokens that carry the OIDC nonce through a
launch, the identity-mapping rules (LTI ``sub`` + issuer, claim by e-mail,
never silent account creation), and the roster sync that pre-provisions
student accounts. Wire-format details (JWKS, AGS, NRPS) belong to adapters.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import jwt as pyjwt

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ..models import ExternalCourseLink, GradePassback, User

logger = logging.getLogger("palestrix.integrations")


class LaunchValidationError(Exception):
    """An id_token that fails validation (signature, audience, nonce,
    deployment). The launch endpoint answers 401 with this message."""


@dataclass
class RosterEntry:
    """One member of the platform course, as the platform asserts them."""

    external_id: str  # the LTI sub on the platform
    email: str
    name: str
    role: str  # "student" | "teacher" | "other"


@dataclass
class LaunchClaims:
    """A validated LTI launch, normalized out of the claim URIs so the API
    routes never touch purl.imsglobal.org strings."""

    message_type: str  # "resource" | "deep-link"
    issuer: str
    subject: str
    email: str
    name: str
    roles: list[str] = field(default_factory=list)  # normalized: instructor|learner
    deployment_id: str = ""
    context_id: str = ""
    context_title: str = ""
    nrps_url: str = ""
    lineitem_url: str = ""  # AGS line item bound to this resource link
    resource_link_id: str = ""
    resource_link_title: str = ""
    target_link_uri: str = ""
    custom: dict = field(default_factory=dict)
    deep_link_return_url: str = ""
    deep_link_data: str = ""


@runtime_checkable
class ExternalPlatform(Protocol):
    """The integration contract. Adapters are pure platform clients: they
    validate launches, read rosters, write grades, and sign deep-linking
    responses. They never touch PalestrIX tables — the registry rows are the
    API's to mutate (mirroring the Phase 7 TenantCloud split)."""

    id: str  # "canvas-lms"
    name: str
    issuer: str

    def login_redirect_url(
        self, *, login_hint: str, target_link_uri: str, state: str, nonce: str,
        lti_message_hint: str = "",
    ) -> str: ...

    def validate_launch(self, id_token: str, *, nonce: str) -> LaunchClaims: ...

    def fetch_roster(self, link: "ExternalCourseLink") -> list[RosterEntry]: ...

    def push_grade(self, passback: "GradePassback") -> str: ...

    def deep_link_response_jwt(
        self, *, deployment_id: str, data: str, content_items: list[dict]
    ) -> str: ...

    def jwks(self) -> dict: ...


# -- registry ---------------------------------------------------------------------

_platforms: dict[str, ExternalPlatform] = {}


def register_platform(platform: ExternalPlatform) -> None:
    _platforms[platform.id] = platform


def unregister_platform(platform_id: str) -> None:
    _platforms.pop(platform_id, None)


def get_platform(platform_id: str) -> ExternalPlatform | None:
    return _platforms.get(platform_id)


def active_platforms() -> list[ExternalPlatform]:
    return list(_platforms.values())


def activate_configured_platforms() -> None:
    """Called at startup (API lifespan and the worker). Nothing answers by
    default; PALESTRIX_CANVAS_ISSUER + .._CLIENT_ID activate the Canvas
    adapter."""
    from ..config import get_settings

    settings = get_settings()
    if settings.canvas_issuer and settings.canvas_client_id:
        from .canvas import CanvasPlatform

        register_platform(CanvasPlatform())
        logger.info("canvas-lms platform active (%s)", settings.canvas_issuer)


# -- signed launch state -----------------------------------------------------------
#
# The OIDC initiation -> launch round trip and the deep-linking picker are
# stateless: everything a later request must trust rides in an HS256 JWT
# signed with the app secret (typ discriminates the flows, exp bounds them).


def sign_state(payload: dict, *, typ: str, ttl_minutes: int = 10) -> str:
    from ..config import get_settings

    now = datetime.now(timezone.utc)
    return pyjwt.encode(
        {
            **payload,
            "typ": typ,
            "iat": now,
            "exp": now + timedelta(minutes=ttl_minutes),
            "iss": "palestrix",
        },
        get_settings().secret_key,
        algorithm="HS256",
    )


def read_state(token: str, *, typ: str) -> dict:
    """Raises pyjwt.PyJWTError on anything invalid or expired."""
    from ..config import get_settings

    claims = pyjwt.decode(
        token, get_settings().secret_key, algorithms=["HS256"], issuer="palestrix"
    )
    if claims.get("typ") != typ:
        raise pyjwt.InvalidTokenError(f"state token is not a {typ} token")
    return claims


# Launch nonces are single-use: the state JWT alone would validate again for
# its whole TTL, so a captured launch POST could be replayed. Per-process on
# purpose (launches are browser-mediated and short); a multi-replica edge
# needs sticky sessions on the launch path, noted in the integration doc.
_used_nonces: dict[str, datetime] = {}


def claim_nonce(nonce: str, *, ttl_minutes: int = 10) -> bool:
    """True the first time a nonce is seen, False on any replay."""
    now = datetime.now(timezone.utc)
    for seen, expires in list(_used_nonces.items()):
        if expires < now:
            _used_nonces.pop(seen, None)
    if nonce in _used_nonces:
        return False
    _used_nonces[nonce] = now + timedelta(minutes=ttl_minutes)
    return True


# -- identity mapping ---------------------------------------------------------------


def map_launch_identity(
    db: "Session", platform: ExternalPlatform, claims: LaunchClaims
) -> "User | None":
    """The identity rules from docs/integrations-canvas-lms.md: the mapping
    key is sub + issuer; a first launch with an unmapped identity claims the
    account whose e-mail the platform asserts (roster sync pre-provisions
    them); anything else returns None — never silent account creation."""
    from sqlalchemy import func, select

    from ..models import ExternalIdentity, Role, User

    identity = db.scalar(
        select(ExternalIdentity).where(
            ExternalIdentity.platform == platform.id,
            ExternalIdentity.issuer == claims.issuer,
            ExternalIdentity.subject == claims.subject,
        )
    )
    if identity is not None:
        return db.get(User, identity.user_id)
    if not claims.email:
        return None
    user = db.scalar(
        select(User).where(func.lower(User.email) == claims.email.lower())
    )
    if user is None:
        return None
    # Claim-by-email crosses a trust boundary: the address is whatever the
    # platform asserts, and whoever administers the LMS decides what it
    # says. That is fine for the student and teacher accounts the roster
    # pre-provisions, and not fine for a platform administrator account —
    # an LMS admin could otherwise set a user's e-mail to the superadmin's
    # and have a launch mint a superadmin session. Those accounts are
    # linked deliberately or not at all.
    if user.role in (Role.admin, Role.superadmin):
        logger.warning(
            "refusing to auto-claim the %s account %s from an %s launch; "
            "link it deliberately if that is intended",
            user.role.value,
            user.handle,
            platform.id,
        )
        return None
    db.add(
        ExternalIdentity(
            user_id=user.id,
            platform=platform.id,
            issuer=claims.issuer,
            subject=claims.subject,
            email=claims.email,
        )
    )
    db.flush()
    return user


def _free_handle(db: "Session", seed: str) -> str:
    """A unique handle for a pre-provisioned account, derived from the e-mail
    local part (register's ^[a-z0-9_-]{3,20}$ alphabet)."""
    from sqlalchemy import select

    from ..models import User

    base = re.sub(r"[^a-z0-9_-]", "", seed.split("@", 1)[0].lower())[:16] or "student"
    base = base.ljust(3, "0")
    candidate = base
    n = 1
    while db.scalar(select(User.id).where(User.handle == candidate)) is not None:
        n += 1
        candidate = f"{base}{n}"
    return candidate


# -- roster sync --------------------------------------------------------------------


def sync_roster(db: "Session", platform: ExternalPlatform, link: "ExternalCourseLink") -> dict:
    """Pull the platform roster and converge enrollment. New students get
    pre-provisioned accounts (no password — they claim the account through
    their first launch, then enroll a passkey); students the platform no
    longer lists are unenrolled, but only if this platform mapped them in the
    first place — locally added students are never touched. PalestrIX stays
    the source of truth for handles; the platform for enrollment."""
    from sqlalchemy import func, select

    from ..events import emit
    from ..models import Course, Enrollment, ExternalIdentity, Role, User, utcnow

    course = db.get(Course, link.course_id)
    entries = platform.fetch_roster(link)
    added = provisioned = skipped = 0
    seen: set[str] = set()

    for entry in entries:
        if entry.role != "student":
            continue  # instructors and observers are never provisioned
        identity = db.scalar(
            select(ExternalIdentity).where(
                ExternalIdentity.platform == platform.id,
                ExternalIdentity.issuer == platform.issuer,
                ExternalIdentity.subject == entry.external_id,
            )
        )
        user = db.get(User, identity.user_id) if identity else None
        if user is None and entry.email:
            user = db.scalar(
                select(User).where(func.lower(User.email) == entry.email.lower())
            )
        if user is None:
            if not entry.email:
                skipped += 1  # nothing to key an account on; surfaced in the result
                continue
            user = User(
                handle=_free_handle(db, entry.email),
                name=entry.name or entry.email,
                email=entry.email.lower(),
                role=Role.student,
                tenant_id=course.tenant_id,
                password_hash=None,  # claimed via launch; passkey enrolled in-app
            )
            db.add(user)
            db.flush()
            provisioned += 1
        if identity is None:
            db.add(
                ExternalIdentity(
                    user_id=user.id,
                    platform=platform.id,
                    issuer=platform.issuer,
                    subject=entry.external_id,
                    email=entry.email,
                )
            )
        seen.add(user.id)
        enrolled = db.scalar(
            select(Enrollment).where(
                Enrollment.course_id == course.id, Enrollment.user_id == user.id
            )
        )
        if enrolled is None:
            db.add(Enrollment(course_id=course.id, user_id=user.id))
            added += 1

    removed = 0
    for enrollment in db.scalars(
        select(Enrollment).where(Enrollment.course_id == course.id)
    ).all():
        if enrollment.user_id in seen:
            continue
        mapped = db.scalar(
            select(ExternalIdentity.id).where(
                ExternalIdentity.user_id == enrollment.user_id,
                ExternalIdentity.platform == platform.id,
                ExternalIdentity.issuer == platform.issuer,
            )
        )
        if mapped is not None:
            db.delete(enrollment)
            removed += 1

    link.last_synced_at = utcnow()
    result = {
        "roster": len(entries),
        "added": added,
        "provisioned": provisioned,
        "removed": removed,
        "skipped": skipped,
    }
    emit(db, "roster.synced", {"course_id": course.id, "platform": platform.id, **result})
    return result

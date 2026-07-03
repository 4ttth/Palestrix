"""/integrations: the external-platform surface (Phase 8).

Two kinds of route live here, with different trust models:

- The LTI wire endpoints (jwks, login, launch, deep-link) are public by
  design — the browser arrives from Canvas carrying platform-signed or
  PalestrIX-signed tokens, and those signatures are the authentication.
  Nothing in them trusts a bare parameter.
- The management endpoints (links, sync, grade queue) are ordinary
  authenticated API: teachers manage links for their own courses
  (courses:write + ownership, same rule as the rest of /courses).
"""

import html

import jwt as pyjwt
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    HTTPException,
    Request,
    status,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas
from ..config import get_settings
from ..db import SessionLocal, get_db
from ..events import dispatch_pending
from ..integrations import (
    ExternalPlatform,
    LaunchClaims,
    LaunchValidationError,
    active_platforms,
    claim_nonce,
    get_platform,
    map_launch_identity,
    read_state,
    sign_state,
    sync_roster,
)
from ..integrations.passback import dispatch_due_passbacks
from ..models import (
    Course,
    ExternalCourseLink,
    GradePassback,
    LabTemplate,
    LtiResourceLink,
    Role,
    User,
    uid,
)
from ..rbac import Principal
from ..security import create_session_token
from .deps import get_principal, require_capability

router = APIRouter(prefix="/integrations", tags=["integrations"])


def _canvas_or_503() -> ExternalPlatform:
    platform = get_platform("canvas-lms")
    if platform is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Canvas LMS is not configured (set PALESTRIX_CANVAS_ISSUER and "
            "PALESTRIX_CANVAS_CLIENT_ID)",
        )
    return platform


# -- status -----------------------------------------------------------------------


@router.get("/platforms", response_model=list[schemas.IntegrationPlatformOut])
def list_platforms(principal: Principal = Depends(get_principal)):
    return [
        schemas.IntegrationPlatformOut(
            id=p.id,
            name=p.name,
            issuer=p.issuer,
            features=["launch", "roster", "grades", "deep-linking"],
            ephemeral_key=bool(getattr(p, "ephemeral_key", False)),
        )
        for p in active_platforms()
    ]


# -- LTI wire endpoints (public: signatures are the auth) ---------------------------


@router.get("/canvas/jwks", include_in_schema=False)
def canvas_jwks():
    """The tool keyset Canvas pins for deep-linking responses and client
    assertions. Public by protocol."""
    return _canvas_or_503().jwks()


@router.api_route("/canvas/login", methods=["GET", "POST"], include_in_schema=False)
async def canvas_login(request: Request):
    """OIDC third-party initiation. Canvas calls this with iss/login_hint/
    target_link_uri (GET or form POST); we bounce the browser to the
    platform's authorization endpoint with a signed state carrying the nonce."""
    platform = _canvas_or_503()
    params = dict(request.query_params)
    if request.method == "POST":
        params.update(dict(await request.form()))
    if params.get("iss", "") != platform.issuer:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown issuer")
    login_hint = params.get("login_hint", "")
    target = params.get("target_link_uri", "")
    if not login_hint or not target:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "missing login_hint or target_link_uri"
        )
    nonce = uid()
    state = sign_state({"nonce": nonce}, typ="lti-state")
    return RedirectResponse(
        platform.login_redirect_url(
            login_hint=login_hint,
            target_link_uri=target,
            state=state,
            nonce=nonce,
            lti_message_hint=params.get("lti_message_hint", ""),
        ),
        status_code=302,
    )


def _reconcile_course_link(
    db: Session, platform: ExternalPlatform, claims: LaunchClaims
) -> ExternalCourseLink | None:
    """Attach launch-claim facts to the teacher-created link. Match by the
    LTI context id once known, else by the platform course id the developer
    key's custom field carries (canvas_course_id=$Canvas.course.id)."""
    link = None
    if claims.context_id:
        link = db.scalar(
            select(ExternalCourseLink).where(
                ExternalCourseLink.platform == platform.id,
                ExternalCourseLink.context_id == claims.context_id,
            )
        )
    if link is None:
        external_course_id = str(claims.custom.get("canvas_course_id", ""))
        if external_course_id:
            link = db.scalar(
                select(ExternalCourseLink).where(
                    ExternalCourseLink.platform == platform.id,
                    ExternalCourseLink.external_course_id == external_course_id,
                )
            )
    if link is not None:
        # The launch claims are authoritative for the LTI-side identifiers.
        link.context_id = claims.context_id or link.context_id
        link.context_title = claims.context_title or link.context_title
        link.nrps_url = claims.nrps_url or link.nrps_url
    return link


def _page(title: str, body_html: str) -> HTMLResponse:
    """Minimal self-contained page for the browser mid-LTI-flow (these render
    inside the Canvas iframe; no frontend session exists yet)."""
    return HTMLResponse(
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)} — PalestrIX</title>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<style>body{font-family:system-ui,sans-serif;background:#0d0d0f;color:#e6e6e8;"
        "display:grid;place-items:center;min-height:100vh;margin:0;padding:24px}"
        "main{max-width:560px;width:100%}h1{font-size:18px;margin:0 0 8px}"
        "p{color:#9d9da4;font-size:14px;line-height:1.6}"
        "table{width:100%;border-collapse:collapse;margin-top:16px}"
        "td{padding:10px 8px;border-top:1px solid #26262b;font-size:14px}"
        "button{background:#2f6fed;color:#fff;border:0;border-radius:999px;"
        "padding:6px 16px;font-size:13px;cursor:pointer}"
        "small{color:#6c6c73;font-family:ui-monospace,monospace}</style></head>"
        f"<body><main><h1>{html.escape(title)}</h1>{body_html}</main></body></html>"
    )


@router.post("/canvas/launch", include_in_schema=False)
def canvas_launch(
    id_token: str = Form(...),
    state: str = Form(...),
    db: Session = Depends(get_db),
):
    """The LTI 1.3 launch. Validates the platform-signed id_token, applies
    the identity-mapping rules, then either hands the browser to the app
    with a session (resource launch) or renders the deep-linking picker."""
    platform = _canvas_or_503()
    try:
        launch_state = read_state(state, typ="lti-state")
        claims = platform.validate_launch(id_token, nonce=launch_state["nonce"])
    except (pyjwt.PyJWTError, LaunchValidationError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"launch rejected: {exc}")
    if not claim_nonce(launch_state["nonce"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "launch rejected: replayed nonce")

    user = map_launch_identity(db, platform, claims)
    if user is None:
        # No silent account creation from a launch (integration doc rules).
        return _page(
            "Account not linked yet",
            "<p>Your Canvas identity isn't mapped to a PalestrIX account. Ask "
            "your teacher to run a roster sync for this course, then open the "
            "assignment again.</p>"
            f"<p><small>{html.escape(claims.email or claims.subject)}</small></p>",
        )

    link = _reconcile_course_link(db, platform, claims)

    if claims.message_type == "deep-link":
        if "instructor" not in claims.roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "content selection is an instructor launch"
            )
        continuation = sign_state(
            {
                "sub": user.id,
                "return_url": claims.deep_link_return_url,
                "data": claims.deep_link_data,
                "deployment_id": claims.deployment_id,
                "launch_url": claims.target_link_uri,
            },
            typ="lti-deeplink",
            ttl_minutes=30,
        )
        db.commit()
        return _deep_link_picker(db, user, continuation)

    # Resource launch: bind the content link's grade column and template.
    resource_link = db.scalar(
        select(LtiResourceLink).where(
            LtiResourceLink.platform == platform.id,
            LtiResourceLink.resource_link_id == claims.resource_link_id,
        )
    )
    if resource_link is None:
        resource_link = LtiResourceLink(
            platform=platform.id, resource_link_id=claims.resource_link_id
        )
        db.add(resource_link)
    resource_link.title = claims.resource_link_title or resource_link.title
    resource_link.lineitem_url = claims.lineitem_url or resource_link.lineitem_url
    if link is not None:
        resource_link.link_id = link.id
    template_id = str(claims.custom.get("palestrix_template_id", ""))
    template = db.get(LabTemplate, template_id) if template_id else None
    if template is not None:
        resource_link.lab_template_id = template.id
        if link is not None and resource_link.assignment_id is None:
            # Bind the course's lab assignment for this template: that is the
            # row grades flow through, so passback knows its line item.
            from ..models import Assignment

            assignment = db.scalar(
                select(Assignment).where(
                    Assignment.course_id == link.course_id,
                    Assignment.lab_template_id == template.id,
                )
            )
            if assignment is not None:
                resource_link.assignment_id = assignment.id

    token = create_session_token(user.id, user.role.value, user.tenant_id)
    db.commit()
    settings = get_settings()
    return RedirectResponse(
        f"{settings.origin}/login?lti_token={token}&next=/dashboard",
        status_code=303,
    )


def _deep_link_picker(db: Session, user: User, continuation: str) -> HTMLResponse:
    """Server-rendered template picker for the Canvas assignment editor. The
    continuation JWT carries everything the response JWT needs."""
    templates = db.scalars(
        select(LabTemplate).where(LabTemplate.owner_id == user.id)
    ).all()
    if user.role is Role.superadmin:
        templates = db.scalars(select(LabTemplate)).all()
    if not templates:
        return _page(
            "No lab templates yet",
            "<p>Publish a lab from the PalestrIX course manager first, then "
            "pick it here.</p>",
        )
    rows = "".join(
        "<tr><td><strong>{title}</strong><br><small>{slug}</small></td>"
        "<td style='text-align:right'>"
        "<form method='post' action='deep-link'>"
        "<input type='hidden' name='continuation' value='{continuation}'>"
        "<input type='hidden' name='template_id' value='{tid}'>"
        "<button type='submit'>Select</button></form></td></tr>".format(
            title=html.escape(t.title),
            slug=html.escape(t.slug),
            continuation=html.escape(continuation),
            tid=html.escape(t.id),
        )
        for t in templates
    )
    return _page(
        "Pick a PalestrIX lab",
        "<p>The selected lab becomes this Canvas assignment; students launch "
        "it from Canvas and grades flow back automatically.</p>"
        f"<table>{rows}</table>",
    )


@router.post("/canvas/deep-link", include_in_schema=False)
def canvas_deep_link(
    continuation: str = Form(...),
    template_id: str = Form(...),
    db: Session = Depends(get_db),
):
    """Picker submission: sign the LtiDeepLinkingResponse and auto-post it
    back to Canvas's return URL (the standard browser-mediated handoff)."""
    platform = _canvas_or_503()
    try:
        state = read_state(continuation, typ="lti-deeplink")
    except pyjwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"picker session invalid: {exc}")
    template = db.get(LabTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such lab template")
    from ..integrations.canvas import CanvasPlatform

    response_jwt = platform.deep_link_response_jwt(
        deployment_id=state["deployment_id"],
        data=state.get("data", ""),
        content_items=[
            CanvasPlatform.content_item(template, launch_url=state.get("launch_url", ""))
        ],
    )
    return _page(
        "Returning to Canvas…",
        "<form id='dl' method='post' action='{url}'>"
        "<input type='hidden' name='JWT' value='{jwt}'>"
        "<noscript><button type='submit'>Continue</button></noscript></form>"
        "<script>document.getElementById('dl').submit()</script>".format(
            url=html.escape(state["return_url"]), jwt=html.escape(response_jwt)
        ),
    )


# -- link management (authenticated) --------------------------------------------------


def _course_teacher_or_403(db: Session, principal: Principal, course_id: str) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such course")
    if principal.role is not Role.superadmin and course.teacher_id != principal.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your course")
    return course


def _link_out(db: Session, link: ExternalCourseLink) -> schemas.ExternalLinkOut:
    out = schemas.ExternalLinkOut.model_validate(link)
    counts = dict(
        db.execute(
            select(GradePassback.status, func.count(GradePassback.id))
            .where(GradePassback.link_id == link.id)
            .group_by(GradePassback.status)
        ).all()
    )
    out.grades_pending = counts.get("pending", 0)
    out.grades_delivered = counts.get("delivered", 0)
    out.grades_failed = counts.get("failed", 0)
    return out


@router.post("/links", response_model=schemas.ExternalLinkOut, status_code=201)
def create_link(
    body: schemas.ExternalLinkIn,
    principal: Principal = Depends(require_capability("courses:write")),
    db: Session = Depends(get_db),
):
    if get_platform(body.platform) is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"platform {body.platform} is not active"
        )
    _course_teacher_or_403(db, principal, body.course_id)
    exists = db.scalar(
        select(ExternalCourseLink).where(
            ExternalCourseLink.platform == body.platform,
            ExternalCourseLink.course_id == body.course_id,
        )
    )
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "course is already linked")
    link = ExternalCourseLink(**body.model_dump(), created_by=principal.user_id)
    db.add(link)
    db.commit()
    return _link_out(db, link)


@router.get("/links", response_model=list[schemas.ExternalLinkOut])
def list_links(
    course_id: str | None = None,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    query = select(ExternalCourseLink)
    if course_id:
        query = query.where(ExternalCourseLink.course_id == course_id)
    if principal.role not in (Role.admin, Role.superadmin):
        query = query.join(Course, Course.id == ExternalCourseLink.course_id).where(
            Course.teacher_id == principal.user_id
        )
    return [_link_out(db, link) for link in db.scalars(query).all()]


@router.delete("/links/{link_id}", status_code=204)
def delete_link(
    link_id: str,
    principal: Principal = Depends(require_capability("courses:write")),
    db: Session = Depends(get_db),
):
    """Unlink. Mapped identities and delivered receipts stay — grades already
    passed back are never retracted (integration doc rules)."""
    link = db.get(ExternalCourseLink, link_id)
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such link")
    _course_teacher_or_403(db, principal, link.course_id)
    for rl in db.scalars(
        select(LtiResourceLink).where(LtiResourceLink.link_id == link.id)
    ).all():
        rl.link_id = None
    db.delete(link)
    db.commit()


@router.post("/links/{link_id}/sync", response_model=schemas.RosterSyncOut)
def sync_link_roster(
    link_id: str,
    background: BackgroundTasks,
    principal: Principal = Depends(require_capability("courses:write")),
    db: Session = Depends(get_db),
):
    link = db.get(ExternalCourseLink, link_id)
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such link")
    _course_teacher_or_403(db, principal, link.course_id)
    platform = get_platform(link.platform)
    if platform is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"platform {link.platform} is not active"
        )
    try:
        result = sync_roster(db, platform, link)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"roster fetch failed: {exc}"
        )
    db.commit()
    background.add_task(dispatch_pending, SessionLocal())
    return schemas.RosterSyncOut(**result)


# -- grade passback queue --------------------------------------------------------------


def _passback_out(db: Session, row: GradePassback) -> schemas.GradePassbackOut:
    out = schemas.GradePassbackOut.model_validate(row)
    student = db.get(User, row.user_id)
    out.student_handle = student.handle if student else row.user_id
    from ..models import Assignment

    assignment = db.get(Assignment, row.assignment_id)
    out.assignment_title = assignment.title if assignment else row.assignment_id
    return out


@router.get("/links/{link_id}/grades", response_model=list[schemas.GradePassbackOut])
def list_grade_passbacks(
    link_id: str,
    principal: Principal = Depends(require_capability("courses:write")),
    db: Session = Depends(get_db),
):
    link = db.get(ExternalCourseLink, link_id)
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such link")
    _course_teacher_or_403(db, principal, link.course_id)
    rows = db.scalars(
        select(GradePassback)
        .where(GradePassback.link_id == link_id)
        .order_by(GradePassback.created_at.desc())
        .limit(100)
    ).all()
    return [_passback_out(db, row) for row in rows]


@router.post("/grades/{passback_id}/retry", response_model=schemas.GradePassbackOut)
def retry_grade_passback(
    passback_id: str,
    principal: Principal = Depends(require_capability("courses:write")),
    db: Session = Depends(get_db),
):
    """Requeue a parked row and attempt delivery right now. The response is
    the row after that attempt — delivered, or pending with the next backoff."""
    row = db.get(GradePassback, passback_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such passback")
    link = db.get(ExternalCourseLink, row.link_id)
    _course_teacher_or_403(db, principal, link.course_id)
    if row.status == "delivered":
        raise HTTPException(status.HTTP_409_CONFLICT, "already delivered")
    from ..models import utcnow

    row.status = "pending"
    row.attempts = 0
    row.error = None
    row.next_attempt_at = utcnow()
    db.commit()
    dispatch_due_passbacks(db)
    db.refresh(row)
    return _passback_out(db, row)

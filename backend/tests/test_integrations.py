"""Phase 8: the Canvas LMS integration (docs/integrations-canvas-lms.md).

The Canvas adapter runs against a mocked platform (httpx MockTransport,
mirroring the Phase 4/7 adapter tests): the mock serves the platform keyset,
verifies the tool's client-credentials assertion before issuing service
tokens, answers NRPS membership, and records AGS score posts. The LTI wire
endpoints are exercised end to end — OIDC initiation, id_token validation,
identity mapping, the deep-linking picker round trip — plus roster sync
(pre-provisioning and drops) and grade passback with retry/backoff.
"""

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, parse_qsl, urlsplit

import httpx
import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select

from test_orchestration import _publish_container_template

ISSUER = "https://canvas.test"
CLIENT_ID = "10000000000042"
DEPLOYMENT_ID = "1:deadbeef"
LAUNCH_URL = "https://palestrix.test/api/v1/integrations/canvas/launch"

# One platform (Canvas-side) signing key for the whole module; RSA keygen is
# the slow part, so the tests share it.
PLATFORM_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PLATFORM_KID = "platform-key-1"

ROLE_LEARNER = "http://purl.imsglobal.org/vocab/lis/v2/membership#Learner"
ROLE_INSTRUCTOR = "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"


def _platform_jwks() -> dict:
    jwk = json.loads(pyjwt.algorithms.RSAAlgorithm.to_jwk(PLATFORM_KEY.public_key()))
    jwk.update({"kid": PLATFORM_KID, "use": "sig", "alg": "RS256"})
    return {"keys": [jwk]}


@pytest.fixture()
def canvas(client):
    """Register a Canvas adapter whose httpx client talks to a mocked
    platform. ``record`` is the mock's shared state: roster members, AGS
    failure toggle, and everything the platform received."""
    from palestrix.integrations import register_platform, unregister_platform
    from palestrix.integrations.canvas import CanvasPlatform

    record = {"members": [], "scores": [], "token_scopes": [], "ags_fail": False}
    holder = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/lti/security/jwks":
            return httpx.Response(200, json=_platform_jwks())
        if path == "/login/oauth2/token":
            form = dict(parse_qsl(request.content.decode()))
            # The assertion must verify against the tool's published JWKS.
            tool_jwk = holder["platform"].jwks()["keys"][0]
            tool_key = pyjwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(tool_jwk))
            claims = pyjwt.decode(
                form["client_assertion"],
                key=tool_key,
                algorithms=["RS256"],
                audience=f"{ISSUER}/login/oauth2/token",
            )
            assert claims["iss"] == CLIENT_ID
            record["token_scopes"].append(form["scope"])
            return httpx.Response(
                200, json={"access_token": "tok-123", "expires_in": 3600}
            )
        if re.fullmatch(r"/api/lti/courses/\d+/names_and_roles", path):
            assert request.headers["Authorization"] == "Bearer tok-123"
            return httpx.Response(200, json={"members": record["members"]})
        if path.endswith("/scores"):
            assert request.headers["Authorization"] == "Bearer tok-123"
            assert request.headers["Content-Type"] == "application/vnd.ims.lis.v1.score+json"
            record["scores"].append(json.loads(request.content))
            if record["ags_fail"]:
                return httpx.Response(500, text="canvas exploded")
            return httpx.Response(
                200, headers={"Location": f"{ISSUER}/results/{len(record['scores'])}"}
            )
        return httpx.Response(404, text=f"unmocked {path}")

    platform = CanvasPlatform(
        client=httpx.Client(transport=httpx.MockTransport(handler), base_url=ISSUER),
        issuer=ISSUER,
        client_id=CLIENT_ID,
        deployment_id=DEPLOYMENT_ID,
    )
    holder["platform"] = platform
    register_platform(platform)
    yield platform, record
    unregister_platform("canvas-lms")


def _initiate(client) -> tuple[str, str]:
    """Run the OIDC initiation and return (state, nonce) from the redirect."""
    resp = client.get(
        "/api/v1/integrations/canvas/login",
        params={
            "iss": ISSUER,
            "login_hint": "opaque-hint",
            "target_link_uri": LAUNCH_URL,
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302, resp.text
    location = resp.headers["location"]
    assert location.startswith(f"{ISSUER}/api/lti/authorize_redirect?")
    params = parse_qs(urlsplit(location).query)
    assert params["client_id"] == [CLIENT_ID]
    assert params["redirect_uri"] == [LAUNCH_URL]
    assert params["response_mode"] == ["form_post"]
    return params["state"][0], params["nonce"][0]


def _id_token(
    nonce: str,
    *,
    email: str,
    sub: str = "canvas-user-1",
    name: str = "Canvas User",
    message_type: str = "LtiResourceLinkRequest",
    roles: tuple = (ROLE_LEARNER,),
    canvas_course_id: str = "",
    template_id: str = "",
    context_id: str = "ctx-1",
    resource_link_id: str = "rl-1",
    lineitem: str = f"{ISSUER}/api/lti/courses/77/line_items/5",
    audience: str = CLIENT_ID,
    key=PLATFORM_KEY,
) -> str:
    now = datetime.now(timezone.utc)
    custom = {}
    if canvas_course_id:
        custom["canvas_course_id"] = canvas_course_id
    if template_id:
        custom["palestrix_template_id"] = template_id
    claims = {
        "iss": ISSUER,
        "aud": audience,
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "nonce": nonce,
        "sub": sub,
        "email": email,
        "name": name,
        "https://purl.imsglobal.org/spec/lti/claim/message_type": message_type,
        "https://purl.imsglobal.org/spec/lti/claim/version": "1.3.0",
        "https://purl.imsglobal.org/spec/lti/claim/deployment_id": DEPLOYMENT_ID,
        "https://purl.imsglobal.org/spec/lti/claim/target_link_uri": LAUNCH_URL,
        "https://purl.imsglobal.org/spec/lti/claim/roles": list(roles),
        "https://purl.imsglobal.org/spec/lti/claim/context": {
            "id": context_id,
            "title": "Canvas Course 77",
        },
        "https://purl.imsglobal.org/spec/lti/claim/custom": custom,
        "https://purl.imsglobal.org/spec/lti-nrps/claim/namesroleservice": {
            "context_memberships_url": f"{ISSUER}/api/lti/courses/77/names_and_roles",
        },
    }
    if message_type == "LtiResourceLinkRequest":
        claims["https://purl.imsglobal.org/spec/lti/claim/resource_link"] = {
            "id": resource_link_id,
            "title": "Lab via Canvas",
        }
        claims["https://purl.imsglobal.org/spec/lti-ags/claim/endpoint"] = {
            "lineitem": lineitem,
            "scope": ["https://purl.imsglobal.org/spec/lti-ags/scope/score"],
        }
    else:
        claims["https://purl.imsglobal.org/spec/lti-dl/claim/deep_linking_settings"] = {
            "deep_link_return_url": f"{ISSUER}/courses/77/deep_linking_response",
            "data": "opaque-dl-data",
        }
    return pyjwt.encode(claims, key, algorithm="RS256", headers={"kid": PLATFORM_KID})


def _linked_course_with_lab(client, teacher, canvas_course_id: str) -> dict:
    """A course linked to a Canvas course, carrying a published lab template
    and its lab assignment — the deep-linked shape grades flow through."""
    course = client.post(
        "/api/v1/courses",
        json={"code": f"CS-{uuid.uuid4().hex[:4]}", "title": "LTI Course"},
        headers=teacher,
    ).json()
    link = client.post(
        "/api/v1/integrations/links",
        json={"course_id": course["id"], "external_course_id": canvas_course_id},
        headers=teacher,
    )
    assert link.status_code == 201, link.text
    template = _publish_container_template(client, teacher)
    assignment = client.post(
        f"/api/v1/courses/{course['id']}/assignments",
        json={"title": "Canvas Lab", "kind": "lab", "lab_template_id": template["id"]},
        headers=teacher,
    ).json()
    return {
        "course": course,
        "link": link.json(),
        "template": template,
        "assignment": assignment,
    }


# -- tool keyset and platform listing ------------------------------------------------


def test_jwks_and_platform_listing(client, canvas, teacher):
    jwks = client.get("/api/v1/integrations/canvas/jwks")
    assert jwks.status_code == 200
    key = jwks.json()["keys"][0]
    assert (key["kty"], key["use"], key["alg"]) == ("RSA", "sig", "RS256")
    assert key["kid"]

    platforms = client.get("/api/v1/integrations/platforms", headers=teacher).json()
    assert len(platforms) == 1
    assert platforms[0]["id"] == "canvas-lms"
    assert platforms[0]["issuer"] == ISSUER
    assert "grades" in platforms[0]["features"]
    assert platforms[0]["ephemeral_key"] is True  # no PEM configured in tests

    # Without any registered platform the wire endpoints answer 503.
    from palestrix.integrations import register_platform, unregister_platform

    platform, _ = canvas
    unregister_platform("canvas-lms")
    try:
        assert client.get("/api/v1/integrations/canvas/jwks").status_code == 503
    finally:
        register_platform(platform)


def test_oidc_initiation(client, canvas):
    state, nonce = _initiate(client)
    assert state and nonce

    wrong_issuer = client.get(
        "/api/v1/integrations/canvas/login",
        params={
            "iss": "https://evil.test",
            "login_hint": "x",
            "target_link_uri": LAUNCH_URL,
        },
        follow_redirects=False,
    )
    assert wrong_issuer.status_code == 400


# -- the LTI 1.3 launch ---------------------------------------------------------------


def test_resource_launch_maps_identity_and_binds_grade_column(
    client, canvas, teacher
):
    from palestrix.db import SessionLocal
    from palestrix.models import ExternalIdentity, LtiResourceLink

    setup = _linked_course_with_lab(client, teacher, canvas_course_id="77")
    state, nonce = _initiate(client)
    resource_link_id = f"rl-{uuid.uuid4().hex[:6]}"
    launch = client.post(
        "/api/v1/integrations/canvas/launch",
        data={
            "id_token": _id_token(
                nonce,
                email="stud1@example.edu",
                sub="canvas-stud-1",
                canvas_course_id="77",
                template_id=setup["template"]["id"],
                resource_link_id=resource_link_id,
            ),
            "state": state,
        },
        follow_redirects=False,
    )
    assert launch.status_code == 303, launch.text
    location = launch.headers["location"]
    # The session token rides in the fragment, never the query string: a
    # query string is logged by every proxy on the way and kept in history.
    assert location.startswith("http://localhost:3000/login#lti_token=")
    assert urlsplit(location).query == ""

    # The session token from the handoff authenticates as the mapped student.
    token = parse_qs(urlsplit(location).fragment)["lti_token"][0]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["handle"] == "stud1"

    # The launch claims attached the LTI context to the teacher's link.
    links = client.get(
        f"/api/v1/integrations/links?course_id={setup['course']['id']}", headers=teacher
    ).json()
    assert links[0]["context_id"] == "ctx-1"
    assert links[0]["context_title"] == "Canvas Course 77"

    # The identity mapping and the grade-column binding were recorded.
    db = SessionLocal()
    try:
        identity = db.query(ExternalIdentity).filter_by(subject="canvas-stud-1").one()
        assert identity.email == "stud1@example.edu"
        rl = db.query(LtiResourceLink).filter_by(resource_link_id=resource_link_id).one()
        assert rl.lineitem_url.endswith("/line_items/5")
        assert rl.lab_template_id == setup["template"]["id"]
        assert rl.assignment_id == setup["assignment"]["id"]
        assert rl.link_id == setup["link"]["id"]
    finally:
        db.close()

    # Replaying the captured launch POST is refused (single-use nonce).
    replay = client.post(
        "/api/v1/integrations/canvas/launch",
        data={
            "id_token": _id_token(nonce, email="stud1@example.edu", sub="canvas-stud-1"),
            "state": state,
        },
        follow_redirects=False,
    )
    assert replay.status_code == 401 and "replayed" in replay.json()["detail"]


def test_launch_rejects_bad_tokens(client, canvas):
    state, nonce = _initiate(client)

    # Audience for someone else's tool.
    wrong_aud = client.post(
        "/api/v1/integrations/canvas/launch",
        data={
            "id_token": _id_token(nonce, email="stud1@example.edu", audience="other"),
            "state": state,
        },
        follow_redirects=False,
    )
    assert wrong_aud.status_code == 401

    # Signed by a key the platform keyset does not carry the kid for is
    # impossible to fake here, so tamper the cheap way: a different nonce.
    wrong_nonce = client.post(
        "/api/v1/integrations/canvas/launch",
        data={
            "id_token": _id_token("some-other-nonce", email="stud1@example.edu"),
            "state": state,
        },
        follow_redirects=False,
    )
    assert wrong_nonce.status_code == 401
    assert "nonce" in wrong_nonce.json()["detail"]


def test_unmapped_identity_never_creates_an_account(client, canvas):
    from palestrix.db import SessionLocal
    from palestrix.models import User

    state, nonce = _initiate(client)
    resp = client.post(
        "/api/v1/integrations/canvas/launch",
        data={
            "id_token": _id_token(
                nonce, email="stranger@nowhere.edu", sub="canvas-stranger"
            ),
            "state": state,
        },
        follow_redirects=False,
    )
    # A friendly page, not a session and not an account.
    assert resp.status_code == 200
    assert "roster sync" in resp.text
    db = SessionLocal()
    try:
        assert (
            db.query(User).filter_by(email="stranger@nowhere.edu").one_or_none() is None
        )
    finally:
        db.close()


# -- roster sync -------------------------------------------------------------------


def test_roster_sync_provisions_and_drops(client, canvas, teacher, student2):
    from palestrix.db import SessionLocal
    from palestrix.models import User

    _, record = canvas
    setup = _linked_course_with_lab(client, teacher, canvas_course_id="78")
    link_id = setup["link"]["id"]
    course_id = setup["course"]["id"]

    # A locally enrolled student the platform knows nothing about.
    enroll = client.post(f"/api/v1/courses/{course_id}/enroll", headers=student2)
    assert enroll.status_code == 201

    fresh_email = f"nova-{uuid.uuid4().hex[:6]}@example.edu"
    record["members"] = [
        {  # existing account, mapped by e-mail claim
            "user_id": "canvas-stud-1",
            "email": "stud1@example.edu",
            "name": "Studious Student",
            "roles": [ROLE_LEARNER],
        },
        {  # brand new: pre-provisioned, claimed on first launch
            "user_id": "canvas-nova",
            "email": fresh_email,
            "name": "Nova Learner",
            "roles": [ROLE_LEARNER],
        },
        {  # instructors are never provisioned
            "user_id": "canvas-teacher",
            "email": "somewhere@else.edu",
            "name": "Their Teacher",
            "roles": [ROLE_INSTRUCTOR],
        },
    ]
    resp = client.post(f"/api/v1/integrations/links/{link_id}/sync", headers=teacher)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "roster": 3,
        "added": 2,
        "provisioned": 1,
        "removed": 0,
        "skipped": 0,
    }
    assert "contextmembership.readonly" in record["token_scopes"][-1]

    db = SessionLocal()
    try:
        nova = db.query(User).filter_by(email=fresh_email).one()
        assert nova.role.value == "student"
        assert nova.password_hash is None  # claimed via launch, then passkey
        assert nova.tenant_id == setup["course"]["tenant_id"]
    finally:
        db.close()

    # A pre-provisioned account cannot password-login before claiming.
    denied = client.post(
        "/api/v1/auth/login", json={"email": fresh_email, "password": "whatever-123!"}
    )
    assert denied.status_code == 401

    # Nova drops off the Canvas roster: unenrolled on the next sync. The
    # locally added student2 has no Canvas mapping and is left alone.
    record["members"] = record["members"][:1] + record["members"][2:]
    resp = client.post(f"/api/v1/integrations/links/{link_id}/sync", headers=teacher)
    assert resp.status_code == 200
    body = resp.json()
    assert body["removed"] == 1 and body["added"] == 0 and body["provisioned"] == 0

    listed = client.get("/api/v1/courses", headers=student2).json()
    assert any(c["id"] == course_id for c in listed)  # still enrolled

    # Link management is the course teacher's, not students'.
    forbidden = client.post(
        f"/api/v1/integrations/links/{link_id}/sync", headers=student2
    )
    assert forbidden.status_code == 403


# -- deep linking ---------------------------------------------------------------------


def test_deep_linking_picker_round_trip(client, canvas, teacher):
    platform, _ = canvas
    template = _publish_container_template(client, teacher)

    state, nonce = _initiate(client)
    picker = client.post(
        "/api/v1/integrations/canvas/launch",
        data={
            "id_token": _id_token(
                nonce,
                email="teach1@example.edu",
                sub="canvas-teach-1",
                message_type="LtiDeepLinkingRequest",
                roles=(ROLE_INSTRUCTOR,),
            ),
            "state": state,
        },
        follow_redirects=False,
    )
    assert picker.status_code == 200, picker.text
    assert template["title"] in picker.text
    continuation = re.search(
        r"name='continuation' value='([^']+)'", picker.text
    ).group(1)

    # Students cannot reach the picker.
    state2, nonce2 = _initiate(client)
    denied = client.post(
        "/api/v1/integrations/canvas/launch",
        data={
            "id_token": _id_token(
                nonce2,
                email="stud1@example.edu",
                sub="canvas-stud-1",
                message_type="LtiDeepLinkingRequest",
                roles=(ROLE_LEARNER,),
            ),
            "state": state2,
        },
        follow_redirects=False,
    )
    assert denied.status_code == 403

    # Selecting a template returns the signed LtiDeepLinkingResponse, posted
    # back to Canvas's return URL by the auto-submitting form.
    selected = client.post(
        "/api/v1/integrations/canvas/deep-link",
        data={"continuation": continuation, "template_id": template["id"]},
    )
    assert selected.status_code == 200
    assert f"action='{ISSUER}/courses/77/deep_linking_response'" in selected.text
    response_jwt = re.search(r"name='JWT' value='([^']+)'", selected.text).group(1)

    tool_key = pyjwt.algorithms.RSAAlgorithm.from_jwk(
        json.dumps(platform.jwks()["keys"][0])
    )
    claims = pyjwt.decode(
        response_jwt, key=tool_key, algorithms=["RS256"], audience=ISSUER
    )
    assert claims["iss"] == CLIENT_ID
    assert (
        claims["https://purl.imsglobal.org/spec/lti/claim/message_type"]
        == "LtiDeepLinkingResponse"
    )

    # The picker lists only the instructor's own templates, but the form it
    # posts carries the id, and this handler took whatever arrived — so a
    # valid continuation could deep-link somebody else's lab. What the UI
    # offers is never the boundary; the handler checks ownership itself.
    from palestrix.db import SessionLocal
    from palestrix.models import LabTemplate, User

    db = SessionLocal()
    try:
        other = db.scalar(select(User).where(User.handle == "stud1"))
        theirs = LabTemplate(
            slug="someone-elses:1.0",
            title="Not The Teacher's Lab",
            kind="container",
            owner_id=other.id,
        )
        db.add(theirs)
        db.commit()
        foreign_id = theirs.id
    finally:
        db.close()

    stolen = client.post(
        "/api/v1/integrations/canvas/deep-link",
        data={"continuation": continuation, "template_id": foreign_id},
    )
    assert stolen.status_code == 403, stolen.text
    assert claims["https://purl.imsglobal.org/spec/lti-dl/claim/data"] == "opaque-dl-data"
    item = claims["https://purl.imsglobal.org/spec/lti-dl/claim/content_items"][0]
    assert item["type"] == "ltiResourceLink"
    assert item["custom"]["palestrix_template_id"] == template["id"]
    assert item["lineItem"] == {"scoreMaximum": 100}
    assert item["url"] == LAUNCH_URL


# -- grade passback -------------------------------------------------------------------


def test_grade_passback_delivers_with_retry(client, canvas, teacher, student):
    _, record = canvas
    setup = _linked_course_with_lab(client, teacher, canvas_course_id="79")
    course_id = setup["course"]["id"]
    assignment_id = setup["assignment"]["id"]
    link_id = setup["link"]["id"]

    # The student launches from Canvas once: that maps their identity and
    # binds the assignment's grade column (line item).
    state, nonce = _initiate(client)
    launch = client.post(
        "/api/v1/integrations/canvas/launch",
        data={
            "id_token": _id_token(
                nonce,
                email="stud1@example.edu",
                sub="canvas-stud-1",
                canvas_course_id="79",
                template_id=setup["template"]["id"],
                context_id="ctx-79",
                resource_link_id=f"rl-{uuid.uuid4().hex[:6]}",
                lineitem=f"{ISSUER}/api/lti/courses/79/line_items/9?type=external",
            ),
            "state": state,
        },
        follow_redirects=False,
    )
    assert launch.status_code == 303, launch.text

    client.post(f"/api/v1/courses/{course_id}/enroll", headers=student)
    submission = client.post(
        f"/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions",
        headers=student,
    ).json()

    # Grade while Canvas is down: the row queues, the first attempt fails,
    # and backoff parks it for later instead of dropping the grade.
    record["ags_fail"] = True
    graded = client.post(
        f"/api/v1/courses/{course_id}/assignments/{assignment_id}"
        f"/submissions/{submission['id']}/grade",
        json={"grade": 88},
        headers=teacher,
    )
    assert graded.status_code == 200, graded.text

    rows = client.get(
        f"/api/v1/integrations/links/{link_id}/grades", headers=teacher
    ).json()
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "pending" and row["attempts"] == 1
    assert "500" in row["error"]
    assert row["student_handle"] == "stud1"
    assert row["assignment_title"] == "Canvas Lab"

    link_row = client.get(
        f"/api/v1/integrations/links?course_id={course_id}", headers=teacher
    ).json()[0]
    assert link_row["grades_pending"] == 1

    # Canvas recovers; a manual retry delivers and keeps the receipt.
    record["ags_fail"] = False
    retried = client.post(
        f"/api/v1/integrations/grades/{row['id']}/retry", headers=teacher
    )
    assert retried.status_code == 200, retried.text
    body = retried.json()
    assert body["status"] == "delivered"
    assert body["receipt"].startswith(f"{ISSUER}/results/")
    assert body["error"] is None

    # The score reached the line item bound at launch, on the AGS wire shape.
    score = record["scores"][-1]
    assert score["scoreGiven"] == 88.0
    assert score["scoreMaximum"] == 100.0
    assert score["userId"] == "canvas-stud-1"
    assert score["gradingProgress"] == "FullyGraded"
    assert "score" in record["token_scopes"][-1]

    # Retrying a delivered row is refused.
    again = client.post(
        f"/api/v1/integrations/grades/{row['id']}/retry", headers=teacher
    )
    assert again.status_code == 409

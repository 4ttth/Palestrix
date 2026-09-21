"""Phase 5: the display-enrichment fields and admin read endpoints the live
frontend surfaces render. Additive contract only — shapes existing clients
rely on are covered by the earlier test modules."""

import os
from datetime import datetime, timedelta, timezone

from palestrix.db import SessionLocal
from palestrix.models import Module, Path


def test_module_completed_flag_follows_caller(client, student, student2):
    db = SessionLocal()
    try:
        path = Path(slug="surfaces-path", title="Surfaces Path", hours=5)
        db.add(path)
        db.flush()
        for i, title in enumerate(["First steps", "Second steps"]):
            db.add(
                Module(path_id=path.id, title=title, position=i, palestras_award=10)
            )
        db.commit()
    finally:
        db.close()

    modules = client.get(
        "/api/v1/academy/paths/surfaces-path/modules", headers=student
    ).json()
    assert [m["completed"] for m in modules] == [False, False]

    done = client.post(
        f"/api/v1/academy/modules/{modules[0]['id']}/complete", headers=student
    )
    assert done.status_code == 201

    mine = client.get(
        "/api/v1/academy/paths/surfaces-path/modules", headers=student
    ).json()
    assert [m["completed"] for m in mine] == [True, False]
    # Another caller's view is untouched.
    theirs = client.get(
        "/api/v1/academy/paths/surfaces-path/modules", headers=student2
    ).json()
    assert [m["completed"] for m in theirs] == [False, False]


def test_challenge_solved_and_first_blood_at(client, teacher, student, student2):
    now = datetime.now(timezone.utc)
    event = client.post(
        "/api/v1/compete/events",
        json={
            "title": "Surfaces Round",
            "starts_at": (now - timedelta(hours=1)).isoformat(),
            "ends_at": (now + timedelta(hours=4)).isoformat(),
        },
        headers=teacher,
    ).json()
    challenge = client.post(
        f"/api/v1/compete/events/{event['id']}/challenges",
        json={
            "title": "Surfaces Warmup",
            "category": "Misc",
            "points": 50,
            "flag": "CLCTF{surfaces}",
            "palestras_award": 10,
        },
        headers=teacher,
    ).json()

    board = client.get(
        f"/api/v1/compete/events/{event['id']}/challenges", headers=student
    ).json()
    row = next(c for c in board if c["id"] == challenge["id"])
    assert row["solved"] is False and row["first_blood_at"] is None

    ok = client.post(
        f"/api/v1/compete/challenges/{challenge['id']}/submit",
        json={"flag": "CLCTF{surfaces}"},
        headers=student,
    )
    assert ok.status_code == 200 and ok.json()["correct"] is True

    mine = next(
        c
        for c in client.get(
            f"/api/v1/compete/events/{event['id']}/challenges", headers=student
        ).json()
        if c["id"] == challenge["id"]
    )
    assert mine["solved"] is True
    assert mine["first_blood"] == "stud1"
    assert mine["first_blood_at"] is not None

    theirs = next(
        c
        for c in client.get(
            f"/api/v1/compete/events/{event['id']}/challenges", headers=student2
        ).json()
        if c["id"] == challenge["id"]
    )
    assert theirs["solved"] is False  # solved is per caller


def test_writeup_author_handle_and_comment_count(client, student, student2):
    writeup = client.post(
        "/api/v1/community/writeups",
        json={
            "title": "Surfaces: enrichment notes",
            "body_md": "Notes.",
            "tags": ["meta"],
            "published": True,
        },
        headers=student,
    ).json()
    assert writeup["author_handle"] == "stud1"
    assert writeup["comments"] == 0

    client.post(
        f"/api/v1/community/writeups/{writeup['id']}/comments",
        json={"body": "Nice one."},
        headers=student2,
    )
    listed = next(
        w
        for w in client.get("/api/v1/community/writeups", headers=student2).json()
        if w["id"] == writeup["id"]
    )
    assert listed["author_handle"] == "stud1"
    assert listed["comments"] == 1


def test_course_and_assignment_counts(client, teacher, student):
    course = client.post(
        "/api/v1/courses",
        json={"code": "TST 500", "title": "Surfaces 500", "section": "T5"},
        headers=teacher,
    ).json()
    assert course["students"] == 0 and course["assignments"] == 0

    client.post(f"/api/v1/courses/{course['id']}/enroll", headers=student)
    assignment = client.post(
        f"/api/v1/courses/{course['id']}/assignments",
        json={"title": "Reading", "kind": "file"},
        headers=teacher,
    ).json()
    assert assignment["submissions"] == 0

    client.post(
        f"/api/v1/courses/{course['id']}/assignments/{assignment['id']}/submissions",
        headers=student,
    )
    listed = next(
        c
        for c in client.get("/api/v1/courses", headers=teacher).json()
        if c["id"] == course["id"]
    )
    assert listed["students"] == 1 and listed["assignments"] == 1
    rows = client.get(
        f"/api/v1/courses/{course['id']}/assignments", headers=teacher
    ).json()
    assert rows[0]["submissions"] == 1 and rows[0]["graded"] == 0


def test_instance_display_enrichment(client, teacher, student):
    template = client.post(
        "/api/v1/labs/templates",
        data={
            "slug": "surfaces-lab:1.0",
            "title": "Surfaces Lab",
            "kind": "container",
            "access_mode": "no-gui",
            "ttl_minutes_default": "30",
            "ttl_minutes_max": "60",
        },
        files={"archive": ("bundle.tar.gz", b"fake-archive-bytes")},
        headers=teacher,
    ).json()
    inst = client.post(
        "/api/v1/instances", json={"template_id": template["id"]}, headers=student
    ).json()
    assert inst["template_slug"] == "surfaces-lab:1.0"
    assert inst["template_title"] == "Surfaces Lab"
    assert inst["kind"] == "container"
    assert inst["access_mode"] == "no-gui"
    assert inst["owner_handle"] == "stud1"
    # The list view carries the same enrichment.
    listed = next(
        i
        for i in client.get("/api/v1/instances", headers=student).json()
        if i["id"] == inst["id"]
    )
    assert listed["template_title"] == "Surfaces Lab"
    client.delete(f"/api/v1/instances/{inst['id']}", headers=student)


def test_admin_tenants_isos_and_providers(client, admin, student):
    # Tenant rows report live usage.
    tenants = client.get("/api/v1/admin/tenants", headers=admin).json()
    tenant = next(t for t in tenants if t["id"] == "test-tenant")
    assert "instances_active" in tenant

    # ISO library: upload then list.
    up = client.post(
        "/api/v1/admin/isos",
        files={"file": ("surfaces-test.iso", b"not-really-an-iso")},
        headers=admin,
    )
    assert up.status_code == 201
    isos = client.get("/api/v1/admin/isos", headers=admin).json()
    match = next(i for i in isos if i["key"] == "surfaces-test.iso")
    assert match["size"] == len(b"not-really-an-iso")
    assert match["last_modified"] is not None

    # Providers: the core demo provider is always active in tests.
    providers = client.get("/api/v1/admin/providers", headers=admin).json()
    demo = next(p for p in providers if p["name"] == "demo")
    assert set(demo["kinds"]) >= {"container", "vm"}

    # All three are infra:manage only.
    for path in ("/api/v1/admin/tenants", "/api/v1/admin/isos", "/api/v1/admin/providers"):
        assert client.get(path, headers=student).status_code == 403


def test_security_headers_do_not_break_the_canvas_iframe(client, student):
    """Ordinary responses refuse framing; the LTI wire endpoints cannot.

    An LTI launch renders the picker and the status pages *inside* the
    Canvas iframe, so a blanket X-Frame-Options: DENY made those pages
    blank in the LMS. They are exempted and pinned to the configured
    issuer instead of being opened up.
    """
    from palestrix.config import get_settings

    ordinary = client.get("/api/v1/sandbox/status", headers=student)
    assert ordinary.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in ordinary.headers["Content-Security-Policy"]
    assert ordinary.headers["X-Content-Type-Options"] == "nosniff"
    assert ordinary.headers["Referrer-Policy"] == "no-referrer"

    # With no platform configured, the LTI paths stay locked down too:
    # nothing should be framing them.
    lti = client.get("/api/v1/integrations/canvas/jwks")
    assert lti.headers["X-Frame-Options"] == "DENY"

    # Configure an issuer and the same path becomes framable by it alone.
    import os

    os.environ["PALESTRIX_CANVAS_ISSUER"] = "https://canvas.test"
    get_settings.cache_clear()
    try:
        lti = client.get("/api/v1/integrations/canvas/jwks")
        assert "X-Frame-Options" not in lti.headers
        csp = lti.headers["Content-Security-Policy"]
        assert "frame-ancestors https://canvas.test" in csp
    finally:
        os.environ.pop("PALESTRIX_CANVAS_ISSUER", None)
        get_settings.cache_clear()


def test_rate_limits_are_enforced_not_just_documented():
    """docs/public-api.md publishes a limit table; nothing implemented it.

    A documented control that does not exist is worse than an absent one —
    the login endpoint was taking unlimited password guesses while the
    contract said 429s were coming. The app-level limiter is per process
    and the edge proxy stays authoritative for a deployment, but this is
    the floor that holds when the API is reached directly.

    Built on its own app so the suite's shared client keeps its fixtures.
    """
    from fastapi.testclient import TestClient

    from palestrix import ratelimit
    from palestrix.config import get_settings

    os.environ["PALESTRIX_RATE_LIMIT_ENABLED"] = "1"
    os.environ["PALESTRIX_RATE_LIMIT_AUTH_PER_MINUTE"] = "3"
    get_settings.cache_clear()
    ratelimit.reset()
    try:
        from palestrix.main import create_app

        with TestClient(create_app()) as limited:
            codes = [
                limited.post(
                    "/api/v1/auth/login",
                    json={"email": "nobody@example.edu", "password": "wrong-guess-1"},
                ).status_code
                for _ in range(6)
            ]
        # The first three guesses are answered, the rest are throttled.
        assert codes[:3] == [401, 401, 401], codes
        assert codes[3:] == [429, 429, 429], codes
    finally:
        os.environ.pop("PALESTRIX_RATE_LIMIT_ENABLED", None)
        os.environ.pop("PALESTRIX_RATE_LIMIT_AUTH_PER_MINUTE", None)
        get_settings.cache_clear()
        ratelimit.reset()


def test_rate_limit_buckets_match_the_documented_table():
    """Launch and flag submission are their own buckets: each launch costs a
    real VM, and flag guessing is paced across challenges, not only within
    one (compete.py's cooldown does that)."""
    from palestrix.ratelimit import bucket_for

    api = "/api/v1"
    assert bucket_for(f"{api}/auth/login", "POST", api) == "auth"
    assert bucket_for(f"{api}/auth/token", "POST", api) == "auth"
    assert bucket_for(f"{api}/instances", "POST", api) == "launch"
    assert bucket_for(f"{api}/instances/lab-abc/extend", "POST", api) == "launch"
    assert bucket_for(f"{api}/compete/challenges/c1/submit", "POST", api) == "flag"
    # Reads of the same resources are not launches.
    assert bucket_for(f"{api}/instances", "GET", api) == "general"
    assert bucket_for(f"{api}/academy/paths", "GET", api) == "general"
    assert bucket_for("/healthz", "GET", api) == "general"

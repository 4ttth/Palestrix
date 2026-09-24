"""Phase 5: the display-enrichment fields and admin read endpoints the live
frontend surfaces render. Additive contract only — shapes existing clients
rely on are covered by the earlier test modules."""

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


def test_iso_list_merges_cluster_storage(client, admin):
    """ISOs already on the hypervisor must appear even though Palestrix's
    own bucket has never seen them — the "No ISOs stored" report on a
    cluster holding a dozen images."""
    from palestrix.providers import register_provider
    from palestrix.providers import DemoProvider

    class ClusterProvider(DemoProvider):
        def list_isos(self):
            return [
                {"key": "local:iso/debian-13.7.0-amd64-netinst.iso",
                 "size": 792723456, "ctime": 1758000000},
                # Also held by Palestrix: reported once, as "both".
                {"key": "local:iso/surfaces-test.iso", "size": 17, "ctime": None},
            ]

    client.post(
        "/api/v1/admin/isos",
        files={"file": ("surfaces-test.iso", b"not-really-an-iso")},
        headers=admin,
    )
    register_provider(ClusterProvider())
    try:
        isos = client.get("/api/v1/admin/isos", headers=admin).json()
        by_name = {i["key"].rsplit("/", 1)[-1]: i for i in isos}

        cluster_only = by_name["debian-13.7.0-amd64-netinst.iso"]
        assert cluster_only["source"] == "cluster"
        assert cluster_only["size"] == 792723456
        assert cluster_only["last_modified"] is not None

        # One entry, not two, for an ISO that lives in both places.
        assert by_name["surfaces-test.iso"]["source"] == "both"
        assert sum(
            1 for i in isos if i["key"].endswith("surfaces-test.iso")
        ) == 1
    finally:
        register_provider(DemoProvider())


def test_iso_list_survives_an_unreachable_cluster(client, admin):
    """A hypervisor that cannot answer must not blank the object-store
    list — the admin still needs to see what Palestrix holds."""
    from palestrix.providers import register_provider
    from palestrix.providers import DemoProvider

    class BrokenProvider(DemoProvider):
        def list_isos(self):
            raise RuntimeError("cluster unreachable")

    client.post(
        "/api/v1/admin/isos",
        files={"file": ("kept.iso", b"bytes")},
        headers=admin,
    )
    register_provider(BrokenProvider())
    try:
        resp = client.get("/api/v1/admin/isos", headers=admin)
        assert resp.status_code == 200
        assert any(i["key"].endswith("kept.iso") for i in resp.json())
    finally:
        register_provider(DemoProvider())


# -- remote access help (lab connection modal) ----------------------------------


def test_remote_access_route_is_not_shadowed_by_the_instance_id_route(client, student):
    """/instances/access is declared before /instances/{instance_id}. If that
    order is ever reversed, FastAPI reads "access" as an instance id and this
    returns 404 instead of the help payload."""
    resp = client.get("/api/v1/instances/access", headers=student)
    assert resp.status_code == 200, resp.text
    assert resp.json()["kind"] == "netbird"


def test_remote_access_reports_unconfigured_by_default(client, student):
    """With no overlay configured the UI must be told so, rather than being
    handed blank instructions it would render as working steps."""
    body = client.get("/api/v1/instances/access", headers=student).json()
    assert body["configured"] is False
    assert body["management_url"] == ""
    assert body["docs_url"]  # the upstream how-to is always worth linking


def test_remote_access_reflects_configuration(client, student, monkeypatch):
    from palestrix.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("PALESTRIX_NETBIRD_MANAGEMENT_URL", "https://nb.example.edu/")
    monkeypatch.setenv("PALESTRIX_NETBIRD_NETWORK_NAME", "palestrix-labs")
    try:
        body = client.get("/api/v1/instances/access", headers=student).json()
        assert body["configured"] is True
        # trailing slash trimmed so the UI can join paths without doubling it
        assert body["management_url"] == "https://nb.example.edu"
        assert body["network_name"] == "palestrix-labs"
    finally:
        get_settings.cache_clear()

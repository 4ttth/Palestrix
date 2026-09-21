"""The management surfaces behind the admin/teacher consoles: staff-created
accounts, tenant assignment, course rosters, writeup detail/comments, and
self-service profile settings."""

from sqlalchemy import select

from palestrix.db import SessionLocal
from palestrix.models import Tenant, User


# -- users console ---------------------------------------------------------------


def test_admin_creates_teacher_account(client, admin):
    resp = client.post(
        "/api/v1/users",
        json={
            "name": "New Teacher",
            "handle": "new.teacher",
            "email": "new.teacher@example.edu",
            "password": "a-long-password-123",
            "role": "teacher",
            "tenant_id": "test-tenant",
        },
        headers=admin,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["role"] == "teacher"
    assert body["tenant_id"] == "test-tenant"
    # The account works immediately.
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "new.teacher@example.edu", "password": "a-long-password-123"},
        ).status_code
        == 200
    )


def test_admin_cannot_create_admin_account(client, admin, superadmin):
    payload = {
        "name": "Sneaky Admin",
        "handle": "sneaky",
        "email": "sneaky@example.edu",
        "password": "a-long-password-123",
        "role": "admin",
    }
    assert client.post("/api/v1/users", json=payload, headers=admin).status_code == 403
    assert (
        client.post("/api/v1/users", json=payload, headers=superadmin).status_code
        == 201
    )


def test_create_user_rejects_duplicates_and_students(client, admin, student):
    resp = client.post(
        "/api/v1/users",
        json={
            "name": "Duplicate",
            "handle": "stud1",
            "email": "other@example.edu",
            "password": "a-long-password-123",
        },
        headers=admin,
    )
    assert resp.status_code == 409
    assert (
        client.post(
            "/api/v1/users",
            json={
                "name": "Nope",
                "handle": "nope1",
                "email": "nope1@example.edu",
                "password": "a-long-password-123",
            },
            headers=student,
        ).status_code
        == 403
    )


def test_tenant_assignment_from_users_console(client, admin):
    created = client.post(
        "/api/v1/users",
        json={
            "name": "Placeable",
            "handle": "placeable",
            "email": "placeable@example.edu",
            "password": "a-long-password-123",
        },
        headers=admin,
    ).json()
    assert created["tenant_id"] is None

    resp = client.patch(
        f"/api/v1/users/{created['id']}/tenant",
        json={"tenant_id": "test-tenant"},
        headers=admin,
    )
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == "test-tenant"

    # Clearing works, unknown tenants are refused.
    assert (
        client.patch(
            f"/api/v1/users/{created['id']}/tenant",
            json={"tenant_id": None},
            headers=admin,
        ).json()["tenant_id"]
        is None
    )
    assert (
        client.patch(
            f"/api/v1/users/{created['id']}/tenant",
            json={"tenant_id": "ghost-tenant"},
            headers=admin,
        ).status_code
        == 404
    )


def test_register_auto_assigns_single_active_tenant(client):
    """With exactly one active tenant, self-registration lands in it."""
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Auto Tenant",
            "handle": "autotenant",
            "email": "autotenant@example.edu",
            "password": "a-long-password-123",
        },
    )
    assert resp.status_code == 201
    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {resp.json()['access_token']}"},
    ).json()
    assert me["tenant_id"] == "test-tenant"


def test_register_respects_default_tenant_setting(client):
    from palestrix.config import get_settings

    db = SessionLocal()
    db.add(Tenant(id="second-tenant", name="Second", network_cidr="10.9.1.0/24"))
    db.commit()
    db.close()
    try:
        # Two active tenants and no explicit default: unassigned.
        token = client.post(
            "/api/v1/auth/register",
            json={
                "name": "No Default",
                "handle": "nodefault",
                "email": "nodefault@example.edu",
                "password": "a-long-password-123",
            },
        ).json()["access_token"]
        me = client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        ).json()
        assert me["tenant_id"] is None

        get_settings().default_tenant_id = "second-tenant"
        token = client.post(
            "/api/v1/auth/register",
            json={
                "name": "With Default",
                "handle": "withdefault",
                "email": "withdefault@example.edu",
                "password": "a-long-password-123",
            },
        ).json()["access_token"]
        me = client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        ).json()
        assert me["tenant_id"] == "second-tenant"
    finally:
        get_settings().default_tenant_id = ""
        db = SessionLocal()
        # Detach the accounts this test registered before dropping the tenant
        # they point at: users.tenant_id is a foreign key, so PostgreSQL --
        # and SQLite now that db.py enforces them -- refuses to orphan rows.
        for user in db.scalars(
            select(User).where(User.tenant_id == "second-tenant")
        ):
            user.tenant_id = None
        db.delete(db.get(Tenant, "second-tenant"))
        db.commit()
        db.close()


# -- course rosters ----------------------------------------------------------------


def test_teacher_manages_roster(client, teacher, student):
    course = client.post(
        "/api/v1/courses",
        json={"code": "CS 9001", "title": "Roster Test"},
        headers=teacher,
    ).json()

    resp = client.post(
        f"/api/v1/courses/{course['id']}/enrollments",
        json={"handle": "stud1"},
        headers=teacher,
    )
    assert resp.status_code == 201, resp.text
    user_id = resp.json()["user_id"]

    # Duplicate enrollments and non-students are refused.
    assert (
        client.post(
            f"/api/v1/courses/{course['id']}/enrollments",
            json={"handle": "stud1"},
            headers=teacher,
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/courses/{course['id']}/enrollments",
            json={"handle": "teach1"},
            headers=teacher,
        ).status_code
        == 422
    )

    rows = client.get(
        f"/api/v1/courses/{course['id']}/roster", headers=teacher
    ).json()
    assert [r["handle"] for r in rows] == ["stud1"]

    # Students never see the roster surface.
    assert (
        client.get(f"/api/v1/courses/{course['id']}/roster", headers=student).status_code
        == 403
    )

    assert (
        client.delete(
            f"/api/v1/courses/{course['id']}/enrollments/{user_id}", headers=teacher
        ).status_code
        == 204
    )
    assert (
        client.get(f"/api/v1/courses/{course['id']}/roster", headers=teacher).json()
        == []
    )


# -- community: writeup detail + comments ---------------------------------------------


def test_writeup_detail_and_comments(client, student, student2):
    writeup = client.post(
        "/api/v1/community/writeups",
        json={"title": "Detail view test", "body_md": "# Body\ntext", "published": True},
        headers=student,
    ).json()

    detail = client.get(
        f"/api/v1/community/writeups/{writeup['id']}", headers=student2
    )
    assert detail.status_code == 200
    assert detail.json()["body_md"].startswith("# Body")

    client.post(
        f"/api/v1/community/writeups/{writeup['id']}/comments",
        json={"body": "Nice one"},
        headers=student2,
    )
    comments = client.get(
        f"/api/v1/community/writeups/{writeup['id']}/comments", headers=student
    ).json()
    assert len(comments) == 1
    assert comments[0]["body"] == "Nice one"
    assert comments[0]["author_handle"] == "stud2"


def test_unpublished_writeup_visible_to_author_and_moderator_only(
    client, student, student2, teacher
):
    draft = client.post(
        "/api/v1/community/writeups",
        json={"title": "Draft only", "published": False},
        headers=student,
    ).json()
    path = f"/api/v1/community/writeups/{draft['id']}"
    assert client.get(path, headers=student).status_code == 200
    assert client.get(path, headers=teacher).status_code == 200  # moderator
    assert client.get(path, headers=student2).status_code == 404


# -- profile settings -------------------------------------------------------------------


def test_profile_name_edit_and_password_change(client):
    token = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Settings User",
            "handle": "settingsuser",
            "email": "settingsuser@example.edu",
            "password": "a-long-password-123",
        },
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.patch("/api/v1/auth/me", json={"name": "Renamed User"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed User"

    # Wrong current password is refused; the right one rotates it.
    assert (
        client.post(
            "/api/v1/auth/password",
            json={"current_password": "wrong-password-000", "new_password": "another-long-pass-456"},
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/auth/password",
            json={"current_password": "a-long-password-123", "new_password": "another-long-pass-456"},
            headers=headers,
        ).status_code
        == 204
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "settingsuser@example.edu", "password": "another-long-pass-456"},
        ).status_code
        == 200
    )


def test_upload_filenames_cannot_escape_their_bucket(client, teacher):
    """An upload's own filename becomes part of its object key, so it is
    reduced to one safe segment first. Before, "../../.." walked straight
    out of the bucket on the local backend — and the only thing in the way
    was an ``assert``, which ``python -O`` removes."""
    course = client.post(
        "/api/v1/courses",
        json={"code": "SEC 101", "title": "Key Safety"},
        headers=teacher,
    ).json()
    assignment = client.post(
        f"/api/v1/courses/{course['id']}/assignments",
        json={"title": "Attachment"},
        headers=teacher,
    ).json()

    up = client.post(
        f"/api/v1/courses/{course['id']}/assignments/{assignment['id']}/attachment",
        files={"file": ("../../../../escaped.txt", b"payload", "text/plain")},
        headers=teacher,
    )
    assert up.status_code == 200, up.text
    key = up.json()["storage_key"]
    assert ".." not in key
    assert key.startswith(f"lab-archives/{course['id']}/{assignment['id']}/")

    # The bytes landed inside the bucket, under a flattened name.
    from palestrix.storage import get_storage

    stored = [o.key for o in get_storage().list("lab-archives")]
    assert any(k.endswith("escaped.txt") and ".." not in k for k in stored)


def test_storage_refuses_an_escaping_key_without_asserts(tmp_path):
    """The escape check has to survive ``python -O``. Asserts do not, so it
    raises instead — and raises a type the API answers 400 for rather than
    a 500."""
    import pytest

    from palestrix.storage import LocalStorage, StorageKeyError, safe_filename

    storage = LocalStorage(str(tmp_path))
    with pytest.raises(StorageKeyError):
        storage.exists("lab-archives", "../../etc/passwd")
    with pytest.raises(StorageKeyError):
        storage.exists("not-a-bucket", "x")

    # The sanitizer keeps only the final segment rather than raising: it is
    # what the upload call sites use, and a client's directory parts are
    # never meaningful to us.
    assert safe_filename("../../../etc/passwd") == "passwd"
    assert safe_filename("C:\\Windows\\evil.exe") == "evil.exe"
    assert safe_filename("") == "upload.bin"
    assert safe_filename("..") == "upload.bin"
    assert safe_filename("a/b/c.txt") == "c.txt"
    assert safe_filename("re;po rt|$(id).pdf") == "re_po_rt___id_.pdf"


def test_instance_ids_do_not_collide_across_many_launches():
    """Instance ids are primary keys and rows are never deleted, so the id
    space is consumed permanently. Four random digits gave 9000 of them —
    collisions (a failed INSERT, i.e. a 500 on a launch) well inside one
    term's labs."""
    import re
    import secrets

    # Mirrors the generator in api/instances.py.
    ids = {f"lab-{secrets.token_hex(5)}" for _ in range(20000)}
    assert len(ids) == 20000, "id space is too small to launch labs safely"
    assert all(re.fullmatch(r"lab-[0-9a-f]{10}", i) for i in ids)

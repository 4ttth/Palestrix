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

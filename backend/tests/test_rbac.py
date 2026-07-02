"""The RBAC matrix enforced over HTTP: each capability denied and allowed
per docs/rbac-matrix.md."""


def test_student_cannot_create_course(client, student):
    resp = client.post(
        "/api/v1/courses",
        json={"code": "CS 1", "title": "Nope"},
        headers=student,
    )
    assert resp.status_code == 403


def test_teacher_creates_course_student_enrolls(client, teacher, student):
    course = client.post(
        "/api/v1/courses",
        json={"code": "CS 3712", "title": "Defensive Operations 201"},
        headers=teacher,
    ).json()

    assert (
        client.post(f"/api/v1/courses/{course['id']}/enroll", headers=student).status_code
        == 201
    )
    # Teachers do not enroll.
    assert (
        client.post(f"/api/v1/courses/{course['id']}/enroll", headers=teacher).status_code
        == 403
    )


def test_teacher_cannot_touch_other_teachers_course(client, teacher, superadmin):
    other = client.post(
        "/api/v1/courses",
        json={"code": "CS 8000", "title": "Superadmin-owned"},
        headers=superadmin,
    ).json()
    resp = client.post(
        f"/api/v1/courses/{other['id']}/assignments",
        json={"title": "Injected", "kind": "file"},
        headers=teacher,
    )
    assert resp.status_code == 403


def test_admin_console_gating(client, student, admin):
    assert client.get("/api/v1/admin/tenants", headers=student).status_code == 403
    assert client.get("/api/v1/admin/tenants", headers=admin).status_code == 200


def test_role_escalation_rules(client, admin, superadmin, student):
    users = client.get("/api/v1/users", headers=admin).json()
    stud = next(u for u in users if u["handle"] == "stud2")

    # Admin may promote a student to teacher...
    ok = client.patch(
        f"/api/v1/users/{stud['id']}/role", json={"role": "teacher"}, headers=admin
    )
    assert ok.status_code == 200

    # ...but not to admin; that needs superadmin.
    denied = client.patch(
        f"/api/v1/users/{stud['id']}/role", json={"role": "admin"}, headers=admin
    )
    assert denied.status_code == 403

    allowed = client.patch(
        f"/api/v1/users/{stud['id']}/role", json={"role": "admin"}, headers=superadmin
    )
    assert allowed.status_code == 200

    # Restore for other tests.
    client.patch(
        f"/api/v1/users/{stud['id']}/role", json={"role": "student"}, headers=superadmin
    )


def test_students_cannot_list_users(client, student):
    assert client.get("/api/v1/users", headers=student).status_code == 403

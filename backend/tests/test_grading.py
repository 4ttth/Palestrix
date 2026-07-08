"""Automated checking: diff analysis between the finished and unfinished
systems, the 100%-tally rule, randomized win files, provider-mediated
checking with partial credit, the course gradebook, and the hand-in
triggers (explicit, stop, TTL reaper)."""

import hashlib
import io
import tarfile
import uuid


def _tar_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


UNFINISHED = {
    "Dockerfile": b"FROM alpine\nCOPY etc /etc\n",
    "etc/ssh/sshd_config": b"PermitRootLogin yes\n",
    "etc/motd": b"",
    "etc/insecure-tool.conf": b"enabled\n",
    "etc/app.conf": b"unchanged\n",
}
FINISHED = {
    "Dockerfile": b"FROM alpine\nCOPY etc /etc\n",
    "etc/ssh/sshd_config": b"PermitRootLogin no\n",
    "etc/ssh/sshd_config.d/hardening.conf": b"X11Forwarding no\n",
    "etc/motd": b"Authorized use only\n",
    "etc/app.conf": b"unchanged\n",
    # insecure-tool.conf removed: students must delete it
}


def _publish_template(client, teacher, kind="container", **extra):
    slug = f"grade-lab-{uuid.uuid4().hex[:6]}:1.0"
    data = {
        "slug": slug,
        "title": "Gradable Lab",
        "kind": kind,
        "access_mode": "no-gui",
        "ttl_minutes_default": "60",
        "ttl_minutes_max": "120",
        **extra,
    }
    files = (
        {"archive": ("system.tar.gz", _tar_bytes(UNFINISHED))}
        if kind == "container"
        else None
    )
    resp = client.post("/api/v1/labs/templates", data=data, files=files, headers=teacher)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_diff_scheme(client, teacher, template_id, finished=None):
    return client.post(
        "/api/v1/grading/schemes",
        data={"lab_template_id": template_id, "kind": "diff"},
        files={"finished": ("finished.tar.gz", finished or _tar_bytes(FINISHED))},
        headers=teacher,
    )


def _weights_by_key(scheme, mapping):
    return {
        item["id"]: mapping[item["key"]]
        for item in scheme["items"]
        if item["key"] in mapping
    }


def _course_with_lab(client, teacher, student, template_id):
    course = client.post(
        "/api/v1/courses",
        json={"code": "GRD 101", "title": "Hardening", "section": "T"},
        headers=teacher,
    ).json()
    assignment = client.post(
        f"/api/v1/courses/{course['id']}/assignments",
        json={"title": "Harden the box", "kind": "lab", "lab_template_id": template_id},
        headers=teacher,
    ).json()
    enrolled = client.post(
        f"/api/v1/courses/{course['id']}/enroll", headers=student
    )
    assert enrolled.status_code == 201, enrolled.text
    return course, assignment


# -- diff analysis -------------------------------------------------------------------


def test_diff_analysis_groups_differences(client, teacher):
    template = _publish_template(client, teacher)

    # Identical systems: nothing to grade, and the failed attempt leaves no
    # half-created scheme behind.
    same = _create_diff_scheme(client, teacher, template["id"], _tar_bytes(UNFINISHED))
    assert same.status_code == 422
    assert "identical" in same.json()["detail"]

    resp = _create_diff_scheme(client, teacher, template["id"])
    assert resp.status_code == 201, resp.text
    scheme = resp.json()
    assert scheme["status"] == "draft"
    assert scheme["analysis"]["differences"] == 4  # 2 ssh, 1 motd, 1 removal

    by_key = {item["key"]: item for item in scheme["items"]}
    assert set(by_key) == {"ssh", "motd", "file-insecure-tool-conf"}
    assert by_key["ssh"]["title"] == "SSH configuration"
    assert sorted(by_key["ssh"]["paths"]) == [
        "/etc/ssh/sshd_config",
        "/etc/ssh/sshd_config.d/hardening.conf",
    ]
    # The Dockerfile is build context, never a gradeable difference.
    assert all("Dockerfile" not in p for item in scheme["items"] for p in item["paths"])
    assert all(item["weight_percent"] == 0 for item in scheme["items"])

    # One scheme per template.
    dup = _create_diff_scheme(client, teacher, template["id"])
    assert dup.status_code == 409


def test_weights_must_tally_to_100(client, teacher):
    template = _publish_template(client, teacher)
    scheme = _create_diff_scheme(client, teacher, template["id"]).json()

    # Publishing before the rubric tallies is refused, and names the total.
    premature = client.post(
        f"/api/v1/grading/schemes/{scheme['id']}/publish", headers=teacher
    )
    assert premature.status_code == 422
    assert premature.json()["detail"]["total"] == 0

    weights = _weights_by_key(scheme, {"ssh": 50, "motd": 30, "file-insecure-tool-conf": 10})
    resp = client.patch(
        f"/api/v1/grading/schemes/{scheme['id']}/weights",
        json={"weights": weights},
        headers=teacher,
    )
    assert resp.status_code == 200
    short = client.post(
        f"/api/v1/grading/schemes/{scheme['id']}/publish", headers=teacher
    )
    assert short.status_code == 422 and short.json()["detail"]["total"] == 90

    weights = _weights_by_key(scheme, {"ssh": 50, "motd": 30, "file-insecure-tool-conf": 20})
    client.patch(
        f"/api/v1/grading/schemes/{scheme['id']}/weights",
        json={"weights": weights},
        headers=teacher,
    )
    published = client.post(
        f"/api/v1/grading/schemes/{scheme['id']}/publish", headers=teacher
    )
    assert published.status_code == 200
    assert published.json()["status"] == "published"

    # Published schemes are locked: no weight edits, no delete.
    locked = client.patch(
        f"/api/v1/grading/schemes/{scheme['id']}/weights",
        json={"weights": weights},
        headers=teacher,
    )
    assert locked.status_code == 409
    assert (
        client.delete(f"/api/v1/grading/schemes/{scheme['id']}", headers=teacher).status_code
        == 409
    )


def test_scheme_rbac(client, teacher, student):
    template = _publish_template(client, teacher)
    denied = client.post(
        "/api/v1/grading/schemes",
        data={"lab_template_id": template["id"], "kind": "winfile"},
        headers=student,
    )
    assert denied.status_code == 403
    assert client.get("/api/v1/grading/schemes", headers=student).status_code == 403


# -- win files -----------------------------------------------------------------------


def test_winfiles_randomized_and_locked_at_100(client, teacher, student):
    template = _publish_template(client, teacher)
    resp = client.post(
        "/api/v1/grading/schemes",
        data={"lab_template_id": template["id"], "kind": "winfile", "winfiles": "2"},
        headers=teacher,
    )
    assert resp.status_code == 201, resp.text
    scheme = resp.json()
    assert [i["key"] for i in scheme["items"]] == ["win-1", "win-2"]
    assert all(i["win_filename"] for i in scheme["items"])

    def download(item):
        r = client.get(
            f"/api/v1/grading/schemes/{scheme['id']}/winfiles/{item['id']}",
            headers=teacher,
        )
        assert r.status_code == 200
        return r.text

    first_gen = [download(i) for i in scheme["items"]]
    assert all("printf" in body and "#!/bin/sh" in body for body in first_gen)
    assert first_gen[0] != first_gen[1]  # every script has its own token

    # Students never see the scripts or the scheme.
    denied = client.get(
        f"/api/v1/grading/schemes/{scheme['id']}/winfiles/{scheme['items'][0]['id']}",
        headers=student,
    )
    assert denied.status_code == 403

    # Regeneration re-randomizes: fresh tokens, fresh filenames.
    regen = client.post(
        f"/api/v1/grading/schemes/{scheme['id']}/regenerate",
        data={"winfiles": "2"},
        headers=teacher,
    )
    assert regen.status_code == 200
    regenerated = regen.json()
    second_gen = [download(i) for i in regenerated["items"]]
    assert set(second_gen).isdisjoint(set(first_gen))

    weights = {item["id"]: 60 if item["key"] == "win-1" else 40 for item in regenerated["items"]}
    client.patch(
        f"/api/v1/grading/schemes/{scheme['id']}/weights",
        json={"weights": weights},
        headers=teacher,
    )
    assert (
        client.post(f"/api/v1/grading/schemes/{scheme['id']}/publish", headers=teacher).status_code
        == 200
    )


def test_winfile_scheme_on_vm_template(client, teacher):
    template = _publish_template(client, teacher, kind="vm", vm_template="golden-tpl")
    diff = _create_diff_scheme(client, teacher, template["id"])
    assert diff.status_code == 422  # diff mode needs a container archive
    win = client.post(
        "/api/v1/grading/schemes",
        data={"lab_template_id": template["id"], "kind": "winfile", "winfiles": "1"},
        headers=teacher,
    )
    assert win.status_code == 201


# -- checking a live instance --------------------------------------------------------


class GradedFakeProvider:
    """A container provider whose filesystem the test controls: read_files
    answers from ``filesystem`` (path -> bytes), like a student's box."""

    name = "graded-fake"
    kinds = ("container",)
    filesystem: dict[str, bytes] = {}

    def provision(self, db, instance, template):
        from palestrix.models import InstanceState
        from palestrix.providers import add_log

        instance.node, instance.host, instance.port, instance.proto = (
            "fake-01", "10.0.0.9", 42022, "ssh",
        )
        instance.state = InstanceState.running
        add_log(db, instance.id, "instance running (graded fake)", level="ok")

    def stop(self, db, instance):
        pass

    def destroy(self, db, instance):
        pass

    def read_files(self, db, instance, paths):
        return {
            p: hashlib.sha256(self.filesystem[p]).hexdigest()
            if p in self.filesystem
            else None
            for p in paths
        }


def _restore_demo_provider():
    from palestrix.providers import DemoProvider, register_provider

    register_provider(DemoProvider())


def test_partial_credit_end_to_end(client, teacher, student, student2):
    from palestrix.providers import register_provider

    template = _publish_template(client, teacher)
    scheme = _create_diff_scheme(client, teacher, template["id"]).json()
    weights = _weights_by_key(scheme, {"ssh": 50, "motd": 30, "file-insecure-tool-conf": 20})
    client.patch(
        f"/api/v1/grading/schemes/{scheme['id']}/weights",
        json={"weights": weights},
        headers=teacher,
    )
    client.post(f"/api/v1/grading/schemes/{scheme['id']}/publish", headers=teacher)
    course, assignment = _course_with_lab(client, teacher, student, template["id"])

    # The student's box: SSH fully fixed, MOTD untouched, insecure tool
    # still present -> only the ssh objective (50%) passes.
    GradedFakeProvider.filesystem = {
        "/etc/ssh/sshd_config": FINISHED["etc/ssh/sshd_config"],
        "/etc/ssh/sshd_config.d/hardening.conf": FINISHED[
            "etc/ssh/sshd_config.d/hardening.conf"
        ],
        "/etc/motd": UNFINISHED["etc/motd"],
        "/etc/insecure-tool.conf": UNFINISHED["etc/insecure-tool.conf"],
    }
    register_provider(GradedFakeProvider())
    try:
        inst = client.post(
            "/api/v1/instances", json={"template_id": template["id"]}, headers=student
        ).json()
        assert inst["state"] == "running"

        # Another student cannot hand in someone else's box.
        assert (
            client.post(f"/api/v1/instances/{inst['id']}/grade", headers=student2).status_code
            == 403
        )

        result = client.post(f"/api/v1/instances/{inst['id']}/grade", headers=student)
        assert result.status_code == 200, result.text
        body = result.json()
        assert body["total_percent"] == 50
        passed = {i["key"]: i["passed"] for i in body["items"]}
        assert passed == {"ssh": True, "motd": False, "file-insecure-tool-conf": False}

        # The student's rubric view: titles and weights, never the answers.
        view = client.get(f"/api/v1/instances/{inst['id']}/grading", headers=student).json()
        assert view["scheme_kind"] == "diff"
        assert {r["key"] for r in view["rubric"]} == set(passed)
        assert all(set(r) == {"key", "title", "weight_percent"} for r in view["rubric"])
        assert view["result"]["total_percent"] == 50

        # The grade landed in the course gradebook with the breakdown.
        book = client.get(
            f"/api/v1/courses/{course['id']}/assignments/{assignment['id']}/submissions",
            headers=teacher,
        )
        assert book.status_code == 200
        rows = book.json()
        assert len(rows) == 1 and rows[0]["grade"] == 50
        assert rows[0]["auto"]["trigger"] == "student"

        # Students cannot read the gradebook.
        assert (
            client.get(
                f"/api/v1/courses/{course['id']}/assignments/{assignment['id']}/submissions",
                headers=student,
            ).status_code
            == 403
        )

        # The student fixes the MOTD and hands in again: 50 -> 80.
        GradedFakeProvider.filesystem["/etc/motd"] = FINISHED["etc/motd"]
        again = client.post(f"/api/v1/instances/{inst['id']}/grade", headers=student)
        assert again.json()["total_percent"] == 80
        rows = client.get(
            f"/api/v1/courses/{course['id']}/assignments/{assignment['id']}/submissions",
            headers=teacher,
        ).json()
        assert rows[0]["grade"] == 80

        client.delete(f"/api/v1/instances/{inst['id']}", headers=student)
    finally:
        _restore_demo_provider()


def test_ungraded_template_hand_in_is_409(client, teacher, student):
    template = _publish_template(client, teacher)
    inst = client.post(
        "/api/v1/instances", json={"template_id": template["id"]}, headers=student
    ).json()
    resp = client.post(f"/api/v1/instances/{inst['id']}/grade", headers=student)
    assert resp.status_code == 409
    client.delete(f"/api/v1/instances/{inst['id']}", headers=student)


def test_stop_grades_first(client, teacher, student):
    """Stopping a graded lab is a hand-in: the check runs while the box is
    still up. On the demo provider every path honestly reads absent -> 0%."""
    template = _publish_template(client, teacher)
    scheme = _create_diff_scheme(client, teacher, template["id"]).json()
    weights = _weights_by_key(scheme, {"ssh": 60, "motd": 20, "file-insecure-tool-conf": 20})
    client.patch(
        f"/api/v1/grading/schemes/{scheme['id']}/weights",
        json={"weights": weights},
        headers=teacher,
    )
    client.post(f"/api/v1/grading/schemes/{scheme['id']}/publish", headers=teacher)
    _course_with_lab(client, teacher, student, template["id"])

    inst = client.post(
        "/api/v1/instances", json={"template_id": template["id"]}, headers=student
    ).json()
    stopped = client.post(f"/api/v1/instances/{inst['id']}/stop", headers=student)
    assert stopped.status_code == 200

    view = client.get(f"/api/v1/instances/{inst['id']}/grading", headers=student).json()
    assert view["result"] is not None
    assert view["result"]["trigger"] == "stop"
    # Demo box reads all-absent: the two configure objectives fail, but the
    # "remove the insecure file" objective is genuinely satisfied by absence.
    assert view["result"]["total_percent"] == 20
    passed = {i["key"]: i["passed"] for i in view["result"]["items"]}
    assert passed == {"ssh": False, "motd": False, "file-insecure-tool-conf": True}
    client.delete(f"/api/v1/instances/{inst['id']}", headers=student)


def test_reaper_grades_expired_instances(client, teacher, student, admin):
    """Time up is a hand-in: the reaper grades before it destroys, and the
    grade reaches the gradebook with trigger=reaper."""
    template = _publish_template(client, teacher)
    scheme = _create_diff_scheme(client, teacher, template["id"]).json()
    weights = _weights_by_key(scheme, {"ssh": 100, "motd": 0, "file-insecure-tool-conf": 0})
    client.patch(
        f"/api/v1/grading/schemes/{scheme['id']}/weights",
        json={"weights": weights},
        headers=teacher,
    )
    client.post(f"/api/v1/grading/schemes/{scheme['id']}/publish", headers=teacher)
    course, assignment = _course_with_lab(client, teacher, student, template["id"])

    inst = client.post(
        "/api/v1/instances", json={"template_id": template["id"]}, headers=student
    ).json()

    from datetime import datetime, timedelta, timezone

    from palestrix.db import SessionLocal
    from palestrix.models import Instance

    db = SessionLocal()
    row = db.get(Instance, inst["id"])
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    db.close()

    reaped = client.post("/api/v1/admin/reaper/run", headers=admin).json()
    assert inst["id"] in reaped["reaped"]

    view = client.get(f"/api/v1/instances/{inst['id']}/grading", headers=student).json()
    assert view["result"]["trigger"] == "reaper"
    rows = client.get(
        f"/api/v1/courses/{course['id']}/assignments/{assignment['id']}/submissions",
        headers=teacher,
    ).json()
    assert rows and rows[0]["grade"] == 0  # demo provider: honest absent reads
    assert rows[0]["auto"]["trigger"] == "reaper"

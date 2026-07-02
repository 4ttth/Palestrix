"""CTF flow: authoring, flag submission, first blood, cooldown, ledger,
leaderboard, and the instance lifecycle with quotas."""

from datetime import datetime, timedelta, timezone


def _make_event(client, teacher):
    now = datetime.now(timezone.utc)
    event = client.post(
        "/api/v1/compete/events",
        json={
            "title": "Test Round",
            "starts_at": (now - timedelta(hours=1)).isoformat(),
            "ends_at": (now + timedelta(hours=4)).isoformat(),
        },
        headers=teacher,
    ).json()
    challenge = client.post(
        f"/api/v1/compete/events/{event['id']}/challenges",
        json={
            "title": "Warmup",
            "category": "Web",
            "points": 100,
            "flag": "CLCTF{warmup}",
            "palestras_award": 50,
        },
        headers=teacher,
    ).json()
    return event, challenge


def test_flag_flow_first_blood_and_cooldown(client, teacher, student, student2):
    event, challenge = _make_event(client, teacher)
    cid = challenge["id"]

    # Teacher may not submit flags.
    assert (
        client.post(
            f"/api/v1/compete/challenges/{cid}/submit",
            json={"flag": "CLCTF{warmup}"},
            headers=teacher,
        ).status_code
        == 403
    )

    # Wrong flag, then immediate retry: cooldown.
    wrong = client.post(
        f"/api/v1/compete/challenges/{cid}/submit",
        json={"flag": "CLCTF{nope}"},
        headers=student,
    )
    assert wrong.status_code == 200 and wrong.json()["correct"] is False
    retry = client.post(
        f"/api/v1/compete/challenges/{cid}/submit",
        json={"flag": "CLCTF{warmup}"},
        headers=student,
    )
    assert retry.status_code == 429

    # student2 takes first blood meanwhile.
    fb = client.post(
        f"/api/v1/compete/challenges/{cid}/submit",
        json={"flag": "CLCTF{warmup}"},
        headers=student2,
    ).json()
    assert fb["correct"] is True
    assert fb["first_blood"] is True
    assert fb["palestras"] == 75  # 50 award + 25 first-blood bonus

    # Palestras hit the ledger.
    bal = client.get("/api/v1/gamification/balance", headers=student2).json()
    assert bal["palestras"] >= 75

    # Duplicate solve is rejected.
    dup = client.post(
        f"/api/v1/compete/challenges/{cid}/submit",
        json={"flag": "CLCTF{warmup}"},
        headers=student2,
    )
    assert dup.status_code == 409

    # Board reflects the solve and first blood.
    board = client.get(
        f"/api/v1/compete/events/{event['id']}/challenges", headers=student
    ).json()
    row = next(c for c in board if c["id"] == cid)
    assert row["solves"] == 1
    assert row["first_blood"] == "stud2"

    lb = client.get(
        f"/api/v1/compete/events/{event['id']}/leaderboard", headers=student
    ).json()
    assert lb[0]["handle"] == "stud2"
    assert lb[0]["score"] == 100
    assert lb[0]["first_bloods"] == 1


def test_instance_lifecycle_and_quota(client, teacher, student):
    # Teacher publishes a container lab with an archive.
    resp = client.post(
        "/api/v1/labs/templates",
        data={
            "slug": "quota-lab:1.0",
            "title": "Quota Lab",
            "kind": "container",
            "access_mode": "no-gui",
            "ttl_minutes_default": "60",
            "ttl_minutes_max": "120",
        },
        files={"archive": ("bundle.tar.gz", b"fake-archive-bytes")},
        headers=teacher,
    )
    assert resp.status_code == 201, resp.text
    template = resp.json()

    # Student launches: demo provider runs it immediately, logs exist.
    inst = client.post(
        "/api/v1/instances",
        json={"template_id": template["id"]},
        headers=student,
    )
    assert inst.status_code == 201, inst.text
    body = inst.json()
    assert body["state"] == "running"
    assert body["port"] > 0
    logs = client.get(f"/api/v1/instances/{body['id']}/logs", headers=student).json()
    assert any("running" in line["msg"] for line in logs)

    # Tenant quota is 2 (conftest): a second runs, a third is denied.
    second = client.post(
        "/api/v1/instances", json={"template_id": template["id"]}, headers=student
    )
    assert second.status_code == 201
    third = client.post(
        "/api/v1/instances", json={"template_id": template["id"]}, headers=student
    )
    assert third.status_code == 409
    assert third.json()["detail"]["error"] == "quota_exceeded"

    # Destroy releases quota.
    gone = client.delete(f"/api/v1/instances/{body['id']}", headers=student)
    assert gone.status_code == 202 and gone.json()["state"] == "expired"
    fourth = client.post(
        "/api/v1/instances", json={"template_id": template["id"]}, headers=student
    )
    assert fourth.status_code == 201

    # Cleanup for other tests.
    for row in client.get("/api/v1/instances", headers=student).json():
        if row["state"] == "running":
            client.delete(f"/api/v1/instances/{row['id']}", headers=student)


def test_extend_requires_palestras(client, student):
    instances = client.get("/api/v1/instances", headers=student).json()
    # Relaunch one if none are running.
    running = [i for i in instances if i["state"] == "running"]
    if not running:
        template = client.get("/api/v1/labs/templates", headers=student).json()[0]
        running = [
            client.post(
                "/api/v1/instances",
                json={"template_id": template["id"]},
                headers=student,
            ).json()
        ]
    iid = running[0]["id"]
    resp = client.post(
        f"/api/v1/instances/{iid}/extend", json={"minutes": 30}, headers=student
    )
    # stud1 has no earnings yet: the spend must be refused, not silently granted.
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "insufficient_palestras"
    client.delete(f"/api/v1/instances/{iid}", headers=student)

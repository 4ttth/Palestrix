"""Phase 3 gamification rules: solve-count-scaled flag awards, the first-blood
bonus as its own auditable ledger line, writeup earning under the staff
no-earn rule, per-source daily caps, streak accrual with the weekly
checkpoint, community score on public profiles, and the global leaderboards.

Rules that need many actors or synthetic calendar days use throwaway
registered students (kept out of the shared fixtures so balances stay
hermetic); the streak calendar is driven straight through the service."""

import uuid
from datetime import datetime, timedelta, timezone


def _register(client, handle):
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "name": f"User {handle}",
            "handle": handle,
            "email": f"{handle}@example.edu",
            "password": "throwaway-pass-123!",
        },
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _running_challenge(client, teacher, *, award=100, points=100):
    now = datetime.now(timezone.utc)
    event = client.post(
        "/api/v1/compete/events",
        json={
            "title": "Scoring Round",
            "starts_at": (now - timedelta(hours=1)).isoformat(),
            "ends_at": (now + timedelta(hours=2)).isoformat(),
        },
        headers=teacher,
    ).json()
    flag = f"CLCTF{{{uuid.uuid4().hex[:8]}}}"
    challenge = client.post(
        f"/api/v1/compete/events/{event['id']}/challenges",
        json={
            "title": "Scaler",
            "category": "Misc",
            "points": points,
            "flag": flag,
            "palestras_award": award,
        },
        headers=teacher,
    ).json()
    return event, challenge, flag


def _balance(client, headers):
    return client.get("/api/v1/gamification/balance", headers=headers).json()["palestras"]


def test_flag_award_scales_with_solves_and_first_blood(client, teacher):
    _, challenge, flag = _running_challenge(client, teacher, award=100)
    cid = challenge["id"]

    solvers = []
    for _ in range(3):
        headers = _register(client, f"solver_{uuid.uuid4().hex[:6]}")
        result = client.post(
            f"/api/v1/compete/challenges/{cid}/submit",
            json={"flag": flag},
            headers=headers,
        )
        assert result.status_code == 200
        solvers.append((headers, result.json()))

    (h1, r1), (_, r2), (_, r3) = solvers
    # First solver: full base + first-blood bonus. Later solvers earn a base
    # that decays by 8% per prior solve (dynamic scoring), no bonus.
    assert r1["first_blood"] is True and r2["first_blood"] is False
    assert r1["palestras"] == 125  # 100 base + 25 first blood
    assert r2["palestras"] == 92  # round(100 * 0.92)
    assert r3["palestras"] == 84  # round(100 * 0.84)

    # The first-blood bonus is its own ledger entry, separate from the capture.
    ledger1 = client.get("/api/v1/gamification/ledger", headers=h1).json()
    by_reason = {e["reason"]: e["delta"] for e in ledger1}
    assert by_reason["flag.captured"] == 100
    assert by_reason["first_blood.bonus"] == 25


def test_writeup_publication_earns_students_only(client, teacher):
    student = _register(client, f"writer_{uuid.uuid4().hex[:6]}")
    before = _balance(client, student)
    published = client.post(
        "/api/v1/community/writeups",
        json={"title": "A writeup on XOR pads", "published": True},
        headers=student,
    )
    assert published.status_code == 201
    after = _balance(client, student)
    assert after - before == 60  # writeup_publish_award_palestras default

    # A draft earns nothing until it is published.
    draft = client.post(
        "/api/v1/community/writeups",
        json={"title": "Draft, not yet public", "published": False},
        headers=student,
    )
    assert draft.status_code == 201
    assert _balance(client, student) == after

    # Teachers may publish but have no earn path (leaderboards stay student-only).
    teacher_before = _balance(client, teacher)
    tpub = client.post(
        "/api/v1/community/writeups",
        json={"title": "Teacher shares a technique", "published": True},
        headers=teacher,
    )
    assert tpub.status_code == 201
    assert _balance(client, teacher) == teacher_before


def test_module_earn_respects_daily_cap(client):
    from palestrix.db import SessionLocal
    from palestrix.models import Module, Path

    db = SessionLocal()
    try:
        path = Path(slug=f"cap-{uuid.uuid4().hex[:6]}", title="Cap Path", hours=1)
        db.add(path)
        db.flush()
        module_ids = []
        for i in range(6):
            module = Module(
                path_id=path.id, title=f"M{i}", position=i, palestras_award=100
            )
            db.add(module)
            db.flush()
            module_ids.append(module.id)
        db.commit()
    finally:
        db.close()

    student = _register(client, f"grinder_{uuid.uuid4().hex[:6]}")
    awarded = []
    for module_id in module_ids:
        resp = client.post(
            f"/api/v1/academy/modules/{module_id}/complete", headers=student
        )
        assert resp.status_code == 201
        awarded.append(resp.json()["palestras_awarded"])

    # The module source caps at 500/day: five completions pay 100, the sixth 0.
    assert sum(awarded) == 500
    assert awarded[-1] == 0
    assert _balance(client, student) == 500


def test_streak_accrual_weekly_checkpoint_and_reset():
    from palestrix import gamification as g
    from palestrix.db import SessionLocal
    from palestrix.events import _plugin_queue
    from palestrix.models import Role, Streak, User

    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex[:6]
        user = User(
            handle=f"streaker_{suffix}",
            name="Streaker",
            email=f"streaker_{suffix}@example.edu",
            role=Role.student,
        )
        db.add(user)
        db.commit()
        uid = user.id
        base = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)

        for day in range(6):  # six consecutive days, no checkpoint yet
            g.touch_streak(db, uid, Role.student, when=base + timedelta(days=day))
        db.commit()
        assert db.get(Streak, uid).current_days == 6
        assert g.balance(db, uid) == 0

        # A second action the same day does not advance the streak.
        g.touch_streak(db, uid, Role.student, when=base + timedelta(days=5, hours=6))
        db.commit()
        assert db.get(Streak, uid).current_days == 6

        # The seventh consecutive day pays the weekly checkpoint.
        g.touch_streak(db, uid, Role.student, when=base + timedelta(days=6))
        db.commit()
        streak = db.get(Streak, uid)
        assert streak.current_days == 7 and streak.weeks_paid == 1
        assert g.balance(db, uid) == 100  # streak_weekly_bonus_palestras default

        # A gap of more than a day resets the streak and the paid-week counter,
        # but leaves the longest-streak record and the already-earned bonus.
        g.touch_streak(db, uid, Role.student, when=base + timedelta(days=10))
        db.commit()
        streak = db.get(Streak, uid)
        assert streak.current_days == 1 and streak.weeks_paid == 0
        assert streak.longest_days == 7
        assert g.balance(db, uid) == 100
    finally:
        _plugin_queue.clear()  # these bypass the app; don't leak plugin events
        db.close()


def test_leaderboard_and_summary_are_student_only(client, teacher, admin):
    handle = f"climber_{uuid.uuid4().hex[:6]}"
    student = _register(client, handle)
    assert (
        client.post(
            "/api/v1/community/writeups",
            json={"title": "Climbing the ranks writeup", "published": True},
            headers=student,
        ).status_code
        == 201
    )

    summary = client.get("/api/v1/gamification/summary", headers=student).json()
    assert summary["handle"] == handle
    assert summary["lifetime_earned"] >= 60
    assert summary["rank"] is not None

    board = client.get("/api/v1/gamification/leaderboard", headers=student).json()
    handles = {row["handle"] for row in board}
    assert handle in handles
    assert "teach1" not in handles and "admin1" not in handles
    assert [row["rank"] for row in board] == list(range(1, len(board) + 1))

    # Staff have no earn path, so no rank.
    assert client.get("/api/v1/gamification/summary", headers=teacher).json()["rank"] is None
    assert client.get("/api/v1/gamification/summary", headers=admin).json()["rank"] is None

    community = client.get(
        "/api/v1/gamification/leaderboard?board=community", headers=student
    ).json()
    assert any(row["handle"] == handle for row in community)


def test_public_profile_reports_community_score(client, student2):
    handle = f"cauthor_{uuid.uuid4().hex[:6]}"
    author = _register(client, handle)
    writeup = client.post(
        "/api/v1/community/writeups",
        json={"title": "Community score sample writeup", "published": True},
        headers=author,
    ).json()

    before = client.get(f"/api/v1/users/{handle}", headers=student2).json()
    assert before["community_score"] >= 10  # base points for a fresh writeup

    voted = client.post(
        f"/api/v1/community/writeups/{writeup['id']}/vote?value=1", headers=student2
    )
    assert voted.status_code == 200
    after = client.get(f"/api/v1/users/{handle}", headers=student2).json()
    assert after["community_score"] > before["community_score"]

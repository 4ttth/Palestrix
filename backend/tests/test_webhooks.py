"""Webhook subscriptions, event fan-out, and HMAC signatures. Deliveries
are attempted against a loopback URL with nothing listening, so rows exist
and end 'failed' without external network dependencies; the signature is
verified locally. Reaching loopback at all requires the private-target
escape hatch, which is what ``private_webhooks`` turns on -- the default
posture is covered by test_webhook_targets_are_ssrf_guarded."""

import hashlib
import hmac
import json

import pytest


@pytest.fixture()
def private_webhooks(monkeypatch):
    """Permit non-public delivery targets for one test.

    The guard resolves the host on every attempt, so a test that wants a
    real (failing) delivery has to opt in exactly as an operator with an
    internal collector would.
    """
    from palestrix.config import get_settings

    monkeypatch.setenv("PALESTRIX_ALLOW_PRIVATE_WEBHOOKS", "1")
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("PALESTRIX_ALLOW_PRIVATE_WEBHOOKS", raising=False)
    get_settings.cache_clear()


def test_webhook_targets_are_ssrf_guarded(client, student):
    """A subscription is a URL the platform will fetch on the subscriber's
    behalf, and webhooks:manage is granted to every role -- so the default
    refuses everything the internet cannot route to. Without this, any
    student turns the API into a probe of the lab network, the hypervisor
    API, and the cloud metadata service."""
    for url in (
        "http://127.0.0.1:8080/hook",                 # the API's own host
        "http://169.254.169.254/latest/meta-data/",   # cloud metadata
        "http://10.24.7.5/hook",                      # a tenant lab network
        "http://192.168.3.6:8080/hook",               # the hypervisor's LAN
        "http://[::1]:8080/hook",                     # loopback over IPv6
    ):
        refused = client.post(
            "/api/v1/webhooks",
            json={"url": url, "events": ["flag.captured"]},
            headers=student,
        )
        assert refused.status_code == 422, f"{url} was accepted"

    # Ports that are not webhook ports are refused too: without this the
    # subscription list doubles as a port scanner.
    odd_port = client.post(
        "/api/v1/webhooks",
        json={"url": "https://example.edu:2222/hook", "events": ["flag.captured"]},
        headers=student,
    )
    assert odd_port.status_code == 422


def test_subscribe_validate_and_sign(
    client, student, teacher, student2, private_webhooks
):
    # Unknown event types are rejected.
    bad = client.post(
        "/api/v1/webhooks",
        json={"url": "http://127.0.0.1:8080/hook", "events": ["nope.event"]},
        headers=student,
    )
    assert bad.status_code == 422

    sub = client.post(
        "/api/v1/webhooks",
        json={
            "url": "http://127.0.0.1:8080/hook",  # loopback, nothing listening
            "events": ["flag.captured", "palestras.changed"],
        },
        headers=student,
    )
    assert sub.status_code == 201
    body = sub.json()
    secret = body["secret"]
    assert len(secret) == 48

    # The secret is shown exactly once: the list view omits it.
    listed = client.get("/api/v1/webhooks", headers=student).json()
    assert all("secret" not in row for row in listed)

    # Fire a matching event through the real flow: a flag capture.
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    event = client.post(
        "/api/v1/compete/events",
        json={
            "title": "Hook Round",
            "starts_at": (now - timedelta(hours=1)).isoformat(),
            "ends_at": (now + timedelta(hours=1)).isoformat(),
        },
        headers=teacher,
    ).json()
    challenge = client.post(
        f"/api/v1/compete/events/{event['id']}/challenges",
        json={
            "title": "Hooked",
            "category": "Misc",
            "points": 10,
            "flag": "CLCTF{hooked}",
            "palestras_award": 5,
        },
        headers=teacher,
    ).json()
    solve = client.post(
        f"/api/v1/compete/challenges/{challenge['id']}/submit",
        json={"flag": "CLCTF{hooked}"},
        headers=student2,
    )
    assert solve.status_code == 200 and solve.json()["correct"]

    deliveries = client.get(
        f"/api/v1/webhooks/{body['id']}/deliveries", headers=student
    ).json()
    assert any(d["event_type"] == "flag.captured" for d in deliveries)
    # The unroutable URL means the attempt was made and failed cleanly.
    assert all(d["status"] in ("failed", "pending") for d in deliveries)

    # Verify the recorded signature matches HMAC-SHA256(secret, body).
    from palestrix.db import SessionLocal
    from palestrix.models import WebhookDelivery
    from sqlalchemy import select

    db = SessionLocal()
    try:
        row = db.scalars(
            select(WebhookDelivery).where(
                WebhookDelivery.event_type == "flag.captured"
            )
        ).first()
        raw = json.dumps(row.payload, separators=(",", ":")).encode()
        expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        assert row.signature == expected
    finally:
        db.close()

    # Unsubscribe deactivates.
    assert (
        client.delete(f"/api/v1/webhooks/{body['id']}", headers=student).status_code
        == 204
    )


def test_academy_completion_posts_ledger(client, teacher, student):
    # Academy content comes from seeds normally; create via direct DB here.
    from palestrix.db import SessionLocal
    from palestrix.models import Module, Path

    db = SessionLocal()
    try:
        path = Path(slug="test-path", title="Test Path", hours=2)
        db.add(path)
        db.flush()
        module = Module(
            path_id=path.id, title="Only Module", position=0, palestras_award=40
        )
        db.add(module)
        db.commit()
        module_id = module.id
    finally:
        db.close()

    before = client.get("/api/v1/gamification/balance", headers=student).json()[
        "palestras"
    ]
    done = client.post(f"/api/v1/academy/modules/{module_id}/complete", headers=student)
    assert done.status_code == 201
    after = client.get("/api/v1/gamification/balance", headers=student).json()[
        "palestras"
    ]
    assert after - before == 40

    # Idempotence: completing twice is a conflict, not double pay.
    again = client.post(
        f"/api/v1/academy/modules/{module_id}/complete", headers=student
    )
    assert again.status_code == 409

    # Teachers have no earn path.
    denied = client.post(
        f"/api/v1/academy/modules/{module_id}/complete", headers=teacher
    )
    assert denied.status_code == 403

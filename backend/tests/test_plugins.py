"""Plugin framework: discovery, enablement, capability scoping, config
encryption, the echo provider end to end, crash isolation, and the
contract version gate."""

import pytest


def _plugin(client, superadmin, plugin_id):
    rows = client.get("/api/v1/plugins", headers=superadmin).json()
    return next(p for p in rows if p["id"] == plugin_id)


def test_discovery_and_gating(client, superadmin, student):
    # Students never see the plugin console.
    assert client.get("/api/v1/plugins", headers=student).status_code == 403

    rows = client.get("/api/v1/plugins", headers=superadmin).json()
    ids = {p["id"] for p in rows}
    # Entry-point discovery (installed package) and path discovery (fixtures).
    assert {"provider-demo", "crashy", "needy", "oldapi"} <= ids

    demo = _plugin(client, superadmin, "provider-demo")
    assert demo["source"] == "entry-point"
    assert demo["scopes"] == ["instances:read"]
    assert demo["state"] == "discovered"


def test_unsupported_contract_version(client, superadmin):
    old = _plugin(client, superadmin, "oldapi")
    assert old["state"] == "unsupported"
    resp = client.post(
        "/api/v1/plugins/oldapi/enable", json={"config": {}}, headers=superadmin
    )
    assert resp.status_code == 409


def test_enable_provider_demo_and_scoped_api(client, superadmin):
    resp = client.post(
        "/api/v1/plugins/provider-demo/enable",
        json={"config": {"banner": "ci run"}},
        headers=superadmin,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "enabled"
    assert resp.json()["granted_scopes"] == ["instances:read"]

    # The plugin's service principal is truly capability-scoped: reads
    # within scope succeed, anything else is refused by the same RBAC
    # stack that gates external callers.
    from palestrix.plugins.registry import registry

    api = registry.plugins["provider-demo"].ctx.api
    assert api is not None
    assert api.get("/api/v1/instances").status_code == 200
    assert (
        api.post("/api/v1/courses", json={"code": "X", "title": "Nope"}).status_code
        == 403
    )
    assert api.get("/api/v1/plugins").status_code == 403


def test_echo_provider_end_to_end(client, superadmin, teacher, student):
    # With the plugin enabled, the "echo" kind is publishable and launchable.
    resp = client.post(
        "/api/v1/labs/templates",
        data={
            "slug": "echo-lab:1.0",
            "title": "Echo Lab",
            "kind": "echo",
            "access_mode": "no-gui",
            "ttl_minutes_default": "30",
            "ttl_minutes_max": "60",
        },
        headers=teacher,
    )
    assert resp.status_code == 201, resp.text

    inst = client.post(
        "/api/v1/instances", json={"template_id": resp.json()["id"]}, headers=student
    )
    assert inst.status_code == 201, inst.text
    body = inst.json()
    assert body["state"] == "running"
    assert body["node"] == "echo-plugin"

    logs = client.get(f"/api/v1/instances/{body['id']}/logs", headers=student).json()
    assert any(line["msg"].startswith("echo:") for line in logs)

    client.delete(f"/api/v1/instances/{body['id']}", headers=student)

    # Disabling the plugin deactivates its provider: new publishes and
    # launches of the kind are refused.
    client.post("/api/v1/plugins/provider-demo/disable", headers=superadmin)
    bad = client.post(
        "/api/v1/labs/templates",
        data={
            "slug": "echo-lab:2.0",
            "title": "Echo Lab 2",
            "kind": "echo",
            "access_mode": "no-gui",
            "ttl_minutes_default": "30",
            "ttl_minutes_max": "60",
        },
        headers=teacher,
    )
    assert bad.status_code == 422
    relaunch = client.post(
        "/api/v1/instances", json={"template_id": "echo-lab:1.0"}, headers=student
    )
    assert relaunch.status_code == 409

    # Re-enable for later tests.
    ok = client.post(
        "/api/v1/plugins/provider-demo/enable", json={"config": {}}, headers=superadmin
    )
    assert ok.status_code == 200


def test_required_config_and_secret_encryption(client, superadmin):
    # Missing required config is refused with the exact keys.
    resp = client.post(
        "/api/v1/plugins/needy/enable", json={"config": {}}, headers=superadmin
    )
    assert resp.status_code == 422
    assert "api_url" in resp.json()["detail"]

    # Undeclared keys are refused too.
    resp = client.post(
        "/api/v1/plugins/needy/enable",
        json={"config": {"api_url": "https://x", "api_token": "s3cret", "bogus": 1}},
        headers=superadmin,
    )
    assert resp.status_code == 422

    resp = client.post(
        "/api/v1/plugins/needy/enable",
        json={"config": {"api_url": "https://x.example", "api_token": "s3cret-token"}},
        headers=superadmin,
    )
    assert resp.status_code == 200, resp.text

    # The secret key is encrypted at rest, never stored in the clear.
    from palestrix.db import SessionLocal
    from palestrix.models import PluginRecord

    db = SessionLocal()
    try:
        record = db.get(PluginRecord, "needy")
        assert record.config["api_url"] == "https://x.example"
        stored_token = record.config["api_token"]
        assert stored_token != "s3cret-token"
        assert stored_token.startswith("enc:v1:")
    finally:
        db.close()

    # And decrypted into the running context.
    from palestrix.plugins.registry import registry

    assert registry.plugins["needy"].ctx.config["api_token"] == "s3cret-token"

    client.post("/api/v1/plugins/needy/disable", headers=superadmin)


def test_crash_isolation(client, superadmin, teacher, student2):
    resp = client.post(
        "/api/v1/plugins/crashy/enable", json={"config": {}}, headers=superadmin
    )
    assert resp.status_code == 200

    # Trigger a bus event through the normal flow: publish a writeup.
    # TestClient runs background tasks after the response, so the crashing
    # on_event hook fires during this request... and must not break it.
    pub = client.post(
        "/api/v1/community/writeups",
        json={"title": "Crash test writeup", "published": True},
        headers=student2,
    )
    assert pub.status_code == 201

    # The platform is fine, the crashy plugin is disabled and errored.
    crashy = _plugin(client, superadmin, "crashy")
    assert crashy["state"] == "error"
    assert "crashed" in (crashy["error"] or "")

    # Other plugins were untouched.
    demo = _plugin(client, superadmin, "provider-demo")
    assert demo["state"] == "enabled"


def test_scope_escalation_needs_each_new_scope_approved(client, superadmin):
    """Re-approval must name every newly requested scope.

    The check used a proper-subset test, so approving a scope that was not a
    strict subset of the escalation — an unrelated one, say — satisfied it,
    and the genuinely new scope was granted without anybody having approved
    it. Driven through the registry because this is the enablement rule
    rather than an HTTP concern.
    """
    import dataclasses

    from sqlalchemy import select

    from palestrix.db import SessionLocal
    from palestrix.models import PluginRecord, User
    from palestrix.plugins.registry import PluginError, registry

    loaded = registry.plugins["crashy"]
    original = loaded.manifest
    db = SessionLocal()
    try:
        # The service principal the registry mints is owned by a real
        # account, so the grantor has to be one.
        grantor = db.scalar(select(User.id).where(User.handle == "super1"))
        # The installed version was approved for one scope only.
        record = db.get(PluginRecord, "crashy") or PluginRecord(plugin_id="crashy")
        record.granted_scopes = ["instances:read"]
        record.enabled = False
        db.add(record)
        db.commit()

        # The "new version" additionally wants instances:launch.
        loaded.manifest = dataclasses.replace(
            original, scopes=("instances:read", "instances:launch")
        )

        # Approving an unrelated scope must not carry instances:launch in.
        with pytest.raises(PluginError) as unrelated:
            registry.enable(
                db, "crashy", config={}, granted_by_user_id=grantor,
                approve_scopes=["courses:read"],
            )
        assert "instances:launch" in str(unrelated.value)
        assert unrelated.value.code == "scopes"

        # Approving nothing is refused for the same reason.
        with pytest.raises(PluginError):
            registry.enable(
                db, "crashy", config={}, granted_by_user_id=grantor,
                approve_scopes=[],
            )

        # Naming it is what grants it.
        registry.enable(
            db, "crashy", config={}, granted_by_user_id=grantor,
            approve_scopes=["instances:launch"],
        )
        db.expire_all()
        assert set(db.get(PluginRecord, "crashy").granted_scopes) == {
            "instances:read",
            "instances:launch",
        }
    finally:
        loaded.manifest = original
        try:
            registry.disable(db, "crashy")
        except PluginError:
            pass
        db.close()

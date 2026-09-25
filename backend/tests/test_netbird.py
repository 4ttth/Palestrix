"""The superadmin NetBird overlay console: peer classification, the reap
safety rules, and the endpoints that surface them."""

import palestrix.integrations.netbird as nb
from palestrix.config import get_settings


def _peer(name, connected, groups, pid=None):
    return {
        "id": pid or name,
        "name": name,
        "ip": "100.105.0.9",
        "connected": connected,
        "last_seen": "2026-09-24T07:25:41Z",
        "os": "Linux",
        "groups": [{"name": g} for g in groups],
    }


def test_classify_flags_students_and_protects_infrastructure():
    student = nb.classify(_peer("stud-laptop", False, ["All", "students"]))
    assert student["is_student"] and not student["is_protected"]

    router = nb.classify(_peer("palestrix-lab-router", True, ["All", "lab-routers"]))
    assert router["is_protected"] and not router["is_student"]

    # A peer tagged both student and protected is treated as protected: the
    # router must never be reapable even if a future change also tags it.
    both = nb.classify(_peer("weird", False, ["students", "infrastructure"]))
    assert both["is_protected"] and not both["is_student"]


def test_reapable_is_offline_students_only():
    peers = [
        _peer("online-student", True, ["students"]),
        _peer("offline-student", False, ["students"]),
        _peer("offline-router", False, ["lab-routers"]),
        _peer("offline-admin", False, ["infrastructure"]),
    ]
    names = {p["name"] for p in nb.reapable(peers)}
    assert names == {"offline-student"}


def test_netbird_status_configured_false_without_token(client, admin, monkeypatch):
    monkeypatch.delenv("PALESTRIX_NETBIRD_API_TOKEN", raising=False)
    get_settings.cache_clear()
    body = client.get("/api/v1/admin/netbird", headers=admin).json()
    assert body["configured"] is False
    assert body["peers"] == []


def test_netbird_console_is_infra_only(client, student):
    assert client.get("/api/v1/admin/netbird", headers=student).status_code == 403
    assert client.post("/api/v1/admin/netbird/reap", headers=student).status_code == 403


def test_netbird_reap_spares_online_and_protected(client, admin, monkeypatch):
    """The reap endpoint deletes offline students, keeps online ones, and
    never touches the router — proven against a fake NetBird."""
    peers = [
        _peer("online-student", True, ["students"], "p1"),
        _peer("offline-student-a", False, ["students"], "p2"),
        _peer("offline-student-b", False, ["students"], "p3"),
        _peer("palestrix-lab-router", False, ["lab-routers"], "p4"),
    ]
    deleted = []

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def peers(self):
            return peers

        def delete_peer(self, pid):
            deleted.append(pid)

        def close(self):
            pass

    monkeypatch.setenv("PALESTRIX_NETBIRD_API_TOKEN", "tok")
    monkeypatch.setattr(nb, "NetBirdClient", FakeClient)
    get_settings.cache_clear()

    body = client.post("/api/v1/admin/netbird/reap", headers=admin).json()
    assert set(body["reaped"]) == {"offline-student-a", "offline-student-b"}
    assert body["kept"] == 1
    assert set(deleted) == {"p2", "p3"}  # never p4 (router), never p1 (online)

    monkeypatch.delenv("PALESTRIX_NETBIRD_API_TOKEN", raising=False)
    get_settings.cache_clear()


def test_delete_peer_refuses_the_router(client, admin, monkeypatch):
    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def peers(self):
            return [_peer("palestrix-lab-router", True, ["lab-routers"], "router-id")]

        def delete_peer(self, pid):
            raise AssertionError("must not delete a protected peer")

        def close(self):
            pass

    monkeypatch.setenv("PALESTRIX_NETBIRD_API_TOKEN", "tok")
    monkeypatch.setattr(nb, "NetBirdClient", FakeClient)
    get_settings.cache_clear()

    resp = client.delete("/api/v1/admin/netbird/peers/router-id", headers=admin)
    assert resp.status_code == 409

    monkeypatch.delenv("PALESTRIX_NETBIRD_API_TOKEN", raising=False)
    get_settings.cache_clear()


def test_access_endpoint_carries_the_shared_join_command(client, student, monkeypatch):
    monkeypatch.setenv("PALESTRIX_NETBIRD_MANAGEMENT_URL", "https://api.netbird.io")
    monkeypatch.setenv("PALESTRIX_NETBIRD_SETUP_KEY", "SHARED-KEY-123")
    monkeypatch.setenv("PALESTRIX_LAB_SSH_PASSWORD", "PalestrixLab2026")
    get_settings.cache_clear()

    body = client.get("/api/v1/instances/access", headers=student).json()
    assert body["configured"] is True
    assert body["setup_key"] == "SHARED-KEY-123"
    assert body["join_command"] == (
        "netbird up --management-url https://api.netbird.io --setup-key SHARED-KEY-123"
    )
    # The lab login rides along so the modal is one place.
    assert body["lab_username"] == "student"
    assert body["lab_password"] == "PalestrixLab2026"

    for var in (
        "PALESTRIX_NETBIRD_MANAGEMENT_URL",
        "PALESTRIX_NETBIRD_SETUP_KEY",
        "PALESTRIX_LAB_SSH_PASSWORD",
    ):
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()

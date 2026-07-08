"""Provider connectivity self-tests: the admin console's "Test connection"
button and the check() adapters behind it."""

import httpx


def test_check_endpoint_registry_only_provider(client, admin, student):
    resp = client.post("/api/v1/admin/providers/demo/check", headers=admin)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert "registry-only" in body["detail"]

    assert (
        client.post("/api/v1/admin/providers/demo/check", headers=student).status_code
        == 403
    )
    assert (
        client.post("/api/v1/admin/providers/ghost/check", headers=admin).status_code
        == 404
    )


def test_proxmox_check_reports_cluster_summary(client):
    from palestrix.orchestration.proxmox import ProxmoxProvider

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/version"):
            return httpx.Response(200, json={"data": {"version": "9.1.1"}})
        if request.url.path.endswith("/nodes/pve/qemu"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"vmid": 100, "name": "kali-web", "template": 1},
                        {"vmid": 101, "name": "lab-1234", "template": 0},
                    ]
                },
            )
        return httpx.Response(404)

    mock_client = httpx.Client(
        base_url="https://pve.test/api2/json",
        transport=httpx.MockTransport(handler),
    )
    provider = ProxmoxProvider(client=mock_client)
    detail = provider.check()
    assert "9.1.1" in detail
    assert "2 VMs" in detail
    assert "1 templates" in detail


def test_proxmox_check_surfaces_auth_failure(client):
    from palestrix.orchestration.proxmox import ProxmoxError, ProxmoxProvider

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid token value!")

    mock_client = httpx.Client(
        base_url="https://pve.test/api2/json",
        transport=httpx.MockTransport(handler),
    )
    provider = ProxmoxProvider(client=mock_client)
    try:
        provider.check()
        raise AssertionError("check() should have raised")
    except ProxmoxError as exc:
        assert "401" in str(exc)
        assert "invalid token value" in str(exc)


def test_docker_check_uses_cli(client):
    from palestrix.orchestration.docker import DockerProvider

    calls = []

    def runner(args, input_bytes=None):
        calls.append(args)
        return "27.1.1\n"

    provider = DockerProvider(runner=runner)
    detail = provider.check()
    assert "27.1.1" in detail
    assert calls == [["version", "--format", "{{.Server.Version}}"]]

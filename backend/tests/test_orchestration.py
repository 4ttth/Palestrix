"""Phase 4 orchestration: the SSE log stream, the stop transition, the TTL
reaper (scheduled logic exercised via the admin force-run), provision
failure/retry policy, and both real adapters driven against fakes — the
Docker adapter with a recorded CLI runner, the Proxmox adapter with an
httpx.MockTransport standing in for a PVE cluster."""

import io
import json
import uuid
from datetime import datetime, timedelta, timezone

import httpx


def _publish_container_template(client, teacher, slug=None):
    slug = slug or f"orch-lab-{uuid.uuid4().hex[:6]}:1.0"
    resp = client.post(
        "/api/v1/labs/templates",
        data={
            "slug": slug,
            "title": "Orchestration Lab",
            "kind": "container",
            "access_mode": "no-gui",
            "ttl_minutes_default": "60",
            "ttl_minutes_max": "120",
        },
        files={"archive": ("bundle.tar.gz", b"fake-archive-bytes")},
        headers=teacher,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _cleanup(client, headers):
    for row in client.get("/api/v1/instances", headers=headers).json():
        if row["state"] in ("running", "stopped"):
            client.delete(f"/api/v1/instances/{row['id']}", headers=headers)


def test_sse_log_stream_replays_and_closes(client, teacher, student):
    template = _publish_container_template(client, teacher)
    inst = client.post(
        "/api/v1/instances", json={"template_id": template["id"]}, headers=student
    ).json()
    assert inst["state"] == "running"  # inline queue finished before the response

    events, final_state = [], None
    with client.stream(
        "GET", f"/api/v1/instances/{inst['id']}/logs/stream", headers=student
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        lines = list(resp.iter_lines())
    for i, line in enumerate(lines):
        if line.startswith("data: ") and (i == 0 or not lines[i - 1].startswith("event:")):
            events.append(json.loads(line[len("data: "):]))
        if line.startswith("event: state"):
            final_state = lines[i + 1][len("data: "):]

    # The stream replays what /logs returned, then closes with the state.
    assert any("running" in e["msg"] for e in events)
    assert {"t", "level", "msg"} <= set(events[0])
    assert final_state == "running"

    # Streams are owner-gated exactly like the one-shot log endpoint.
    other = client.post(
        "/api/v1/auth/login",
        json={"email": "stud2@example.edu", "password": "test-password-123!"},
    ).json()["access_token"]
    denied = client.get(
        f"/api/v1/instances/{inst['id']}/logs/stream",
        headers={"Authorization": f"Bearer {other}"},
    )
    assert denied.status_code == 403
    _cleanup(client, student)


def test_stop_transition(client, teacher, student):
    template = _publish_container_template(client, teacher)
    inst = client.post(
        "/api/v1/instances", json={"template_id": template["id"]}, headers=student
    ).json()

    stopped = client.post(f"/api/v1/instances/{inst['id']}/stop", headers=student)
    assert stopped.status_code == 200
    assert stopped.json()["state"] == "stopped"

    # stop is running-only; extend is running-only too.
    again = client.post(f"/api/v1/instances/{inst['id']}/stop", headers=student)
    assert again.status_code == 409
    extend = client.post(
        f"/api/v1/instances/{inst['id']}/extend", json={"minutes": 30}, headers=student
    )
    assert extend.status_code == 409

    # A stopped instance still holds quota until destroyed or reaped.
    gone = client.delete(f"/api/v1/instances/{inst['id']}", headers=student)
    assert gone.status_code == 202 and gone.json()["state"] == "expired"


def test_reaper_expires_and_releases_quota(client, teacher, student, admin):
    template = _publish_container_template(client, teacher)
    inst = client.post(
        "/api/v1/instances", json={"template_id": template["id"]}, headers=student
    ).json()

    # Students cannot run the reaper.
    assert (
        client.post("/api/v1/admin/reaper/run", headers=student).status_code == 403
    )

    # Nothing has expired yet: a pass reaps nothing.
    idle = client.post("/api/v1/admin/reaper/run", headers=admin).json()
    assert inst["id"] not in idle["reaped"]

    # Move expiry into the past and force a pass.
    from palestrix.db import SessionLocal
    from palestrix.models import Instance

    db = SessionLocal()
    try:
        row = db.get(Instance, inst["id"])
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()

    result = client.post("/api/v1/admin/reaper/run", headers=admin).json()
    assert inst["id"] in result["reaped"]

    detail = client.get(f"/api/v1/instances/{inst['id']}", headers=student).json()
    assert detail["state"] == "expired"
    logs = client.get(f"/api/v1/instances/{inst['id']}/logs", headers=student).json()
    assert any("reaper: TTL hit" in line["msg"] for line in logs)

    # Quota released: the tenant (cap 2) can immediately host new launches.
    relaunch = client.post(
        "/api/v1/instances", json={"template_id": template["id"]}, headers=student
    )
    assert relaunch.status_code == 201
    _cleanup(client, student)


def test_provision_failure_retries_once_then_fails(client, teacher, student):
    from palestrix.providers import register_provider

    class FlakyProvider:
        name = "flaky"
        kinds = ("flaky",)
        attempts = 0

        def provision(self, db, instance, template):
            FlakyProvider.attempts += 1
            raise RuntimeError("simulated adapter outage")

        def destroy(self, db, instance):
            pass

    register_provider(FlakyProvider())
    resp = client.post(
        "/api/v1/labs/templates",
        data={
            "slug": "flaky-lab:1.0",
            "title": "Flaky Lab",
            "kind": "flaky",
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
    assert inst.status_code == 201
    body = inst.json()
    # Re-queued once with the same instance id, then marked failed.
    assert FlakyProvider.attempts == 2
    assert body["state"] == "failed"
    logs = client.get(f"/api/v1/instances/{body['id']}/logs", headers=student).json()
    assert any("provision failed: simulated adapter outage" in l["msg"] for l in logs)
    assert any("retry (attempt 2)" in l["msg"] for l in logs)

    # failed is not an active state: the slot is free again.
    template = _publish_container_template(client, teacher)
    ok = client.post(
        "/api/v1/instances", json={"template_id": template["id"]}, headers=student
    )
    assert ok.status_code == 201
    _cleanup(client, student)


# -- Docker adapter against a recorded fake CLI ---------------------------------


class FakeDockerCli:
    """Stands in for the docker binary: records every invocation and answers
    from a small canned state machine."""

    def __init__(self):
        self.calls = []
        self.containers = {}  # cid -> instance label
        self.networks = ["bridge"]
        self.images = set()
        self._next = 0

    def __call__(self, args, input_bytes=None):
        self.calls.append((list(args), input_bytes))
        cmd = args[0]
        if cmd == "ps":
            label = next(a for a in args if a.startswith("label=")).partition("=")[2]
            if "=" in label:
                key, _, value = label.partition("=")
            else:
                value = None
            hits = [
                cid
                for cid, iid in self.containers.items()
                if value is None or iid == value
            ]
            return "\n".join(hits) + ("\n" if hits else "")
        if cmd == "network":
            if args[1] == "ls":
                return "\n".join(self.networks) + "\n"
            self.networks.append(args[-1])
            return ""
        if cmd == "images":
            return "sha256:cafe\n" if args[-1] in self.images else ""
        if cmd == "build":
            self.images.add(args[args.index("-t") + 1])
            return ""
        if cmd == "run":
            self._next += 1
            cid = f"c0ffee{self._next:06d}abcdef"
            label = next(a for a in args if a.startswith("palestrix.instance="))
            self.containers[cid] = label.partition("=")[2]
            return cid + "\n"
        if cmd == "port":
            return "22/tcp -> 0.0.0.0:49155\n"
        if cmd == "inspect":
            return self.containers.get(args[-1], "") + "\n"
        if cmd in ("stop", "rm"):
            self.containers.pop(args[-1], None)
            return ""
        raise AssertionError(f"unexpected docker call: {args}")


def test_docker_adapter_lifecycle(client, teacher, student):
    """Provision → published port exposed → stop → destroy, entirely through
    the adapter with a fake CLI. Uses real registry rows and real storage."""
    import io as _io

    from palestrix.db import SessionLocal
    from palestrix.models import Instance, InstanceState, LabTemplate
    from palestrix.orchestration.docker import DockerProvider
    from palestrix.storage import get_storage

    slug = f"dockerized:{uuid.uuid4().hex[:4]}"
    key = f"templates/{slug.replace(':', '_')}/bundle.tar.gz"
    get_storage().put("lab-archives", key, _io.BytesIO(b"tar-bytes"), 9)

    db = SessionLocal()
    try:
        template = LabTemplate(
            slug=slug,
            title="Dockerized",
            kind="container",
            access_mode="no-gui",
            archive_key=f"lab-archives/{key}",
            owner_id="tester",
        )
        instance = Instance(
            id=f"lab-{uuid.uuid4().hex[:4]}",
            template_id="tpl",
            owner_id="tester",
            tenant_id="test-tenant",
            state=InstanceState.provisioning,
        )
        fake = FakeDockerCli()
        provider = DockerProvider(runner=fake)

        provider.provision(db, instance, template)
        assert instance.state is InstanceState.running
        assert instance.port == 49155
        assert instance.proto == "ssh"
        assert instance.node.startswith("docker/")
        # The archive fed docker build as the stdin context.
        build = next(c for c in fake.calls if c[0][0] == "build")
        assert build[1] == b"tar-bytes"
        # The tenant network was created with the documented name.
        assert "net-test-tenant" in fake.networks
        run = next(c[0] for c in fake.calls if c[0][0] == "run")
        assert "--network" in run and "net-test-tenant" in run
        assert f"palestrix.instance={instance.id}" in " ".join(run)

        provider.stop(db, instance)
        assert any(c[0][0] == "stop" for c in fake.calls)
        provider.destroy(db, instance)
        assert not fake.containers  # gone

        db.rollback()  # scratch rows never land in the shared test db
    finally:
        db.close()


# -- Proxmox adapter against a mocked PVE API ------------------------------------


def _proxmox_mock(state: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        state["requests"].append((request.method, path))
        if path.endswith("/cluster/nextid"):
            return httpx.Response(200, json={"data": "9001"})
        if path.endswith("/nodes/pve/qemu") and request.method == "GET":
            vms = [{"vmid": 100, "name": "kali-web", "template": 1}]
            if state.get("cloned"):
                vms.append({"vmid": 9001, "name": state["instance_id"], "template": 0})
            return httpx.Response(200, json={"data": vms})
        if path.endswith("/qemu/100/clone"):
            state["cloned"] = True
            return httpx.Response(200, json={"data": "UPID:pve:clone"})
        if "/tasks/" in path and path.endswith("/status"):
            return httpx.Response(
                200, json={"data": {"status": "stopped", "exitstatus": "OK"}}
            )
        if path.endswith("/qemu/9001/config"):
            state["config"] = dict(httpx.QueryParams(request.content.decode()))
            return httpx.Response(200, json={"data": None})
        if path.endswith("/qemu/9001/status/start"):
            return httpx.Response(200, json={"data": "UPID:pve:start"})
        if path.endswith("/qemu/9001/agent/network-get-interfaces"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "result": [
                            {"name": "lo", "ip-addresses": [
                                {"ip-address": "127.0.0.1", "ip-address-type": "ipv4"}
                            ]},
                            {"name": "eth0", "ip-addresses": [
                                {"ip-address": "10.24.7.31", "ip-address-type": "ipv4"}
                            ]},
                        ]
                    }
                },
            )
        if path.endswith("/qemu/9001/status/stop"):
            return httpx.Response(200, json={"data": "UPID:pve:stop"})
        if path.endswith("/qemu/9001") and request.method == "DELETE":
            state["deleted"] = True
            return httpx.Response(200, json={"data": "UPID:pve:destroy"})
        return httpx.Response(500, json={"errors": f"unmocked {path}"})

    return httpx.MockTransport(handler)


def test_proxmox_adapter_lifecycle(client):
    from palestrix.db import SessionLocal
    from palestrix.models import Instance, InstanceState, LabTemplate
    from palestrix.orchestration.proxmox import ProxmoxProvider

    state = {"requests": [], "instance_id": f"lab-{uuid.uuid4().hex[:4]}"}
    mock_client = httpx.Client(
        transport=_proxmox_mock(state), base_url="https://pve:8006/api2/json"
    )
    provider = ProxmoxProvider(client=mock_client, poll_seconds=0)

    db = SessionLocal()
    try:
        template = LabTemplate(
            slug="vm-lab:1.0",
            title="VM Lab",
            kind="vm",
            access_mode="no-gui",
            vm_template="kali-web",
            owner_id="tester",
        )
        instance = Instance(
            id=state["instance_id"],
            template_id="tpl",
            owner_id="tester",
            tenant_id="test-tenant",
            state=InstanceState.provisioning,
        )
        provider.provision(db, instance, template)
        assert instance.state is InstanceState.running
        assert instance.host == "10.24.7.31"  # from the guest agent
        assert instance.port == 22 and instance.proto == "ssh"
        assert instance.node == "pve"
        assert state["config"]["net0"].startswith("virtio,bridge=")
        # clone happened from the named template's vmid.
        assert ("POST", "/api2/json/nodes/pve/qemu/100/clone") in state["requests"]

        provider.destroy(db, instance)
        assert state.get("deleted") is True

        db.rollback()
    finally:
        db.close()


def test_proxmox_agent_ipv4_skips_apipa_and_loopback():
    """The guest agent reports loopback and a 169.254 APIPA before its real
    lease; the adapter must never publish either as the SSH target."""
    from palestrix.orchestration.proxmox import ProxmoxError, ProxmoxProvider

    scans = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/agent/network-get-interfaces"):
            scans["n"] += 1
            ifaces = [
                {"name": "lo", "ip-addresses": [
                    {"ip-address": "127.0.0.1", "ip-address-type": "ipv4"}]},
                {"name": "eth0", "ip-addresses": [
                    {"ip-address": "169.254.11.22", "ip-address-type": "ipv4"}]},
            ]
            # The DHCP lease only lands on the third poll.
            if scans["n"] >= 3:
                ifaces[1]["ip-addresses"] = [
                    {"ip-address": "10.24.7.55", "ip-address-type": "ipv4"}
                ]
            return httpx.Response(200, json={"data": {"result": ifaces}})
        return httpx.Response(500, json={"errors": "unmocked"})

    provider = ProxmoxProvider(
        client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://pve:8006/api2/json"
        ),
        poll_seconds=0,
    )
    # Prefers the tenant subnet; APIPA and loopback are skipped entirely.
    assert provider._agent_ipv4(9001, tenant_cidr="10.24.7.0/24") == "10.24.7.55"
    assert scans["n"] >= 3

    # A VM that only ever gets APIPA is a hard failure, not a bad SSH target.
    def apipa_only(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"result": [
            {"name": "eth0", "ip-addresses": [
                {"ip-address": "169.254.9.9", "ip-address-type": "ipv4"}]},
        ]}})

    stuck = ProxmoxProvider(
        client=httpx.Client(
            transport=httpx.MockTransport(apipa_only), base_url="https://pve:8006/api2/json"
        ),
        poll_seconds=0,
    )
    stuck._timeout = 0  # deadline is immediately past
    try:
        stuck._agent_ipv4(9001, tenant_cidr="10.24.7.0/24")
        raise AssertionError("APIPA-only should raise, not return a link-local address")
    except ProxmoxError as exc:
        assert "no usable IPv4" in str(exc)

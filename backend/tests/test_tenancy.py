"""Phase 7: the multitenant cloud layer and the hardened-deployment code
paths. Tenant lifecycle through the API (materialize, quota edits, archive),
the full instances/vCPU/RAM quota check, the tenant VLAN on the Proxmox
adapter plus admin ISO forwarding to cluster storage, both real cloud
adapters against mocked managers (OpenNebula XML-RPC, CloudStack signed
REST), the additive schema migrations, the security headers, and the
production boot guard."""

import base64
import hashlib
import hmac
import uuid
import xmlrpc.client
from urllib.parse import quote

import httpx

from test_orchestration import _proxmox_mock, _publish_container_template


def _new_tenant(client, admin, **overrides):
    body = {
        "id": f"t-{uuid.uuid4().hex[:8]}",
        "name": "Phase 7 Tenant",
        "instance_quota": 5,
        "cpu_cap": 48,
        "ram_cap_gb": 96,
        **overrides,
    }
    resp = client.post("/api/v1/admin/tenants", json=body, headers=admin)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _assign(client, admin, tenant_id, handle="stud2"):
    resp = client.post(
        f"/api/v1/admin/tenants/{tenant_id}/assign/{handle}", headers=admin
    )
    assert resp.status_code == 200, resp.text


# -- tenant lifecycle over the API ------------------------------------------------


def test_create_tenant_materializes_network(client, admin, student):
    tenant = _new_tenant(client, admin)

    # LocalCloud allocated the isolation primitives at create time.
    assert tenant["vlan_id"] is not None
    assert tenant["network_cidr"].endswith("/24")
    assert tenant["cloud_ref"] == f"local:vlan={tenant['vlan_id']}"
    assert tenant["archived"] is False

    # A second tenant gets its own VLAN and its own /24 from the pool.
    other = _new_tenant(client, admin)
    assert other["vlan_id"] != tenant["vlan_id"]
    assert other["network_cidr"] != tenant["network_cidr"]

    # A pinned CIDR is kept, never overwritten by the pool.
    pinned = _new_tenant(client, admin, network_cidr="10.99.99.0/24")
    assert pinned["network_cidr"] == "10.99.99.0/24"

    # Slug collisions and non-admin callers are refused.
    dup = client.post(
        "/api/v1/admin/tenants",
        json={"id": tenant["id"], "name": "Duplicate"},
        headers=admin,
    )
    assert dup.status_code == 409
    forbidden = client.post(
        "/api/v1/admin/tenants",
        json={"id": "nope-nope", "name": "Nope"},
        headers=student,
    )
    assert forbidden.status_code == 403


def test_patch_tenant_updates_quotas(client, admin):
    tenant = _new_tenant(client, admin)
    resp = client.patch(
        f"/api/v1/admin/tenants/{tenant['id']}",
        json={"instance_quota": 9, "cpu_cap": 12, "name": "Renamed"},
        headers=admin,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert (body["instance_quota"], body["cpu_cap"], body["name"]) == (9, 12, "Renamed")
    # VLAN and CIDR are fixed at creation; the patch surface cannot touch them.
    assert body["vlan_id"] == tenant["vlan_id"]
    assert body["network_cidr"] == tenant["network_cidr"]

    missing = client.patch(
        "/api/v1/admin/tenants/no-such-tenant", json={"cpu_cap": 1}, headers=admin
    )
    assert missing.status_code == 404


def test_archive_requires_idle_and_blocks_launches(client, admin, teacher, student2):
    # An active instance blocks archiving (destroy or reap first).
    template = _publish_container_template(client, teacher)
    inst = client.post(
        "/api/v1/instances", json={"template_id": template["id"]}, headers=student2
    ).json()
    busy = client.delete("/api/v1/admin/tenants/test-tenant", headers=admin)
    assert busy.status_code == 409
    assert "active instance" in busy.json()["detail"]
    client.delete(f"/api/v1/instances/{inst['id']}", headers=student2)

    # An idle tenant archives; its members can no longer launch.
    doomed = _new_tenant(client, admin)
    _assign(client, admin, doomed["id"])
    try:
        gone = client.delete(f"/api/v1/admin/tenants/{doomed['id']}", headers=admin)
        assert gone.status_code == 200 and gone.json()["archived"] is True
        denied = client.post(
            "/api/v1/instances", json={"template_id": template["id"]}, headers=student2
        )
        assert denied.status_code == 409
        assert "archived" in denied.json()["detail"]
    finally:
        _assign(client, admin, "test-tenant")  # restore for later test modules

    # Archived tenants stay listed (history references them) and are counted.
    cloud = client.get("/api/v1/admin/cloud", headers=admin).json()
    assert cloud["name"] == "local"
    assert cloud["tenants_archived"] >= 1
    listed = client.get("/api/v1/admin/tenants", headers=admin).json()
    assert any(t["id"] == doomed["id"] and t["archived"] for t in listed)


def test_cpu_and_ram_quotas_block_launch(client, admin, teacher, student2):
    tenant = _new_tenant(client, admin, instance_quota=10, cpu_cap=3, ram_cap_gb=64)
    _assign(client, admin, tenant["id"])
    try:
        resp = client.post(
            "/api/v1/labs/templates",
            data={
                "slug": f"heavy-{uuid.uuid4().hex[:6]}:1.0",
                "title": "Heavy Lab",
                "kind": "container",
                "access_mode": "no-gui",
                "cpu": "2",
                "ram_gb": "2",
            },
            files={"archive": ("bundle.tar.gz", b"fake-archive-bytes")},
            headers=teacher,
        )
        assert resp.status_code == 201, resp.text
        template = resp.json()
        assert (template["cpu"], template["ram_gb"]) == (2, 2)

        first = client.post(
            "/api/v1/instances", json={"template_id": template["id"]}, headers=student2
        )
        assert first.status_code == 201, first.text

        # 2 vCPU in use + 2 requested > cap 3: the denial names the blocking
        # quota (docs/ephemeral-lifecycle.md §Walkthrough 1).
        second = client.post(
            "/api/v1/instances", json={"template_id": template["id"]}, headers=student2
        )
        assert second.status_code == 409
        detail = second.json()["detail"]
        assert detail["error"] == "quota_exceeded"
        assert detail["quota"] == "cpu"
        assert (detail["limit"], detail["used"], detail["requested"]) == (3, 2, 2)

        # The tenant listing reports the same live resource usage.
        listed = client.get("/api/v1/admin/tenants", headers=admin).json()
        row = next(t for t in listed if t["id"] == tenant["id"])
        assert (row["instances_active"], row["cpu_active"], row["ram_active_gb"]) == (1, 2, 2)

        client.delete(f"/api/v1/instances/{first.json()['id']}", headers=student2)
    finally:
        _assign(client, admin, "test-tenant")


# -- Proxmox: tenant VLAN tag and ISO forwarding ----------------------------------


def test_proxmox_vlan_tag_and_iso_forwarding(client, admin):
    from palestrix.db import SessionLocal
    from palestrix.models import Instance, InstanceState, LabTemplate, Tenant
    from palestrix.orchestration.proxmox import ProxmoxProvider
    from palestrix.providers import DemoProvider, register_provider

    state = {"requests": [], "instance_id": f"lab-{uuid.uuid4().hex[:4]}"}
    base = _proxmox_mock(state)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/storage/local/upload"):
            state["iso_upload"] = request.headers.get("content-type", "")
            return httpx.Response(200, json={"data": "UPID:pve:upload"})
        return base.handler(request)

    mock_client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://pve:8006/api2/json"
    )
    provider = ProxmoxProvider(client=mock_client, poll_seconds=0)

    db = SessionLocal()
    try:
        tenant = Tenant(id=f"vlan-{uuid.uuid4().hex[:6]}", name="VLAN Tenant", vlan_id=207)
        db.add(tenant)
        # Sessions run with autoflush=False; the adapter looks the tenant up by
        # id mid-provision, so it must be flushed (rollback below removes it).
        db.flush()
        template = LabTemplate(
            slug="vm-vlan:1.0",
            title="VM behind a tenant VLAN",
            kind="vm",
            access_mode="no-gui",
            vm_template="kali-web",
            owner_id="tester",
        )
        instance = Instance(
            id=state["instance_id"],
            template_id="tpl",
            owner_id="tester",
            tenant_id=tenant.id,
            state=InstanceState.provisioning,
        )
        provider.provision(db, instance, template)
        # The tenant's VLAN tag rides the trunk bridge: isolation is the
        # tenant's, not the template's.
        assert state["config"]["net0"].endswith(",tag=207")
        db.rollback()
    finally:
        db.close()

    # Admin ISO uploads forward to the cluster's ISO storage while the
    # Proxmox adapter owns the "vm" kind; object storage keeps its copy.
    register_provider(provider)
    try:
        up = client.post(
            "/api/v1/admin/isos",
            files={"file": ("kali-2026.iso", b"iso-bytes")},
            headers=admin,
        )
        assert up.status_code == 201, up.text
        body = up.json()
        assert body["stored"] == "isos/kali-2026.iso"  # storage keys are bucket/key
        assert body["forwarded_to"] == "local:iso/kali-2026.iso"
        assert "multipart/form-data" in state["iso_upload"]
    finally:
        register_provider(DemoProvider())  # hand "vm" back to the demo provider


# -- OpenNebula adapter against a mocked front-end ---------------------------------


def _one_response(value) -> bytes:
    return xmlrpc.client.dumps(
        ((True, value, 0),), methodresponse=True
    ).encode()


def test_opennebula_adapter_materializes_tenant(client):
    from palestrix.db import SessionLocal
    from palestrix.models import Tenant
    from palestrix.tenancy.opennebula import OpenNebulaCloud

    calls: list[tuple[str, tuple]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params, method = xmlrpc.client.loads(request.content)
        calls.append((method, params[1:]))  # drop the session string
        if method == "one.grouppool.info":
            return httpx.Response(200, content=_one_response("<GROUP_POOL></GROUP_POOL>"))
        if method == "one.group.allocate":
            return httpx.Response(200, content=_one_response(12))
        if method == "one.vnpool.info":
            return httpx.Response(200, content=_one_response("<VNET_POOL></VNET_POOL>"))
        if method == "one.vn.allocate":
            return httpx.Response(200, content=_one_response(34))
        if method == "one.vdcpool.info":
            return httpx.Response(200, content=_one_response("<VDC_POOL></VDC_POOL>"))
        if method == "one.vdc.allocate":
            return httpx.Response(200, content=_one_response(5))
        if method in ("one.vdc.addgroup", "one.group.quota"):
            return httpx.Response(200, content=_one_response(0))
        return httpx.Response(500, content=_one_response(f"unmocked {method}"))

    cloud = OpenNebulaCloud(
        client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url="http://one:2633/RPC2"
        )
    )

    db = SessionLocal()
    try:
        tenant = Tenant(
            id=f"one-{uuid.uuid4().hex[:6]}",
            name="OpenNebula Tenant",
            instance_quota=4,
            cpu_cap=16,
            ram_cap_gb=32,
            network_cidr="10.24.7.0/24",
        )
        db.add(tenant)
        cloud.ensure_tenant(db, tenant)

        assert tenant.cloud_ref == "opennebula:group=12 vdc=5 vnet=34"
        assert tenant.vlan_id is not None
        assert tenant.network_cidr == "10.24.7.0/24"  # pinned CIDR kept

        vn_template = next(p for m, p in calls if m == "one.vn.allocate")[0]
        assert f'VLAN_ID = "{tenant.vlan_id}"' in vn_template
        assert 'AR = [ TYPE = "IP4", IP = "10.24.7.1", SIZE = "254" ]' in vn_template
        quota = next(p for m, p in calls if m == "one.group.quota")
        assert quota[0] == 12
        assert "VMS = 4" in quota[1] and "CPU = 16" in quota[1]
        assert "MEMORY = 32768" in quota[1]  # GB -> MB
        assert ("one.vdc.addgroup", (5, 12)) in calls
        db.rollback()
    finally:
        db.close()


# -- CloudStack adapter against a mocked management server -------------------------


def test_cloudstack_adapter_signs_and_materializes(client):
    from palestrix.db import SessionLocal
    from palestrix.models import Tenant
    from palestrix.tenancy.cloudstack import CloudStackCloud

    secret = "cs-secret-key"
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        # Every request must carry a valid signature (sorted params,
        # lowercased URL encoding, HMAC-SHA1, base64).
        signature = params.pop("signature")
        canonical = "&".join(
            f"{k.lower()}={quote(v, safe='*').lower()}"
            for k, v in sorted(params.items())
        )
        expected = base64.b64encode(
            hmac.new(secret.encode(), canonical.encode(), hashlib.sha1).digest()
        ).decode()
        assert signature == expected, f"bad signature on {params['command']}"
        calls.append(params)

        command = params["command"]
        if command == "listDomains":
            return httpx.Response(200, json={"listdomainsresponse": {}})
        if command == "createDomain":
            return httpx.Response(
                200, json={"createdomainresponse": {"domain": {"id": "dom-42"}}}
            )
        if command == "listAccounts":
            return httpx.Response(200, json={"listaccountsresponse": {}})
        if command == "createAccount":
            return httpx.Response(200, json={"createaccountresponse": {}})
        if command == "updateResourceLimit":
            return httpx.Response(200, json={"updateresourcelimitresponse": {}})
        if command == "listNetworks":
            return httpx.Response(200, json={"listnetworksresponse": {}})
        if command == "createNetwork":
            return httpx.Response(200, json={"createnetworkresponse": {}})
        return httpx.Response(
            200, json={"errorresponse": {"errortext": f"unmocked {command}"}}
        )

    cloud = CloudStackCloud(
        client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://cs:8080/client/api"
        )
    )
    cloud._api_key = "cs-api-key"
    cloud._secret_key = secret
    cloud._zone_id = "zone-1"
    cloud._offering_id = "offer-1"

    db = SessionLocal()
    try:
        tenant = Tenant(
            id=f"cs-{uuid.uuid4().hex[:6]}",
            name="CloudStack Tenant",
            instance_quota=6,
            cpu_cap=24,
            ram_cap_gb=48,
            network_cidr="10.31.5.0/24",
        )
        db.add(tenant)
        cloud.ensure_tenant(db, tenant)

        assert tenant.cloud_ref == "cloudstack:domain=dom-42"
        limits = {
            c["resourcetype"]: c["max"]
            for c in calls
            if c["command"] == "updateResourceLimit"
        }
        assert limits == {"0": "6", "8": "24", "9": "49152"}  # GB -> MB
        network = next(c for c in calls if c["command"] == "createNetwork")
        assert network["name"] == f"net-{tenant.id}"
        assert network["gateway"] == "10.31.5.1"
        assert network["domainid"] == "dom-42"

        # Retirement is one cleanup call once the domain exists.
        calls.clear()

        def retire_handler(request: httpx.Request) -> httpx.Response:
            params = dict(request.url.params)
            calls.append(params)
            if params["command"] == "listDomains":
                return httpx.Response(
                    200,
                    json={"listdomainsresponse": {"domain": [{"id": "dom-42"}]}},
                )
            return httpx.Response(200, json={"deletedomainresponse": {}})

        cloud._client = httpx.Client(
            transport=httpx.MockTransport(retire_handler),
            base_url="https://cs:8080/client/api",
        )
        cloud.retire_tenant(db, tenant)
        assert any(
            c["command"] == "deleteDomain" and c["cleanup"] == "true" for c in calls
        )
        assert tenant.cloud_ref == "cloudstack:retired"
        db.rollback()
    finally:
        db.close()


# -- hardened deployments -----------------------------------------------------------


def test_migrations_add_missing_columns(tmp_path):
    from sqlalchemy import create_engine, inspect, text

    from palestrix.migrations import upgrade

    engine = create_engine(f"sqlite:///{tmp_path / 'pre-phase7.db'}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE tenants (id VARCHAR(64) PRIMARY KEY, name VARCHAR(128), "
                "instance_quota INTEGER, cpu_cap INTEGER, ram_cap_gb INTEGER, "
                "network_cidr VARCHAR(32), created_at DATETIME)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO tenants (id, name, instance_quota, cpu_cap, ram_cap_gb, "
                "network_cidr) VALUES ('legacy', 'Legacy', 3, 48, 96, '')"
            )
        )

    applied = upgrade(engine)
    columns = {c["name"] for c in inspect(engine).get_columns("tenants")}
    assert {"vlan_id", "cloud_ref", "archived"} <= columns
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT archived, cloud_ref FROM tenants WHERE id = 'legacy'")
        ).one()
    assert row.archived == 0 and row.cloud_ref == ""  # defaults backfilled
    assert applied and upgrade(engine) == []  # second pass is a no-op


def test_security_headers_on_every_response(client):
    resp = client.get("/healthz")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    # HSTS is production-only; the dev/test app must not pin plain HTTP setups.
    assert "Strict-Transport-Security" not in resp.headers


def test_production_readiness_guard():
    import pytest

    from palestrix.config import Settings
    from palestrix.hardening import DEV_SECRET, enforce_readiness, production_readiness

    dev = Settings(secret_key=DEV_SECRET, _env_file=None)
    findings = production_readiness(dev)
    assert any("PALESTRIX_SECRET_KEY" in f for f in findings)
    assert any("SQLite" in f for f in findings)

    hardened = Settings(
        environment="production",
        secret_key="p" * 48,
        database_url="postgresql+psycopg://palestrix:pw@db:5432/palestrix",
        origin="https://palestrix.example.edu",
        cors_origins="https://palestrix.example.edu",
        queue_backend="redis",
        reaper_enabled=True,
        storage_backend="minio",
        _env_file=None,
    )
    assert production_readiness(hardened) == []
    enforce_readiness(hardened)  # must not raise

    # In production the same findings refuse startup instead of warning.
    broken = Settings(
        environment="production", secret_key=DEV_SECRET, _env_file=None
    )
    with pytest.raises(RuntimeError, match="production readiness failed"):
        enforce_readiness(broken)

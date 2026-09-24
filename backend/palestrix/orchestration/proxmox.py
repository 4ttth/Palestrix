"""Proxmox VE adapter: real VMs cloned from admin-built templates.

Talks to the Proxmox HTTP API (``/api2/json``) with an API token — no SSH,
no shelling out to ``qm``. The flow follows docs/ephemeral-lifecycle.md §3:
clone from the named template, attach the tenant bridge, start, wait for
the QEMU guest agent to report an address, then expose either the agent's
IP (headless, ssh) or a noVNC proxy port (gui).

Idempotency is by instance id: the clone is named after the instance
(``lab-XXXX``), and stop/destroy find the VM by that name, so a retried
provision first removes its own leftover.

Activated for the "vm" kind when PALESTRIX_PROXMOX_HOST is set; otherwise
the demo provider keeps the kind. Tests inject an ``httpx.Client`` built on
a MockTransport.
"""

from __future__ import annotations

import logging
import time
from urllib.parse import quote, urlparse

import httpx

from ..config import get_settings
from ..models import InstanceState
from ..providers import add_log
from ..tls import client_verify

logger = logging.getLogger("palestrix.proxmox")


class ProxmoxError(RuntimeError):
    pass


def _clean_credential(name: str, value: str) -> str:
    """Strip whitespace and surrounding quotes from a credential setting,
    logging when anything was removed — those artifacts otherwise surface
    only as an unexplained 401 from the cluster."""
    cleaned = value.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in "\"'":
        cleaned = cleaned[1:-1].strip()
    if cleaned != value:
        logger.warning(
            "proxmox: %s carried surrounding whitespace/quotes; using the cleaned value",
            name,
        )
    return cleaned


def _fingerprint(secret: str) -> str:
    """A non-reversible fingerprint of a secret: character count plus the
    first 8 hex of its SHA-256. Safe to show the owning admin so they can
    confirm the service loaded the *same* secret that works elsewhere (curl,
    the Proxmox UI) without the platform ever echoing the secret itself. A
    mismatch means the running process is reading a different value than
    expected — a stale .env, a wrong working directory, or a systemd
    Environment= override winning over the file."""
    if not secret:
        return "empty"
    import hashlib

    digest = hashlib.sha256(secret.encode()).hexdigest()[:8]
    return f"{len(secret)}ch·{digest}"


class ProxmoxProvider:
    name = "proxmox"
    kinds = ("vm",)

    def __init__(
        self, client: httpx.Client | None = None, poll_seconds: float = 2.0
    ) -> None:
        settings = get_settings()
        self._node = settings.proxmox_node
        self._bridge = settings.proxmox_bridge
        self._iso_storage = settings.proxmox_iso_storage
        self._console_host = urlparse(settings.proxmox_host).hostname or ""
        self._timeout = settings.proxmox_timeout_seconds
        self._poll = poll_seconds
        # The classic .env paste artifacts — surrounding quotes, stray
        # whitespace — turn into an opaque "401 invalid token value!" from
        # the cluster. Strip them and say so, instead of failing silently.
        self._token_id = _clean_credential(
            "PALESTRIX_PROXMOX_TOKEN_ID", settings.proxmox_token_id
        )
        secret = _clean_credential(
            "PALESTRIX_PROXMOX_TOKEN_SECRET", settings.proxmox_token_secret
        )
        # Fingerprint (not the secret) so the connection check can prove which
        # value the process actually loaded — the decisive test when curl
        # works but the service 401s on the same-looking credential.
        self._secret_fingerprint = _fingerprint(secret)
        self._client = client or httpx.Client(
            base_url=f"{settings.proxmox_host.rstrip('/')}/api2/json",
            headers={"Authorization": f"PVEAPIToken={self._token_id}={secret}"},
            verify=client_verify(
                settings.proxmox_verify_tls, settings.proxmox_ca_bundle
            ),
            timeout=settings.proxmox_timeout_seconds,
        )

    # -- API plumbing -------------------------------------------------------------

    @staticmethod
    def _failure(resp: httpx.Response) -> str:
        """Proxmox reports auth failures in the HTTP reason phrase ("401
        invalid token value!") with an empty body — include both so errors
        never truncate to a bare status code."""
        detail = resp.text[:200].strip() or resp.reason_phrase
        return f"{resp.status_code} {detail}"

    def _get(self, path: str):
        resp = self._client.get(path)
        if resp.status_code >= 400:
            raise ProxmoxError(f"GET {path} -> {self._failure(resp)}")
        return resp.json().get("data")

    def _post(self, path: str, **data):
        resp = self._client.post(path, data=data or None)
        if resp.status_code >= 400:
            raise ProxmoxError(f"POST {path} -> {self._failure(resp)}")
        return resp.json().get("data")

    def _delete(self, path: str):
        resp = self._client.delete(path)
        if resp.status_code >= 400:
            raise ProxmoxError(f"DELETE {path} -> {self._failure(resp)}")
        return resp.json().get("data")

    def _wait_task(self, upid: str) -> None:
        """Proxmox mutations return a task UPID; poll it to completion."""
        deadline = time.monotonic() + self._timeout
        path = f"/nodes/{self._node}/tasks/{quote(upid, safe='')}/status"
        while True:
            status = self._get(path) or {}
            if status.get("status") == "stopped":
                if status.get("exitstatus") != "OK":
                    raise ProxmoxError(f"task {upid} failed: {status.get('exitstatus')}")
                return
            if time.monotonic() > deadline:
                raise ProxmoxError(f"task {upid} timed out")
            time.sleep(self._poll)

    def _vm_by_name(self, name: str) -> dict | None:
        for vm in self._get(f"/nodes/{self._node}/qemu") or []:
            if vm.get("name") == name:
                return vm
        return None

    def _agent_ipv4(self, vmid: int, tenant_cidr: str = "") -> str:
        """Poll the guest agent for the instance's real IPv4. The agent needs
        a little while after boot; 500s until then are expected.

        Address selection matters: a VM whose tenant VLAN has no DHCP boots
        with a ``169.254.x`` APIPA (link-local) address, which is useless for
        SSH — publishing it is the classic "connects to APIPA instead of the
        private IP" bug. So link-local, loopback, and Docker/CNI ranges are
        skipped, and when the tenant's CIDR is known its address is preferred
        over any other NIC. If only an APIPA address ever appears, we keep
        waiting (then time out) rather than hand back an unreachable one —
        the real fix is DHCP on the tenant segment (docs/lab-networking.md)."""
        import ipaddress

        subnet = None
        if tenant_cidr:
            try:
                subnet = ipaddress.ip_network(tenant_cidr, strict=False)
            except ValueError:
                subnet = None

        deadline = time.monotonic() + self._timeout
        path = f"/nodes/{self._node}/qemu/{vmid}/agent/network-get-interfaces"
        while True:
            routable = []  # non-loopback, non-link-local IPv4s seen this poll
            try:
                data = self._get(path) or {}
                for iface in data.get("result", []):
                    if iface.get("name") in ("lo", "Loopback"):
                        continue
                    for addr in iface.get("ip-addresses", []):
                        if addr.get("ip-address-type") != "ipv4":
                            continue
                        ip = addr.get("ip-address", "")
                        try:
                            parsed = ipaddress.ip_address(ip)
                        except ValueError:
                            continue
                        if parsed.is_loopback or parsed.is_link_local:
                            continue  # 127.* and 169.254.* are never SSH targets
                        routable.append((ip, parsed))
            except ProxmoxError:
                pass  # agent not up yet
            if routable:
                # A multi-NIC VM: the tenant-subnet address wins; otherwise the
                # first routable NIC is the lab interface.
                if subnet is not None:
                    for ip, parsed in routable:
                        if parsed in subnet:
                            return ip
                return routable[0][0]
            # Only loopback/link-local so far — the VM has no real lease yet
            # (or the tenant VLAN has no DHCP). Wait; do not publish APIPA.
            if time.monotonic() > deadline:
                raise ProxmoxError(
                    f"guest agent on vmid {vmid} reported no usable IPv4 "
                    "(only loopback/link-local — is DHCP running on the tenant "
                    "VLAN? see docs/lab-networking.md)"
                )
            time.sleep(self._poll)

    # -- provider contract ----------------------------------------------------------

    def provision(self, db, instance, template) -> None:
        add_log(db, instance.id, f"queue: job accepted (tenant {instance.tenant_id})")

        source = self._vm_by_name(template.vm_template or "")
        if source is None or not source.get("template"):
            raise ProxmoxError(f"no VM template named '{template.vm_template}' on {self._node}")

        # Idempotent by instance id: a retry replaces its own leftover clone.
        leftover = self._vm_by_name(instance.id)
        if leftover:
            add_log(db, instance.id, "proxmox: replacing leftover VM from a prior attempt", level="warn")
            self._remove_vmid(int(leftover["vmid"]))

        vmid = int(self._get("/cluster/nextid"))
        add_log(
            db,
            instance.id,
            f"proxmox: cloning template {template.vm_template} "
            f"(vmid {source['vmid']} -> {vmid})",
        )
        upid = self._post(
            f"/nodes/{self._node}/qemu/{source['vmid']}/clone",
            newid=vmid,
            name=instance.id,
        )
        self._wait_task(upid)

        # The tenant fixes the network: its VLAN tag rides the trunk bridge,
        # so instances of different tenants can never share a segment
        # (docs/ephemeral-lifecycle.md §Multitenancy invariants).
        from ..models import Tenant

        tenant = db.get(Tenant, instance.tenant_id)
        net0 = f"virtio,bridge={self._bridge}"
        if tenant is not None and tenant.vlan_id:
            net0 += f",tag={tenant.vlan_id}"
            add_log(
                db,
                instance.id,
                f"network: attached to bridge {self._bridge}, vlan {tenant.vlan_id}",
            )
        else:
            add_log(db, instance.id, f"network: attached to bridge {self._bridge}")

        # Size the clone to what the template declares. A clone otherwise
        # inherits the golden image's cores and memory, so a lab published as
        # 1 vCPU / 1 GB could boot as whatever the admin happened to build --
        # and tenant quota (api/instances.py) would still charge the declared
        # figure. Setting them here makes the declaration binding instead of
        # advisory, which is the whole point of declaring it.
        config = {"net0": net0}
        if template.cpu:
            config["cores"] = template.cpu
        if template.ram_gb:
            config["memory"] = template.ram_gb * 1024  # Proxmox wants MiB
        self._post(f"/nodes/{self._node}/qemu/{vmid}/config", **config)
        if "cores" in config or "memory" in config:
            add_log(
                db,
                instance.id,
                f"vm: sized to {template.cpu or 'template'} vCPU, "
                f"{template.ram_gb or 'template'} GB RAM",
            )

        upid = self._post(f"/nodes/{self._node}/qemu/{vmid}/status/start")
        self._wait_task(upid)
        add_log(db, instance.id, "vm: started, waiting for guest agent heartbeat")

        instance.node = self._node
        if template.access_mode == "gui":
            vnc = self._post(f"/nodes/{self._node}/qemu/{vmid}/vncproxy", websocket=1) or {}
            instance.host = self._console_host
            instance.port = int(vnc.get("port", 0))
            instance.proto = "vnc"
            add_log(db, instance.id, f"console: noVNC proxy on {instance.host}:{instance.port}")
        else:
            instance.host = self._agent_ipv4(
                vmid, tenant.network_cidr if tenant is not None else ""
            )
            instance.port = 22
            instance.proto = "ssh"
        instance.state = InstanceState.running
        add_log(
            db,
            instance.id,
            f"instance running, {instance.proto} exposed on {instance.host}:{instance.port}",
            level="ok",
        )

    def read_files(self, db, instance, paths: list[str]) -> dict[str, str | None]:
        """Automated-checking probe: read files through the QEMU guest agent
        (``agent/file-read``, the same agent that reports the VM's address)
        and hash the content locally. A path the agent cannot read — missing
        file, unreadable — reads as absent; a VM that is gone is an error."""
        import hashlib

        vm = self._vm_by_name(instance.id)
        if vm is None:
            raise ProxmoxError("vm not found for grading probe")
        observed: dict[str, str | None] = {}
        for path in paths:
            try:
                data = self._get(
                    f"/nodes/{self._node}/qemu/{vm['vmid']}/agent/file-read"
                    f"?file={quote(path, safe='')}"
                )
            except ProxmoxError:
                observed[path] = None
                continue
            content = (data or {}).get("content")
            observed[path] = (
                hashlib.sha256(content.encode()).hexdigest()
                if content is not None
                else None
            )
        return observed

    def stop(self, db, instance) -> None:
        vm = self._vm_by_name(instance.id)
        if vm is None:
            return
        upid = self._post(f"/nodes/{self._node}/qemu/{vm['vmid']}/status/stop")
        self._wait_task(upid)
        add_log(db, instance.id, "vm: stopped", level="warn")

    def destroy(self, db, instance) -> None:
        vm = self._vm_by_name(instance.id)
        if vm is None:
            add_log(db, instance.id, "vm: already gone", level="warn")
            return
        self._remove_vmid(int(vm["vmid"]))
        add_log(db, instance.id, "vm: stopped and destroyed", level="warn")

    def check(self) -> str:
        """Connectivity self-test for the admin console: round-trips the API
        with the configured token and node — the exact auth the provisioner
        uses — and reports what it can see. Raises ProxmoxError carrying the
        authenticating identity plus Proxmox's own status line (401 invalid
        token, 403 permission check failed, ...) so the console shows both
        what was tried and why it was refused."""
        who = self._token_id or "<no token configured>"
        # secret {len}ch·{hash8}: compare against your working credential —
        #   printf '%s' 'YOUR-SECRET' | sha256sum | cut -c1-8
        # A mismatch means this process loaded a different secret than the
        # one that works (stale .env / wrong CWD / systemd Environment=).
        ident = f"{who} (secret {self._secret_fingerprint})"
        try:
            version = self._get("/version") or {}
            vms = self._get(f"/nodes/{self._node}/qemu") or []
        except ProxmoxError as exc:
            raise ProxmoxError(f"as {ident}: {exc}") from exc
        templates = sum(1 for vm in vms if vm.get("template"))
        return (
            f"Proxmox VE {version.get('version', '?')} reachable as {ident}; "
            f"node {self._node}: {len(vms)} VMs visible, {templates} templates"
        )

    def upload_iso(self, filename: str, data) -> str:
        """Forward an admin-uploaded ISO to the cluster's ISO storage
        (``POST /nodes/{node}/storage/{storage}/upload``), so templates can
        be built from it without touching the Proxmox UI — the Phase 7
        hardened-runbook path (docs/usecase-a-baremetal.md §Layer 1 step 5).

        ``data`` may be bytes or a seekable binary file object; file objects
        are streamed so multi-GB ISOs never sit in memory whole."""
        resp = self._client.post(
            f"/nodes/{self._node}/storage/{self._iso_storage}/upload",
            data={"content": "iso"},
            files={"filename": (filename, data, "application/x-iso9660-image")},
            # A multi-GB ISO outlives the default API timeout; only the
            # read/write legs need the headroom.
            timeout=httpx.Timeout(self._timeout, read=3600.0, write=3600.0),
        )
        if resp.status_code >= 400:
            raise ProxmoxError(
                f"iso upload -> {self._failure(resp)}"
            )
        upid = resp.json().get("data")
        if upid:
            self._wait_task(upid)
        return f"{self._iso_storage}:iso/{filename}"

    def list_isos(self) -> list[dict]:
        """The ISOs the cluster already has, from
        ``GET /nodes/{node}/storage/{storage}/content?content=iso``.

        The admin console used to list only Palestrix's own object-storage
        bucket, so a cluster full of ISOs downloaded through the Proxmox UI
        read as "No ISOs stored" — the upload path forwarded *to* the
        cluster but nothing ever read *back* from it. Provisioning picks a
        boot image from what Proxmox can actually attach, so the cluster is
        the list that matters.

        Returns the adapter-neutral shape the admin endpoint merges into
        ``StoredObjectOut``: volid as the key, size in bytes, no mtime
        (Proxmox reports ``ctime`` only for some storage types, so the
        caller treats it as optional)."""
        rows = self._get(
            f"/nodes/{self._node}/storage/{self._iso_storage}/content"
            "?content=iso"
        ) or []
        out = []
        for row in rows:
            volid = row.get("volid")
            if not volid:
                continue
            out.append(
                {
                    "key": volid,
                    "size": int(row.get("size") or 0),
                    "ctime": row.get("ctime"),
                }
            )
        out.sort(key=lambda r: r["key"].lower())
        return out

    def list_vm_templates(self) -> list[dict]:
        """The VM templates on the node, for the lab-template picker.

        A teacher publishing a lab has to name a ``vm_template``, and until
        now that was a free-text box whose correct values lived only in a
        runbook — a typo surfaced as a provisioning failure minutes later,
        on the student's screen. This lets the UI offer the real list."""
        vms = self._get(f"/nodes/{self._node}/qemu") or []
        out = [
            {
                "name": vm.get("name") or str(vm.get("vmid")),
                "vmid": int(vm.get("vmid")),
                "cpu": int(vm.get("cpus") or 0),
                "ram_mb": int((vm.get("maxmem") or 0) // (1024 * 1024)),
            }
            for vm in vms
            if vm.get("template")
        ]
        out.sort(key=lambda r: r["name"].lower())
        return out

    def _remove_vmid(self, vmid: int) -> None:
        try:
            upid = self._post(f"/nodes/{self._node}/qemu/{vmid}/status/stop")
            self._wait_task(upid)
        except ProxmoxError as exc:
            logger.warning("proxmox: stop before destroy failed for %s: %s", vmid, exc)
        upid = self._delete(f"/nodes/{self._node}/qemu/{vmid}")
        self._wait_task(upid)

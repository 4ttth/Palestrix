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

logger = logging.getLogger("palestrix.proxmox")


class ProxmoxError(RuntimeError):
    pass


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
        self._client = client or httpx.Client(
            base_url=f"{settings.proxmox_host.rstrip('/')}/api2/json",
            headers={
                "Authorization": "PVEAPIToken="
                f"{settings.proxmox_token_id}={settings.proxmox_token_secret}"
            },
            verify=settings.proxmox_verify_tls,
            timeout=settings.proxmox_timeout_seconds,
        )

    # -- API plumbing -------------------------------------------------------------

    def _get(self, path: str):
        resp = self._client.get(path)
        if resp.status_code >= 400:
            raise ProxmoxError(f"GET {path} -> {resp.status_code}: {resp.text[:200]}")
        return resp.json().get("data")

    def _post(self, path: str, **data):
        resp = self._client.post(path, data=data or None)
        if resp.status_code >= 400:
            raise ProxmoxError(f"POST {path} -> {resp.status_code}: {resp.text[:200]}")
        return resp.json().get("data")

    def _delete(self, path: str):
        resp = self._client.delete(path)
        if resp.status_code >= 400:
            raise ProxmoxError(f"DELETE {path} -> {resp.status_code}: {resp.text[:200]}")
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

    def _agent_ipv4(self, vmid: int) -> str:
        """Poll the guest agent for the first non-loopback IPv4. The agent
        needs a little while after boot; 500s until then are expected."""
        deadline = time.monotonic() + self._timeout
        path = f"/nodes/{self._node}/qemu/{vmid}/agent/network-get-interfaces"
        while True:
            try:
                data = self._get(path) or {}
                for iface in data.get("result", []):
                    if iface.get("name") in ("lo", "Loopback"):
                        continue
                    for addr in iface.get("ip-addresses", []):
                        ip = addr.get("ip-address", "")
                        if addr.get("ip-address-type") == "ipv4" and not ip.startswith("127."):
                            return ip
            except ProxmoxError:
                pass  # agent not up yet
            if time.monotonic() > deadline:
                raise ProxmoxError(f"guest agent on vmid {vmid} never reported an address")
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
        self._post(f"/nodes/{self._node}/qemu/{vmid}/config", net0=net0)

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
            instance.host = self._agent_ipv4(vmid)
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

    def upload_iso(self, filename: str, data: bytes) -> str:
        """Forward an admin-uploaded ISO to the cluster's ISO storage
        (``POST /nodes/{node}/storage/{storage}/upload``), so templates can
        be built from it without touching the Proxmox UI — the Phase 7
        hardened-runbook path (docs/usecase-a-baremetal.md §Layer 1 step 5)."""
        resp = self._client.post(
            f"/nodes/{self._node}/storage/{self._iso_storage}/upload",
            data={"content": "iso"},
            files={"filename": (filename, data, "application/x-iso9660-image")},
        )
        if resp.status_code >= 400:
            raise ProxmoxError(
                f"iso upload -> {resp.status_code}: {resp.text[:200]}"
            )
        upid = resp.json().get("data")
        if upid:
            self._wait_task(upid)
        return f"{self._iso_storage}:iso/{filename}"

    def _remove_vmid(self, vmid: int) -> None:
        try:
            upid = self._post(f"/nodes/{self._node}/qemu/{vmid}/status/stop")
            self._wait_task(upid)
        except ProxmoxError as exc:
            logger.warning("proxmox: stop before destroy failed for %s: %s", vmid, exc)
        upid = self._delete(f"/nodes/{self._node}/qemu/{vmid}")
        self._wait_task(upid)

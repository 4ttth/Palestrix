"""OpenNebula cloud-layer adapter: tenants as Group + VDC + virtual network.

Talks XML-RPC to the OpenNebula front-end (``oned``, usually
``http://host:2633/RPC2``) with a service account — the same interface the
CLI tools use. One tenant materializes as (docs/usecase-a-baremetal.md
§Layer 2, Option 1):

- a **Group** named after the tenant slug, carrying the VM quota
  (VMS/CPU/MEMORY mapped from the PalestrIX tenant caps),
- a **VDC** ``vdc-<tenant>`` the group is added to (the site attaches its
  hosts and datastores to the VDC out of band),
- a **virtual network** ``net-<tenant>``: 802.1Q on the trunk device, the
  tenant's VLAN tag, one address range covering the tenant CIDR.

Idempotent by name: every call starts from the pool listings, so re-running
``ensure_tenant`` converges. Activated when PALESTRIX_CLOUD_BACKEND is
``opennebula`` and an endpoint is set; tests inject an ``httpx.Client`` built
on a MockTransport.
"""

from __future__ import annotations

import ipaddress
import logging
import xmlrpc.client
from xml.etree import ElementTree as ET

import httpx

from ..config import get_settings
from . import allocate_cidr, allocate_vlan

logger = logging.getLogger("palestrix.tenancy.opennebula")


class OpenNebulaError(RuntimeError):
    pass


class OpenNebulaCloud:
    name = "opennebula"

    def __init__(self, client: httpx.Client | None = None) -> None:
        settings = get_settings()
        self._session = (
            f"{settings.opennebula_username}:{settings.opennebula_password}"
        )
        self._phydev = settings.opennebula_phydev
        self._client = client or httpx.Client(
            base_url=settings.opennebula_endpoint,
            timeout=settings.opennebula_timeout_seconds,
        )

    # -- XML-RPC plumbing --------------------------------------------------------

    def _call(self, method: str, *args):
        """One RPC round trip. OpenNebula answers [success, body, errcode];
        a failed call carries its error message in the body."""
        payload = xmlrpc.client.dumps((self._session, *args), methodname=method)
        resp = self._client.post(
            "", content=payload.encode(), headers={"Content-Type": "text/xml"}
        )
        if resp.status_code >= 400:
            raise OpenNebulaError(f"{method} -> HTTP {resp.status_code}")
        (result,), _ = xmlrpc.client.loads(resp.content)
        success, body = result[0], result[1]
        if not success:
            raise OpenNebulaError(f"{method}: {body}")
        return body

    def _pool(self, method: str, element: str, *args) -> dict[str, int]:
        """Pool listing as name -> id, the basis of idempotency."""
        xml = self._call(method, *args)
        root = ET.fromstring(xml)
        return {
            node.findtext("NAME"): int(node.findtext("ID"))
            for node in root.findall(element)
            if node.findtext("NAME") and node.findtext("ID")
        }

    def _set_quota(self, group_id: int, tenant) -> None:
        template = (
            "VM = [\n"
            f"  VMS = {tenant.instance_quota},\n"
            f"  CPU = {tenant.cpu_cap},\n"
            f"  MEMORY = {tenant.ram_cap_gb * 1024}\n"
            "]"
        )
        self._call("one.group.quota", group_id, template)

    # -- TenantCloud contract ------------------------------------------------------

    def ensure_tenant(self, db, tenant) -> None:
        groups = self._pool("one.grouppool.info", "GROUP")
        group_id = groups.get(tenant.id)
        if group_id is None:
            group_id = int(self._call("one.group.allocate", tenant.id))
            logger.info("tenant %s: allocated group %s", tenant.id, group_id)

        tenant.vlan_id = allocate_vlan(db, tenant)
        tenant.network_cidr = allocate_cidr(db, tenant)

        vnet_name = f"net-{tenant.id}"
        vnets = self._pool("one.vnpool.info", "VNET", -2, -1, -1)
        vnet_id = vnets.get(vnet_name)
        if vnet_id is None:
            net = ipaddress.ip_network(tenant.network_cidr)
            first_host = str(net.network_address + 1)
            template = (
                f'NAME = "{vnet_name}"\n'
                'VN_MAD = "802.1Q"\n'
                f'PHYDEV = "{self._phydev}"\n'
                f'VLAN_ID = "{tenant.vlan_id}"\n'
                'AUTOMATIC_VLAN_ID = "NO"\n'
                f'AR = [ TYPE = "IP4", IP = "{first_host}", SIZE = "{net.num_addresses - 2}" ]'
            )
            vnet_id = int(self._call("one.vn.allocate", template, -1))
            logger.info("tenant %s: allocated vnet %s (vlan %s)", tenant.id, vnet_id, tenant.vlan_id)

        vdc_name = f"vdc-{tenant.id}"
        vdcs = self._pool("one.vdcpool.info", "VDC")
        vdc_id = vdcs.get(vdc_name)
        if vdc_id is None:
            vdc_id = int(self._call("one.vdc.allocate", f'NAME = "{vdc_name}"'))
            self._call("one.vdc.addgroup", vdc_id, group_id)

        self._set_quota(group_id, tenant)
        tenant.cloud_ref = f"opennebula:group={group_id} vdc={vdc_id} vnet={vnet_id}"

    def sync_quota(self, db, tenant) -> None:
        group_id = self._pool("one.grouppool.info", "GROUP").get(tenant.id)
        if group_id is None:
            self.ensure_tenant(db, tenant)  # converge instead of failing
            return
        self._set_quota(group_id, tenant)

    def retire_tenant(self, db, tenant) -> None:
        """Tear down what ensure_tenant built (missing pieces are fine — a
        half-retired tenant retires the rest on the next call). The registry
        keeps the VLAN and CIDR reserved; see LocalCloud.retire_tenant."""
        vnet_id = self._pool("one.vnpool.info", "VNET", -2, -1, -1).get(f"net-{tenant.id}")
        if vnet_id is not None:
            self._call("one.vn.delete", vnet_id)
        vdc_id = self._pool("one.vdcpool.info", "VDC").get(f"vdc-{tenant.id}")
        if vdc_id is not None:
            self._call("one.vdc.delete", vdc_id)
        group_id = self._pool("one.grouppool.info", "GROUP").get(tenant.id)
        if group_id is not None:
            self._call("one.group.delete", group_id)
        tenant.cloud_ref = "opennebula:retired"

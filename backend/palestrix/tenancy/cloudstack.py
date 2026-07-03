"""Apache CloudStack cloud-layer adapter: tenants as Domain + Account.

Talks to the CloudStack HTTP API (``/client/api``) with an API/secret key
pair, using the standard request signature: parameters sorted by name,
URL-encoded and lowercased, HMAC-SHA1 with the secret key, base64. One
tenant materializes as (docs/usecase-a-baremetal.md §Layer 2, Option 2):

- a **Domain** named after the tenant slug,
- a service **Account** in that domain (owner of the tenant's resources),
- domain **resource limits** mapped from the PalestrIX tenant caps
  (type 0 = instances, 8 = vCPU, 9 = memory in MB),
- an isolated guest **network** ``net-<tenant>`` on the tenant CIDR.

Idempotent by name via the list* calls. Activated when
PALESTRIX_CLOUD_BACKEND is ``cloudstack`` and an endpoint is set; tests
inject an ``httpx.Client`` built on a MockTransport and verify the signature
scheme against a recomputed HMAC.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import logging
import secrets
from urllib.parse import quote

import httpx

from ..config import get_settings
from . import allocate_cidr, allocate_vlan

logger = logging.getLogger("palestrix.tenancy.cloudstack")

# updateResourceLimit resource types (CloudStack API constants).
RESOURCE_INSTANCES = 0
RESOURCE_CPU = 8
RESOURCE_MEMORY_MB = 9


class CloudStackError(RuntimeError):
    pass


class CloudStackCloud:
    name = "cloudstack"

    def __init__(self, client: httpx.Client | None = None) -> None:
        settings = get_settings()
        self._api_key = settings.cloudstack_api_key
        self._secret_key = settings.cloudstack_secret_key
        self._zone_id = settings.cloudstack_zone_id
        self._offering_id = settings.cloudstack_network_offering_id
        self._client = client or httpx.Client(
            base_url=settings.cloudstack_endpoint,
            verify=settings.cloudstack_verify_tls,
            timeout=settings.cloudstack_timeout_seconds,
        )

    # -- signed-request plumbing ---------------------------------------------------

    def _sign(self, params: dict[str, str]) -> str:
        canonical = "&".join(
            f"{key.lower()}={quote(value, safe='*').lower()}"
            for key, value in sorted(params.items())
        )
        digest = hmac.new(
            self._secret_key.encode(), canonical.encode(), hashlib.sha1
        ).digest()
        return base64.b64encode(digest).decode()

    def _call(self, command: str, **params) -> dict:
        query = {
            "command": command,
            "response": "json",
            "apikey": self._api_key,
            **{k: str(v) for k, v in params.items() if v is not None},
        }
        query["signature"] = self._sign(
            {k: v for k, v in query.items() if k != "signature"}
        )
        resp = self._client.get("", params=query)
        if resp.status_code >= 400:
            raise CloudStackError(
                f"{command} -> HTTP {resp.status_code}: {resp.text[:200]}"
            )
        body = resp.json()
        # Responses wrap under "<command>response" (lowercased).
        key = next(iter(body), "")
        payload = body.get(key, {})
        if isinstance(payload, dict) and payload.get("errortext"):
            raise CloudStackError(f"{command}: {payload['errortext']}")
        return payload if isinstance(payload, dict) else {}

    def _domain_id(self, tenant) -> str | None:
        domains = self._call("listDomains", name=tenant.id, listall="true").get(
            "domain", []
        )
        return domains[0]["id"] if domains else None

    def _sync_limits(self, domain_id: str, tenant) -> None:
        for rtype, ceiling in (
            (RESOURCE_INSTANCES, tenant.instance_quota),
            (RESOURCE_CPU, tenant.cpu_cap),
            (RESOURCE_MEMORY_MB, tenant.ram_cap_gb * 1024),
        ):
            self._call(
                "updateResourceLimit",
                resourcetype=rtype,
                max=ceiling,
                domainid=domain_id,
            )

    # -- TenantCloud contract --------------------------------------------------------

    def ensure_tenant(self, db, tenant) -> None:
        domain_id = self._domain_id(tenant)
        if domain_id is None:
            created = self._call("createDomain", name=tenant.id)
            domain_id = created.get("domain", {}).get("id", "")
            logger.info("tenant %s: created domain %s", tenant.id, domain_id)

        accounts = self._call("listAccounts", domainid=domain_id, listall="true").get(
            "account", []
        )
        if not accounts:
            # The service account owns the tenant's resources. Nobody logs in
            # with it; the password is discarded on purpose.
            self._call(
                "createAccount",
                domainid=domain_id,
                accounttype=0,
                username=f"svc-{tenant.id}",
                firstname="PalestrIX",
                lastname=tenant.id,
                email=f"{tenant.id}@palestrix.invalid",
                password=secrets.token_urlsafe(24),
            )

        self._sync_limits(domain_id, tenant)

        tenant.vlan_id = allocate_vlan(db, tenant)
        tenant.network_cidr = allocate_cidr(db, tenant)
        networks = self._call("listNetworks", domainid=domain_id, listall="true").get(
            "network", []
        )
        if not any(n.get("name") == f"net-{tenant.id}" for n in networks):
            net = ipaddress.ip_network(tenant.network_cidr)
            self._call(
                "createNetwork",
                name=f"net-{tenant.id}",
                displaytext=f"PalestrIX tenant {tenant.id}",
                zoneid=self._zone_id,
                networkofferingid=self._offering_id,
                domainid=domain_id,
                acltype="Domain",
                gateway=str(net.network_address + 1),
                netmask=str(net.netmask),
                vlan=tenant.vlan_id,
            )
        tenant.cloud_ref = f"cloudstack:domain={domain_id}"

    def sync_quota(self, db, tenant) -> None:
        domain_id = self._domain_id(tenant)
        if domain_id is None:
            self.ensure_tenant(db, tenant)  # converge instead of failing
            return
        self._sync_limits(domain_id, tenant)

    def retire_tenant(self, db, tenant) -> None:
        """deleteDomain with cleanup removes the account, network, and any
        straggler resources in one call; the registry keeps the VLAN and CIDR
        reserved (see LocalCloud.retire_tenant)."""
        domain_id = self._domain_id(tenant)
        if domain_id is not None:
            self._call("deleteDomain", id=domain_id, cleanup="true")
        tenant.cloud_ref = "cloudstack:retired"

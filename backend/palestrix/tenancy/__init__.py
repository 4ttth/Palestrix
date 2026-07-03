"""Phase 7 multitenant cloud layer (docs/architecture.md §Multitenant cloud
layer, docs/usecase-a-baremetal.md §Layer 2).

A tenant is the isolation unit: its own network, naming prefix, and quota
pool. This module is where a tenant row becomes real infrastructure. It
mirrors the Phase 4 provider and Phase 6 detonator registries: core ships a
built-in ``LocalCloud`` that does honest registry-side allocation (VLAN tag,
tenant CIDR) with no external manager, and configuration swaps in an adapter
that additionally materializes the tenant in OpenNebula (group + VDC +
virtual network) or Apache CloudStack (domain + account + network). Pick one
per site; the API contract is identical for all three.

The API is the only caller: ``ensure_tenant`` on create, ``sync_quota`` on
quota edits, ``retire_tenant`` on archive (refused while the tenant still
holds active instances). Adapters mutate the tenant row (``vlan_id``,
``network_cidr``, ``cloud_ref``) and leave the commit to the endpoint.
"""

from __future__ import annotations

import ipaddress
import logging
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ..models import Tenant

logger = logging.getLogger("palestrix.tenancy")


@runtime_checkable
class TenantCloud(Protocol):
    """The cloud-layer contract. All three operations are idempotent: adapters
    look their objects up by tenant-derived names, never by remembered ids, so
    a re-run converges instead of duplicating."""

    name: str

    def ensure_tenant(self, db: "Session", tenant: "Tenant") -> None: ...

    def sync_quota(self, db: "Session", tenant: "Tenant") -> None: ...

    def retire_tenant(self, db: "Session", tenant: "Tenant") -> None: ...


# -- shared allocation helpers ---------------------------------------------------
#
# Every backend needs a VLAN tag and a tenant CIDR; the registry is the
# source of truth for what is taken (docs/ephemeral-lifecycle.md invariants:
# an archived tenant keeps its VLAN and CIDR so a new tenant can never
# inherit a network that old records still reference).


def allocate_vlan(db: "Session", tenant: "Tenant") -> int:
    """Lowest free tag in [PALESTRIX_TENANT_VLAN_MIN, .._MAX]."""
    from sqlalchemy import select

    from ..config import get_settings
    from ..models import Tenant

    if tenant.vlan_id:
        return tenant.vlan_id
    settings = get_settings()
    taken = set(
        db.scalars(select(Tenant.vlan_id).where(Tenant.vlan_id.is_not(None))).all()
    )
    for tag in range(settings.tenant_vlan_min, settings.tenant_vlan_max + 1):
        if tag not in taken:
            return tag
    raise RuntimeError(
        f"tenant VLAN range {settings.tenant_vlan_min}-{settings.tenant_vlan_max} "
        "is exhausted; raise PALESTRIX_TENANT_VLAN_MAX"
    )


def allocate_cidr(db: "Session", tenant: "Tenant") -> str:
    """The admin may pin a CIDR at create time; otherwise carve the next free
    /24 out of PALESTRIX_TENANT_CIDR_POOL."""
    from sqlalchemy import select

    from ..config import get_settings
    from ..models import Tenant

    if tenant.network_cidr:
        return tenant.network_cidr
    settings = get_settings()
    pool = ipaddress.ip_network(settings.tenant_cidr_pool)
    taken = {
        cidr
        for cidr in db.scalars(
            select(Tenant.network_cidr).where(Tenant.network_cidr != "")
        ).all()
    }
    for subnet in pool.subnets(new_prefix=24):
        if str(subnet) not in taken:
            return str(subnet)
    raise RuntimeError(f"tenant CIDR pool {pool} is exhausted")


class LocalCloud:
    """Built-in default: registry-only tenancy. Allocates the VLAN tag and
    tenant CIDR that the Phase 4 adapters isolate with (Proxmox tags ``net0``,
    Docker pins the bridge subnet); quotas are enforced by the API itself, so
    there is nothing external to push them to. A deployment that wants
    self-service inside limits fronts the hypervisor with OpenNebula or
    CloudStack instead (PALESTRIX_CLOUD_BACKEND)."""

    name = "local"

    def ensure_tenant(self, db, tenant) -> None:
        tenant.vlan_id = allocate_vlan(db, tenant)
        tenant.network_cidr = allocate_cidr(db, tenant)
        tenant.cloud_ref = f"local:vlan={tenant.vlan_id}"
        logger.info(
            "tenant %s materialized: vlan %s, cidr %s",
            tenant.id,
            tenant.vlan_id,
            tenant.network_cidr,
        )

    def sync_quota(self, db, tenant) -> None:
        pass  # quotas live in the registry; the API is the enforcement point

    def retire_tenant(self, db, tenant) -> None:
        # The VLAN and CIDR stay assigned: instance history references this
        # network, and reissuing it to a new tenant would let stale rules or
        # records bleed across the isolation boundary.
        logger.info("tenant %s archived; vlan %s stays reserved", tenant.id, tenant.vlan_id)


_cloud: TenantCloud = LocalCloud()


def register_cloud(cloud: TenantCloud) -> None:
    global _cloud
    _cloud = cloud


def active_cloud() -> TenantCloud:
    return _cloud


def activate_configured_cloud() -> None:
    """Called at startup (API lifespan and the worker). LocalCloud answers
    unless PALESTRIX_CLOUD_BACKEND names an adapter with its endpoint set."""
    from ..config import get_settings

    settings = get_settings()
    if settings.cloud_backend == "opennebula" and settings.opennebula_endpoint:
        from .opennebula import OpenNebulaCloud

        register_cloud(OpenNebulaCloud())
        logger.info("opennebula cloud layer active (%s)", settings.opennebula_endpoint)
    elif settings.cloud_backend == "cloudstack" and settings.cloudstack_endpoint:
        from .cloudstack import CloudStackCloud

        register_cloud(CloudStackCloud())
        logger.info("cloudstack cloud layer active (%s)", settings.cloudstack_endpoint)

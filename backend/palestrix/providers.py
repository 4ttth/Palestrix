"""Instance provider registry: the first plugin extension point.

Core registers the built-in demo provider (containers and VMs, instant
provisioning; replaced by the Proxmox and Docker adapters in Phase 4).
Plugins register additional providers with new kinds through
PluginContext.providers. A plugin-owned provider is only active while its
plugin is enabled.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Protocol, runtime_checkable

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from .models import Instance, LabTemplate


@runtime_checkable
class InstanceProvider(Protocol):
    """Phase 2b contract: provision + destroy. Phase 4 extends this with
    expose(), stop(), and stream_logs() when real adapters land."""

    name: str
    kinds: tuple[str, ...]

    def provision(
        self, db: "Session", instance: "Instance", template: "LabTemplate"
    ) -> None: ...

    def destroy(self, db: "Session", instance: "Instance") -> None: ...


@dataclass
class _Entry:
    provider: InstanceProvider
    owner_plugin: str | None  # None = core, always active


_by_kind: dict[str, _Entry] = {}
_enabled_check: Callable[[str], bool] = lambda plugin_id: False


def set_enablement_checker(fn: Callable[[str], bool]) -> None:
    """Called once by the plugin registry so provider activation follows
    plugin enablement without an import cycle."""
    global _enabled_check
    _enabled_check = fn


def register_provider(
    provider: InstanceProvider, owner_plugin: str | None = None
) -> None:
    for kind in provider.kinds:
        existing = _by_kind.get(kind)
        if existing and existing.owner_plugin != owner_plugin:
            raise ValueError(
                f"instance kind '{kind}' is already claimed by "
                f"{existing.owner_plugin or 'core'}"
            )
        _by_kind[kind] = _Entry(provider=provider, owner_plugin=owner_plugin)


def _entry_active(entry: _Entry) -> bool:
    return entry.owner_plugin is None or _enabled_check(entry.owner_plugin)


def provider_for_kind(kind: str) -> InstanceProvider | None:
    entry = _by_kind.get(kind)
    if entry is None or not _entry_active(entry):
        return None
    return entry.provider


def known_kinds() -> set[str]:
    """Kinds that can be published and launched right now."""
    return {kind for kind, entry in _by_kind.items() if _entry_active(entry)}


def add_log(db: "Session", instance_id: str, msg: str, level: str = "info") -> None:
    from .models import InstanceLog

    db.add(InstanceLog(instance_id=instance_id, msg=msg, level=level))


class DemoProvider:
    """Built-in placeholder provider: instant transitions with real registry
    side effects (states, logs, endpoints). Swapped for the Proxmox and
    Docker adapters in Phase 4."""

    name = "demo"
    kinds = ("container", "vm")

    def provision(self, db, instance, template) -> None:
        from .models import InstanceState

        add_log(db, instance.id, f"queue: job accepted (tenant {instance.tenant_id})")
        if template.kind == "container":
            add_log(db, instance.id, f"docker: building image from {template.archive_key}")
        else:
            add_log(db, instance.id, f"proxmox: cloning template {template.vm_template}")
        add_log(db, instance.id, "network: attached to tenant-isolated bridge")
        instance.node = "demo-01"
        instance.host = f"10.99.{secrets.randbelow(200) + 1}.{secrets.randbelow(200) + 20}"
        instance.port = secrets.randbelow(20000) + 20000
        instance.proto = "vnc" if template.access_mode == "gui" else "ssh"
        instance.state = InstanceState.running
        add_log(
            db,
            instance.id,
            f"instance running, {instance.proto} exposed on {instance.host}:{instance.port}",
            level="ok",
        )

    def destroy(self, db, instance) -> None:
        add_log(db, instance.id, "instance stopped and destroyed", level="warn")


register_provider(DemoProvider())

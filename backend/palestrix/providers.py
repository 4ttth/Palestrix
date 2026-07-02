"""Instance provider registry: the first plugin extension point.

Core registers the built-in demo provider; the Phase 4 Proxmox and Docker
adapters (palestrix/orchestration/) take over their kinds when configured.
Plugins register additional providers with new kinds through
PluginContext.providers. A plugin-owned provider is only active while its
plugin is enabled.

Adapters must be idempotent by instance id (docs/ephemeral-lifecycle.md):
a re-run provision for the same instance reuses or replaces the resource,
never duplicates it. Log lines go through add_log; the API relays them to
clients over SSE, so the log rows are the live progress stream.
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
    """The Phase 4 contract. provision() and destroy() are required; stop()
    is optional (Phase 2b plugins predate it) — core calls it through
    provider_stop(), which no-ops when absent. provision() fills the access
    fields (host/port/proto) and moves the instance to `running`."""

    name: str
    kinds: tuple[str, ...]

    def provision(
        self, db: "Session", instance: "Instance", template: "LabTemplate"
    ) -> None: ...

    def destroy(self, db: "Session", instance: "Instance") -> None: ...


def provider_stop(
    provider: InstanceProvider, db: "Session", instance: "Instance"
) -> None:
    """Graceful stop where the provider supports it; providers from the
    Phase 2b contract (provision/destroy only) just skip it."""
    stop = getattr(provider, "stop", None)
    if callable(stop):
        stop(db, instance)


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


def active_providers() -> list[InstanceProvider]:
    """Each active provider once, even when it claims several kinds. The
    reaper's reconciliation pass walks these."""
    seen: list[InstanceProvider] = []
    for entry in _by_kind.values():
        if _entry_active(entry) and entry.provider not in seen:
            seen.append(entry.provider)
    return seen


def add_log(db: "Session", instance_id: str, msg: str, level: str = "info") -> None:
    from .models import InstanceLog

    db.add(InstanceLog(instance_id=instance_id, msg=msg, level=level))


class DemoProvider:
    """Built-in placeholder provider: instant transitions with real registry
    side effects (states, logs, endpoints). The development and test default;
    the real Proxmox and Docker adapters (palestrix/orchestration/) take over
    their kinds when configured (PALESTRIX_PROXMOX_HOST /
    PALESTRIX_DOCKER_ENABLED)."""

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

    def stop(self, db, instance) -> None:
        add_log(db, instance.id, "instance stopped", level="warn")

    def destroy(self, db, instance) -> None:
        add_log(db, instance.id, "instance stopped and destroyed", level="warn")


register_provider(DemoProvider())

"""Phase 4 orchestration: the job queue, the provider adapters, and the TTL
reaper (docs/architecture.md §Orchestration service).

Configuration decides what is real: the demo provider owns "container" and
"vm" out of the box; setting PALESTRIX_PROXMOX_HOST hands "vm" to the
Proxmox adapter, and PALESTRIX_DOCKER_ENABLED hands "container" to the
Docker adapter. The HTTP contract is identical for all of them.
"""

from __future__ import annotations

import logging

from ..config import get_settings
from ..providers import register_provider

logger = logging.getLogger("palestrix.orchestration")


def activate_configured_adapters() -> None:
    """Called at startup (API lifespan and the worker). Re-registering a
    core-owned kind overwrites the demo provider for that kind only."""
    settings = get_settings()
    if settings.proxmox_host:
        from .proxmox import ProxmoxProvider

        register_provider(ProxmoxProvider())
        logger.info("proxmox adapter active for 'vm' (%s)", settings.proxmox_host)
    if settings.docker_enabled:
        from .docker import DockerProvider

        register_provider(DockerProvider())
        logger.info("docker adapter active for 'container'")

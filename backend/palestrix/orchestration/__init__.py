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
        from .proxmox import ProxmoxProvider, _clean_credential

        # Fail loud on the config that produces an opaque "401 invalid token
        # value!" at launch time: host set, but the token id or secret blank
        # (a missing/misspelled/overridden env var). Cheaper to catch here
        # than in every worker's provision log.
        if not _clean_credential("PALESTRIX_PROXMOX_TOKEN_ID", settings.proxmox_token_id):
            logger.error(
                "proxmox adapter active but PALESTRIX_PROXMOX_TOKEN_ID is empty; "
                "launches will 401"
            )
        if not _clean_credential(
            "PALESTRIX_PROXMOX_TOKEN_SECRET", settings.proxmox_token_secret
        ):
            logger.error(
                "proxmox adapter active but PALESTRIX_PROXMOX_TOKEN_SECRET is empty; "
                "the cluster will answer 401 'invalid token value'. Check the env "
                "the service actually reads (systemd WorkingDirectory / "
                "EnvironmentFile, or a shell export overriding the .env)."
            )
        register_provider(ProxmoxProvider())
        logger.info("proxmox adapter active for 'vm' (%s)", settings.proxmox_host)
    if settings.docker_enabled:
        from .docker import DockerProvider

        register_provider(DockerProvider())
        logger.info("docker adapter active for 'container'")

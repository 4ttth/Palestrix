"""Docker adapter: real containers from teacher archives.

Drives the local ``docker`` CLI (works identically against Docker Engine and
Docker Desktop, no daemon-socket portability problems). The archive a
teacher uploaded at publish time is fed to ``docker build`` as the build
context on stdin — Docker accepts a (gzipped) tar stream directly, so
nothing is unpacked to disk.

Idempotency is by instance id: every container carries a
``palestrix.instance=<id>`` label, and provision/stop/destroy find their
container through that label rather than remembering ids. Tenant isolation
maps to one bridge network per tenant (``net-<tenant_id>``), matching the
naming in docs/ephemeral-lifecycle.md.

Activated for the "container" kind when PALESTRIX_DOCKER_ENABLED is true;
otherwise the demo provider keeps the kind. The ``runner`` argument exists
for tests, which inject a fake in place of subprocess.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Callable

from ..config import get_settings
from ..models import ACTIVE_STATES, Instance, InstanceState, Tenant
from ..providers import add_log
from ..storage import get_storage

logger = logging.getLogger("palestrix.docker")

# runner(args, input_bytes) -> stdout text; raises DockerError on failure
Runner = Callable[..., str]


class DockerError(RuntimeError):
    pass


def _subprocess_runner(args: list[str], input_bytes: bytes | None = None) -> str:
    settings = get_settings()
    proc = subprocess.run(
        [settings.docker_binary, *args],
        input=input_bytes,
        capture_output=True,
        timeout=600,
    )
    if proc.returncode != 0:
        raise DockerError(
            f"docker {' '.join(args[:2])} failed: "
            f"{proc.stderr.decode(errors='replace').strip()}"
        )
    return proc.stdout.decode(errors="replace")


class DockerProvider:
    name = "docker"
    kinds = ("container",)

    def __init__(self, runner: Runner | None = None) -> None:
        self._run = runner or _subprocess_runner

    def check(self) -> str:
        """Connectivity self-test for the admin console: asks the daemon for
        its version over the same CLI path provisioning uses. Raises
        DockerError with the CLI's stderr when the daemon is unreachable."""
        version = self._run(["version", "--format", "{{.Server.Version}}"]).strip()
        return f"docker daemon reachable, server version {version or 'unknown'}"

    # -- helpers ---------------------------------------------------------------

    def _container_for(self, instance_id: str) -> str | None:
        out = self._run(
            ["ps", "-aq", "--filter", f"label=palestrix.instance={instance_id}"]
        ).strip()
        return out.splitlines()[0] if out else None

    def _ensure_network(self, db, instance) -> str:
        settings = get_settings()
        net = f"{settings.docker_network_prefix}{instance.tenant_id}"
        existing = self._run(["network", "ls", "--format", "{{.Name}}"]).splitlines()
        if net not in existing:
            args = [
                "network",
                "create",
                "--driver",
                "bridge",
                "--label",
                f"palestrix.tenant={instance.tenant_id}",
            ]
            # The tenant fixes the network: its CIDR pins the bridge subnet
            # (docs/ephemeral-lifecycle.md §Multitenancy invariants).
            tenant = db.get(Tenant, instance.tenant_id)
            if tenant is not None and tenant.network_cidr:
                args += ["--subnet", tenant.network_cidr]
            self._run([*args, net])
            add_log(db, instance.id, f"network: created tenant-isolated bridge {net}")
        else:
            add_log(db, instance.id, f"network: attached to tenant bridge {net}")
        return net

    def _ensure_image(self, db, instance, template) -> str:
        name, _, version = template.slug.partition(":")
        image = f"palestrix/labs/{name}:{version or 'latest'}"
        if self._run(["images", "-q", image]).strip():
            add_log(db, instance.id, f"docker: image {image} found in local cache")
            return image
        if not template.archive_key:
            raise DockerError("container template has no build archive")
        bucket, _, key = template.archive_key.partition("/")
        context = get_storage().get(bucket, key)
        add_log(db, instance.id, f"docker: building {image} from {template.archive_key}")
        self._run(["build", "-t", image, "-"], input_bytes=context)
        add_log(db, instance.id, f"docker: image {image} built", level="ok")
        return image

    # -- provider contract -------------------------------------------------------

    def provision(self, db, instance, template) -> None:
        settings = get_settings()
        add_log(db, instance.id, f"queue: job accepted (tenant {instance.tenant_id})")

        # Idempotent by instance id: a retry replaces the previous attempt.
        leftover = self._container_for(instance.id)
        if leftover:
            add_log(db, instance.id, "docker: replacing leftover container from a prior attempt", level="warn")
            self._run(["rm", "-f", leftover])

        net = self._ensure_network(db, instance)
        image = self._ensure_image(db, instance, template)

        cid = self._run(
            [
                "run",
                "-d",
                "--label",
                f"palestrix.instance={instance.id}",
                "--label",
                f"palestrix.tenant={instance.tenant_id}",
                "--network",
                net,
                "--memory",
                settings.docker_memory_limit,
                "--cpus",
                settings.docker_cpu_limit,
                "-P",  # publish exposed ports on ephemeral host ports
                image,
            ]
        ).strip()
        add_log(db, instance.id, f"container: started {cid[:12]}, healthcheck pending")

        port = 0
        for line in self._run(["port", cid]).splitlines():
            # e.g. "22/tcp -> 0.0.0.0:49155"
            if "->" in line:
                port = int(line.rsplit(":", 1)[1])
                break
        instance.node = f"docker/{cid[:12]}"
        instance.host = settings.docker_host_address
        instance.port = port
        instance.proto = "vnc" if template.access_mode == "gui" else "ssh"
        instance.state = InstanceState.running
        add_log(
            db,
            instance.id,
            f"instance running, {instance.proto} exposed on {instance.host}:{instance.port}",
            level="ok",
        )

    def read_files(self, db, instance, paths: list[str]) -> dict[str, str | None]:
        """Automated-checking probe: hash files inside the live container.
        One ``docker exec sha256sum`` per path; a missing file (or an exec
        against a container that is gone) reads as absent — the checker
        treats absence as its own answer, never an error."""
        cid = self._container_for(instance.id)
        if cid is None:
            raise DockerError("container not found for grading probe")
        observed: dict[str, str | None] = {}
        for path in paths:
            quoted = "'" + path.replace("'", "'\\''") + "'"
            out = self._run(
                ["exec", cid, "sh", "-c", f"sha256sum {quoted} 2>/dev/null || true"]
            ).strip()
            observed[path] = out.split()[0] if out else None
        return observed

    def stop(self, db, instance) -> None:
        cid = self._container_for(instance.id)
        if cid:
            self._run(["stop", cid])
            add_log(db, instance.id, "container: stopped", level="warn")

    def destroy(self, db, instance) -> None:
        cid = self._container_for(instance.id)
        if cid:
            self._run(["rm", "-f", cid])
            add_log(db, instance.id, "container: stopped and removed", level="warn")
        else:
            add_log(db, instance.id, "container: already gone", level="warn")

    def reconcile(self, db) -> None:
        """Orphans in both directions: labeled containers without a live
        registry row are removed; running rows without a container are marked
        expired (the 'node dies' policy — quota released, student relaunches)."""
        out = self._run(["ps", "-aq", "--filter", "label=palestrix.instance"]).strip()
        live_ids: set[str] = set()
        for cid in out.splitlines():
            iid = self._run(
                ["inspect", "-f", '{{index .Config.Labels "palestrix.instance"}}', cid]
            ).strip()
            row = db.get(Instance, iid) if iid else None
            if row is None or row.state not in ACTIVE_STATES:
                logger.warning("reconcile: removing orphan container %s (%s)", cid[:12], iid)
                self._run(["rm", "-f", cid])
            else:
                live_ids.add(iid)
        from sqlalchemy import select

        for row in db.scalars(
            select(Instance).where(Instance.state == InstanceState.running)
        ).all():
            template_kind_is_ours = row.id not in live_ids
            if template_kind_is_ours and self._owns(db, row):
                add_log(db, row.id, "reconcile: container missing; marking expired", level="warn")
                row.state = InstanceState.expired

    def _owns(self, db, instance) -> bool:
        from ..models import LabTemplate

        template = db.get(LabTemplate, instance.template_id)
        return bool(template and template.kind in self.kinds)

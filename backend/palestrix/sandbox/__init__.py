"""Phase 6 malware sandbox module (docs/sandbox-security.md).

Self-contained by design: a submitted sample is hashed, stored in its own
bucket, and handed to a detonator that returns a verdict, a behavior trace,
and artifacts. The core platform touches only the sandbox rows and this
module's two public functions — everything about the isolated detonation host
stays behind the coordinator adapter.

- ``activate_configured_detonator`` runs at startup (API lifespan and the
  worker); it swaps the demo detonator for the coordinator adapter when a
  sandbox host is configured. Importing this package also registers the
  ``sandbox.detonate`` job on the platform queue.
- ``submit_run`` is the one entry point that creates a run: dedup by SHA-256,
  store the bytes, enqueue detonation.
"""

from __future__ import annotations

import logging
import secrets

from . import jobs  # noqa: F401 — registers the sandbox.detonate job handler

logger = logging.getLogger("palestrix.sandbox")

SAMPLE_BUCKET = "sandbox-samples"


def activate_configured_detonator() -> None:
    from ..config import get_settings
    from .engine import register_detonator

    settings = get_settings()
    if settings.sandbox_coordinator_url:
        from .coordinator import CoordinatorDetonator

        register_detonator(CoordinatorDetonator())
        logger.info(
            "sandbox coordinator detonator active (%s)",
            settings.sandbox_coordinator_url,
        )


def submit_run(
    db,
    *,
    submitter_id: str,
    tenant_id: str | None,
    filename: str,
    data: bytes,
    media_type: str = "application/octet-stream",
    enqueue_job: bool = True,
):
    """Create (or re-run) an analysis for ``data``. Returns the SandboxRun in
    its initial ``queued`` state and, on the inline queue, already analyzed.

    Dedup: the sample row is keyed by SHA-256, so the same bytes never store
    twice — but each submission still gets its own run (a resubmission is a
    signal, not a silent no-op; docs/sandbox-security.md)."""
    import io

    from ..models import SandboxRun, SandboxRunState, SandboxSample
    from ..orchestration.queue import enqueue
    from ..storage import get_storage
    from .analysis import sha256_bytes, sniff_magic
    from .vault import seal

    sha256 = sha256_bytes(data)
    storage = get_storage()
    sample = db.get(SandboxSample, sha256)
    if sample is None:
        magic, sniffed_media = sniff_magic(data)
        # Sealed at rest so a host AV scanner cannot quarantine the sample
        # (docs/sandbox-security.md §Data privacy). The magic/media type are
        # sniffed from the plaintext first.
        sealed = seal(data)
        storage.put(SAMPLE_BUCKET, sha256, io.BytesIO(sealed), len(sealed))
        sample = SandboxSample(
            sha256=sha256,
            filename=filename,
            size=len(data),
            media_type=media_type or sniffed_media,
            magic=magic,
            storage_key=f"{SAMPLE_BUCKET}/{sha256}",
        )
        db.add(sample)

    run = SandboxRun(
        id=f"sbx-{secrets.token_hex(4)}",
        sample_sha256=sha256,
        submitter_id=submitter_id,
        tenant_id=tenant_id,
        state=SandboxRunState.queued,
    )
    db.add(run)
    db.commit()

    if enqueue_job:
        # Inline backend: detonation finishes before we return. Redis backend:
        # the worker picks it up and the client follows the SSE event stream.
        enqueue("sandbox.detonate", run_id=run.id)
        db.refresh(run)
    return run

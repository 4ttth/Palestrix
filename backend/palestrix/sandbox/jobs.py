"""The ``sandbox.detonate`` job: the persistence half of an analysis.

Registered on the platform job queue (palestrix/orchestration/queue.py) so it
runs inline in the API process (dev/test) or on the RQ worker fleet (redis),
exactly like ``instance.provision``. The job opens its own session and works
from the run id, so it is valid in any process.

The detonator (palestrix/sandbox/engine.py) is the pure analysis unit; this
job owns state transitions, the event timeline, artifact archival to object
storage, and the ``sandbox.report.ready`` emission. State is committed at each
phase boundary so an SSE follower on a redis deployment watches the run move
queued -> static -> detonating -> completed.
"""

from __future__ import annotations

import io
import logging

from ..db import SessionLocal
from ..events import emit
from ..models import (
    SandboxEvent,
    SandboxRun,
    SandboxRunState,
    SandboxSample,
    SandboxVerdict,
    User,
    utcnow,
)
from ..orchestration.queue import job
from ..storage import get_storage
from .engine import DetonatorUnavailable, get_detonator
from .vault import seal, unseal

logger = logging.getLogger("palestrix.sandbox")

SAMPLE_BUCKET = "sandbox-samples"
REPORT_BUCKET = "sandbox-reports"


@job("sandbox.detonate")
def detonate(run_id: str) -> None:
    db = SessionLocal()
    try:
        run = db.get(SandboxRun, run_id)
        if run is None or run.state is not SandboxRunState.queued:
            return  # already handled, or gone; a stale retry is a no-op
        sample = db.get(SandboxSample, run.sample_sha256)
        if sample is None:
            _fail(db, run, "sample bytes are missing from storage")
            return

        seq = _Seq()

        def add(category: str, level: str, msg: str, data: dict | None = None) -> None:
            db.add(
                SandboxEvent(
                    run_id=run.id,
                    seq=seq.next(),
                    category=category,
                    level=level,
                    msg=msg,
                    data=data or {},
                )
            )

        add(
            "system",
            "info",
            f"submission accepted: {sample.filename} "
            f"({run.sample_sha256[:12]}…, {sample.size} bytes)",
        )
        run.state = SandboxRunState.static
        db.commit()

        try:
            data = unseal(get_storage().get(SAMPLE_BUCKET, run.sample_sha256))
        except Exception as exc:  # object store miss
            _fail(db, run, f"could not read sample from storage: {exc}")
            return

        detonator = get_detonator()
        try:
            result = detonator.analyze(sample.filename, run.sample_sha256, data)
        except DetonatorUnavailable as exc:
            add("system", "alert", f"detonation host unavailable: {exc}")
            _fail(db, run, str(exc))
            return
        except Exception as exc:  # noqa: BLE001 — record the real error, never fabricate
            logger.warning("sandbox analysis %s failed: %s", run_id, exc)
            add("system", "alert", f"analysis error: {exc}")
            _fail(db, run, str(exc))
            return

        run.detonator = detonator.name
        run.static = result.static
        run.iocs = result.iocs
        for note in result.static.get("notes", []):
            hot = "EICAR" in note or "packed" in note or "encrypted" in note
            add("static", "alert" if hot else "info", note)

        run.state = SandboxRunState.detonating
        db.commit()

        for ev in result.events:
            add(
                ev.get("category", "system"),
                ev.get("level", "info"),
                ev.get("msg", ""),
                ev.get("data"),
            )

        run.verdict = SandboxVerdict(result.verdict)
        run.score = result.score
        run.family = result.family
        run.mitre = result.mitre
        run.summary = result.summary

        storage = get_storage()
        for art in result.artifacts:
            # Sealed at rest, like samples: analysis artifacts carry IOC
            # strings a host AV would otherwise quarantine. The export endpoint
            # unseals before serving to an admin.
            sealed = seal(art.data)
            storage.put(
                REPORT_BUCKET,
                f"{run.id}/{art.name}",
                io.BytesIO(sealed),
                len(sealed),
            )
        run.report_key = f"{REPORT_BUCKET}/{run.id}/report.json"

        add(
            "system",
            "ok",
            f"analysis complete — verdict {run.verdict.value}, "
            f"score {run.score}/100",
        )
        run.state = SandboxRunState.completed
        run.completed_at = utcnow()

        submitter = db.get(User, run.submitter_id)
        emit(
            db,
            "sandbox.report.ready",
            {
                "report_id": run.id,
                "sha256": run.sample_sha256,
                "verdict": run.verdict.value,
                "score": run.score,
                "family": run.family,
                "by": submitter.handle if submitter else run.submitter_id,
            },
        )
        db.commit()
    finally:
        db.close()


class _Seq:
    def __init__(self) -> None:
        self._n = 0

    def next(self) -> int:
        n = self._n
        self._n += 1
        return n


def _fail(db, run: SandboxRun, reason: str) -> None:
    run.state = SandboxRunState.failed
    run.error = reason
    run.completed_at = utcnow()
    db.commit()

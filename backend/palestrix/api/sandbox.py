"""Sandbox API surface (Phase 6).

Every product function of the malware sandbox is here: submit a sample, list
and read reports, follow a detonation live over SSE, pull archived artifacts,
and share a report with your team. The detonation itself happens behind the
detonator abstraction (palestrix/sandbox/) — the demo detonator in dev/test,
the isolated-host coordinator in a real deployment. This router never touches
sample bytes beyond handing them to the module; raw samples are never served
back out (docs/sandbox-security.md §Handling rules).
"""

import json
import time

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas
from ..config import get_settings
from ..db import SessionLocal, get_db
from ..models import (
    SANDBOX_LIVE_STATES,
    SandboxEvent,
    SandboxRun,
    SandboxSample,
    User,
    as_utc,
)
from ..rbac import Principal
from ..sandbox import submit_run
from ..sandbox.engine import get_detonator
from ..storage import get_storage
from .deps import get_principal, require_capability

router = APIRouter(prefix="/sandbox", tags=["sandbox"])

REPORT_BUCKET = "sandbox-reports"


def _require_enabled() -> None:
    if not get_settings().sandbox_enabled:
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            "the malware sandbox module is disabled in this deployment "
            "(PALESTRIX_SANDBOX_ENABLED)",
        )


@router.get("/status", response_model=schemas.SandboxStatusOut)
def status_(principal: Principal = Depends(get_principal)):
    """What the /sandbox surface renders instead of guessing from a 501:
    whether the module is enabled and whether a live detonation host backs it
    or the demo detonator is answering."""
    settings = get_settings()
    detonator = get_detonator()
    return schemas.SandboxStatusOut(
        enabled=settings.sandbox_enabled,
        detonator=detonator.name,
        live=detonator.live,
        max_sample_mb=settings.sandbox_max_sample_mb,
        wall_clock_seconds=settings.sandbox_wall_clock_seconds,
    )


def _report_out(db: Session, run: SandboxRun) -> schemas.SandboxReportOut:
    out = schemas.SandboxReportOut.model_validate(run)
    sample = db.get(SandboxSample, run.sample_sha256)
    if sample is not None:
        out.filename = sample.filename
        out.size = sample.size
        out.media_type = sample.media_type
        out.magic = sample.magic
    submitter = db.get(User, run.submitter_id)
    out.submitter_handle = submitter.handle if submitter else ""
    out.events = db.scalar(
        select(func.count(SandboxEvent.id)).where(SandboxEvent.run_id == run.id)
    )
    earliest = db.scalar(
        select(SandboxRun.id)
        .where(SandboxRun.sample_sha256 == run.sample_sha256)
        .order_by(SandboxRun.created_at)
        .limit(1)
    )
    out.resubmission = earliest is not None and earliest != run.id
    return out


def _visible_or_403(db: Session, principal: Principal, report_id: str) -> SandboxRun:
    run = db.get(SandboxRun, report_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such report")
    if run.submitter_id == principal.user_id:
        return run
    if principal.can("sandbox:read-all"):
        return run
    # Shared reports are visible to the submitter's tenant (their "team").
    if run.shared and run.tenant_id is not None and run.tenant_id == principal.tenant_id:
        return run
    raise HTTPException(status.HTTP_403_FORBIDDEN, "not your report")


@router.post("/samples", response_model=schemas.SandboxReportOut, status_code=201)
def submit_sample(
    file: UploadFile,
    principal: Principal = Depends(require_capability("sandbox:submit")),
    db: Session = Depends(get_db),
):
    _require_enabled()
    settings = get_settings()
    limit = settings.sandbox_max_sample_mb * 1024 * 1024
    if file.size is not None and file.size > limit:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"sample exceeds the {settings.sandbox_max_sample_mb} MB limit",
        )
    data = file.file.read()
    if len(data) == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "empty submission")
    if len(data) > limit:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"sample exceeds the {settings.sandbox_max_sample_mb} MB limit",
        )

    run = submit_run(
        db,
        submitter_id=principal.user_id,
        tenant_id=principal.tenant_id,
        filename=file.filename or "sample.bin",
        data=data,
        media_type=file.content_type or "application/octet-stream",
    )
    return _report_out(db, run)


@router.get("/reports", response_model=list[schemas.SandboxReportOut])
def list_reports(
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
    all_reports: bool = False,
):
    _require_enabled()
    if all_reports:
        if not principal.can("sandbox:read-all"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
        rows = db.scalars(
            select(SandboxRun).order_by(SandboxRun.created_at.desc())
        ).all()
    else:
        # Own reports, plus reports a teammate shared into the caller's tenant.
        clauses = [SandboxRun.submitter_id == principal.user_id]
        if principal.tenant_id is not None:
            clauses.append(
                (SandboxRun.shared.is_(True))
                & (SandboxRun.tenant_id == principal.tenant_id)
            )
        from sqlalchemy import or_

        rows = db.scalars(
            select(SandboxRun)
            .where(or_(*clauses))
            .order_by(SandboxRun.created_at.desc())
        ).all()
    return [_report_out(db, r) for r in rows]


@router.get("/reports/{report_id}", response_model=schemas.SandboxReportOut)
def get_report(
    report_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    _require_enabled()
    return _report_out(db, _visible_or_403(db, principal, report_id))


@router.get("/reports/{report_id}/events", response_model=list[schemas.SandboxEventOut])
def list_events(
    report_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    """The full behavior timeline in order. The stream endpoint is the live
    view of the same rows; this one stays for replay after the run settles."""
    _require_enabled()
    _visible_or_403(db, principal, report_id)
    return db.scalars(
        select(SandboxEvent)
        .where(SandboxEvent.run_id == report_id)
        .order_by(SandboxEvent.seq)
    ).all()


@router.get("/reports/{report_id}/events/stream")
def stream_events(
    report_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    """Server-Sent Events: replay everything traced so far, then follow while
    the run is still detonating. On settle it sends a final ``state`` event and
    closes. Mirrors the instance provisioning stream so the frontend consumes
    both with one reader (lib/api/stream.ts)."""
    _require_enabled()
    _visible_or_403(db, principal, report_id)
    settings = get_settings()

    def event_stream():
        seen: set[str] = set()
        deadline = time.monotonic() + settings.log_stream_max_seconds
        while True:
            session = SessionLocal()
            try:
                rows = session.scalars(
                    select(SandboxEvent)
                    .where(SandboxEvent.run_id == report_id)
                    .order_by(SandboxEvent.seq)
                ).all()
                for row in rows:
                    if row.id in seen:
                        continue
                    seen.add(row.id)
                    payload = json.dumps(
                        {
                            "seq": row.seq,
                            "t": as_utc(row.t).isoformat(),
                            "category": row.category,
                            "level": row.level,
                            "msg": row.msg,
                            "data": row.data,
                        }
                    )
                    yield f"data: {payload}\n\n"
                state = session.scalar(
                    select(SandboxRun.state).where(SandboxRun.id == report_id)
                )
            finally:
                session.close()
            if state not in SANDBOX_LIVE_STATES or time.monotonic() > deadline:
                yield f"event: state\ndata: {state.value if state else 'unknown'}\n\n"
                return
            time.sleep(settings.log_stream_poll_seconds)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/reports/{report_id}/share", response_model=schemas.SandboxReportOut)
def set_share(
    report_id: str,
    body: schemas.SandboxShareIn,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    """Open or close a report to the submitter's tenant. Only the submitter can
    change sharing (docs/sandbox-security.md §Data privacy)."""
    _require_enabled()
    run = db.get(SandboxRun, report_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such report")
    if run.submitter_id != principal.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the submitter can share")
    run.shared = body.shared
    db.commit()
    return _report_out(db, run)


@router.get(
    "/reports/{report_id}/artifacts", response_model=list[schemas.SandboxArtifactOut]
)
def list_artifacts(
    report_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    """The archived analysis artifacts (report JSON, capture, dropped files).
    Listing is visible to anyone who can see the report; downloading the bytes
    is separately gated below."""
    _require_enabled()
    _visible_or_403(db, principal, report_id)
    prefix = f"{report_id}/"
    return [
        schemas.SandboxArtifactOut(
            key=obj.key, size=obj.size, last_modified=obj.last_modified
        )
        for obj in get_storage().list(REPORT_BUCKET)
        if obj.key.startswith(prefix)
    ]


@router.get("/reports/{report_id}/artifacts/download")
def download_artifact(
    report_id: str,
    key: str,
    principal: Principal = Depends(require_capability("sandbox:export")),
    db: Session = Depends(get_db),
):
    """Pull one archived artifact. Export is admin-only: downloads out of the
    platform are disabled for students, and raw samples are never served at all
    — only report-bucket artifacts (report JSON, capture, dropped-file diffs).
    A deployment wraps these in a password-protected ``infected`` archive at
    the edge (docs/sandbox-security.md §Handling rules)."""
    _require_enabled()
    _visible_or_403(db, principal, report_id)
    if not key.startswith(f"{report_id}/") or ".." in key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "artifact key out of scope")
    storage = get_storage()
    if not storage.exists(REPORT_BUCKET, key):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such artifact")
    from ..sandbox.vault import unseal

    data = unseal(storage.get(REPORT_BUCKET, key))  # sealed at rest
    name = key.rsplit("/", 1)[-1]
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )

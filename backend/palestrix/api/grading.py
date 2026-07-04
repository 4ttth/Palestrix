"""Automated-checking API: rubric schemes on lab templates.

The teacher-facing half of docs/automated-checking.md. A scheme is created
against a template the teacher owns, filled by the checker (archive diff or
win-file generation), weighted to exactly 100%, then published — publishing
is what turns grading on for every new and running instance of the
template. Students never touch this surface; their view is
``GET /instances/{id}/grading`` (rubric titles and weights only, no paths,
no markers, no hashes).
"""

import io
import posixpath

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..db import get_db
from ..grading import analyze_archives, generate_winfiles
from ..models import GradeCheck, GradingScheme, LabTemplate, Role, RubricItem
from ..rbac import Principal
from ..storage import get_storage
from .deps import require_capability

router = APIRouter(prefix="/grading", tags=["grading"])

MAX_WINFILES = 10


def _scheme_or_404(db: Session, scheme_id: str) -> GradingScheme:
    scheme = db.get(GradingScheme, scheme_id)
    if scheme is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such grading scheme")
    return scheme


def _require_scheme_owner(
    db: Session, principal: Principal, scheme: GradingScheme
) -> None:
    template = db.get(LabTemplate, scheme.lab_template_id)
    if principal.role is Role.superadmin:
        return
    if template is None or template.owner_id != principal.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your grading scheme")


def _items(db: Session, scheme: GradingScheme) -> list[RubricItem]:
    return db.scalars(
        select(RubricItem)
        .where(RubricItem.scheme_id == scheme.id)
        .order_by(RubricItem.position)
    ).all()


def _scheme_out(db: Session, scheme: GradingScheme) -> schemas.GradingSchemeOut:
    out = schemas.GradingSchemeOut.model_validate(scheme)
    rows = []
    for item in _items(db, scheme):
        row = schemas.RubricItemOut.model_validate(item)
        row.paths = [f["path"] for f in item.checks.get("files", [])]
        if item.storage_key:
            row.win_filename = posixpath.basename(item.storage_key)
        rows.append(row)
    out.items = rows
    return out


@router.post("/schemes", response_model=schemas.GradingSchemeOut, status_code=201)
def create_scheme(
    lab_template_id: str = Form(),
    kind: str = Form(pattern="^(diff|winfile)$"),
    winfiles: int = Form(default=3, ge=1, le=MAX_WINFILES),
    finished: UploadFile | None = None,
    principal: Principal = Depends(require_capability("courses:write")),
    db: Session = Depends(get_db),
):
    """Create the rubric for a template you own. ``diff``: upload the
    finished system's archive; the template's own archive is the unfinished
    one, and the checker diffs them into weighted objectives. ``winfile``:
    the server mints ``winfiles`` randomized scripts for you to plant."""
    template = db.get(LabTemplate, lab_template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such lab template")
    if principal.role is not Role.superadmin and template.owner_id != principal.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your lab template")
    if db.scalar(
        select(GradingScheme).where(GradingScheme.lab_template_id == template.id)
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "template already has a grading scheme"
        )

    scheme = GradingScheme(
        lab_template_id=template.id, kind=kind, created_by=principal.user_id
    )
    db.add(scheme)
    db.flush()

    if kind == "diff":
        if template.kind != "container" or not template.archive_key:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "diff schemes need a container template with a build archive "
                "(VM templates use winfile mode)",
            )
        if finished is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "diff schemes require the finished system's archive",
            )
        storage = get_storage()
        bucket, _, key = template.archive_key.partition("/")
        unfinished_bytes = storage.get(bucket, key)
        finished_bytes = finished.file.read()
        try:
            specs, analysis = analyze_archives(unfinished_bytes, finished_bytes)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
        scheme.finished_archive_key = storage.put(
            "lab-archives",
            f"grading/{scheme.id}/finished/{finished.filename}",
            io.BytesIO(finished_bytes),
            len(finished_bytes),
        )
        scheme.analysis = analysis
        for spec in specs:
            db.add(RubricItem(scheme_id=scheme.id, **spec))
    else:
        generate_winfiles(db, scheme, winfiles)

    db.commit()
    return _scheme_out(db, scheme)


@router.get("/schemes", response_model=list[schemas.GradingSchemeOut])
def list_schemes(
    lab_template_id: str | None = None,
    principal: Principal = Depends(require_capability("courses:write")),
    db: Session = Depends(get_db),
):
    query = select(GradingScheme)
    if lab_template_id:
        query = query.where(GradingScheme.lab_template_id == lab_template_id)
    if principal.role is not Role.superadmin:
        query = query.join(
            LabTemplate, LabTemplate.id == GradingScheme.lab_template_id
        ).where(LabTemplate.owner_id == principal.user_id)
    return [_scheme_out(db, s) for s in db.scalars(query).all()]


@router.get("/schemes/{scheme_id}", response_model=schemas.GradingSchemeOut)
def get_scheme(
    scheme_id: str,
    principal: Principal = Depends(require_capability("courses:write")),
    db: Session = Depends(get_db),
):
    scheme = _scheme_or_404(db, scheme_id)
    _require_scheme_owner(db, principal, scheme)
    return _scheme_out(db, scheme)


@router.patch("/schemes/{scheme_id}/weights", response_model=schemas.GradingSchemeOut)
def set_weights(
    scheme_id: str,
    body: schemas.GradingWeightsIn,
    principal: Principal = Depends(require_capability("courses:write")),
    db: Session = Depends(get_db),
):
    scheme = _scheme_or_404(db, scheme_id)
    _require_scheme_owner(db, principal, scheme)
    if scheme.status != "draft":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "published schemes are locked"
        )
    items = {item.id: item for item in _items(db, scheme)}
    unknown = set(body.weights) - set(items)
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"unknown rubric items: {sorted(unknown)}",
        )
    for item_id, weight in body.weights.items():
        if not 0 <= weight <= 100:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "weights are 0-100 percent"
            )
        items[item_id].weight_percent = weight
    db.commit()
    return _scheme_out(db, scheme)


@router.post("/schemes/{scheme_id}/publish", response_model=schemas.GradingSchemeOut)
def publish_scheme(
    scheme_id: str,
    principal: Principal = Depends(require_capability("courses:write")),
    db: Session = Depends(get_db),
):
    """Weights must tally to exactly 100% — the whole grade is accounted
    for, nothing double-counted. Publishing locks the rubric and turns
    automated checking on for this template's instances."""
    from ..models import utcnow

    scheme = _scheme_or_404(db, scheme_id)
    _require_scheme_owner(db, principal, scheme)
    if scheme.status == "published":
        raise HTTPException(status.HTTP_409_CONFLICT, "already published")
    total = sum(item.weight_percent for item in _items(db, scheme))
    if total != 100:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "weights_must_total_100",
                "total": total,
            },
        )
    scheme.status = "published"
    scheme.published_at = utcnow()
    db.commit()
    return _scheme_out(db, scheme)


@router.post("/schemes/{scheme_id}/regenerate", response_model=schemas.GradingSchemeOut)
def regenerate_winfiles(
    scheme_id: str,
    winfiles: int = Form(default=3, ge=1, le=MAX_WINFILES),
    principal: Principal = Depends(require_capability("courses:write")),
    db: Session = Depends(get_db),
):
    """Re-randomize a draft winfile scheme: fresh tokens, fresh marker
    directory. Every previously downloaded script stops counting."""
    scheme = _scheme_or_404(db, scheme_id)
    _require_scheme_owner(db, principal, scheme)
    if scheme.kind != "winfile":
        raise HTTPException(status.HTTP_409_CONFLICT, "not a winfile scheme")
    if scheme.status != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, "published schemes are locked")
    generate_winfiles(db, scheme, winfiles)
    db.commit()
    return _scheme_out(db, scheme)


@router.get("/schemes/{scheme_id}/winfiles/{item_id}")
def download_winfile(
    scheme_id: str,
    item_id: str,
    principal: Principal = Depends(require_capability("courses:write")),
    db: Session = Depends(get_db),
):
    scheme = _scheme_or_404(db, scheme_id)
    _require_scheme_owner(db, principal, scheme)
    item = db.get(RubricItem, item_id)
    if item is None or item.scheme_id != scheme.id or not item.storage_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such win file")
    bucket, _, key = item.storage_key.partition("/")
    filename = posixpath.basename(item.storage_key)
    return Response(
        content=get_storage().get(bucket, key),
        media_type="text/x-shellscript",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/schemes/{scheme_id}", status_code=204)
def delete_scheme(
    scheme_id: str,
    principal: Principal = Depends(require_capability("courses:write")),
    db: Session = Depends(get_db),
):
    """Drafts can be discarded and redone. Published schemes are permanent —
    recorded grades reference them."""
    scheme = _scheme_or_404(db, scheme_id)
    _require_scheme_owner(db, principal, scheme)
    if scheme.status != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, "published schemes are locked")
    if db.scalar(select(GradeCheck).where(GradeCheck.scheme_id == scheme.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "scheme has recorded grades")
    for item in _items(db, scheme):
        db.delete(item)
    db.delete(scheme)
    db.commit()
    return None

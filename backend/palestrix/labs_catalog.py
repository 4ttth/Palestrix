"""Lab templates and their rubrics, as repository content.

The academy catalog ships paths and modules; this ships the labs a module can
be gated on, for the same reason: a lab that exists only as hand-inserted rows
on one server cannot be reviewed, cannot be recreated, and quietly differs
between deployments.

Only labs whose grading is fully specified belong here. A rubric item states
an exact file and the SHA-256 of its exact expected contents, which the
checker reads back over the guest agent
(``grading.read_files`` -> ``_item_passed``). That is deliberately strict:
the grader does no parsing, so the lesson must tell the student precisely what
to write.

Applying is insert-only. An existing template with the same slug is left
alone, because a teacher may have edited it through the API and this file
should not overwrite that. Run it with::

    python -m palestrix.labs_catalog            # apply
    python -m palestrix.labs_catalog --dry-run  # report only
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import GradingScheme, LabTemplate, Role, RubricItem, User


@dataclass(frozen=True)
class CatalogRubricItem:
    key: str
    title: str
    detail: str
    weight_percent: int
    path: str
    sha256: str


@dataclass(frozen=True)
class CatalogLab:
    slug: str
    title: str
    kind: str                    # container | vm
    vm_template: str | None
    access_mode: str
    cpu: int
    ram_gb: int
    ttl_minutes_default: int
    ttl_minutes_max: int
    scheme_kind: str             # diff | winfile
    items: tuple[CatalogRubricItem, ...] = field(default=())


def _answer(key: str, title: str, weight: int, filename: str, sha256: str) -> CatalogRubricItem:
    return CatalogRubricItem(
        key=key,
        title=title,
        detail=f"/root/answers/{filename} must contain exactly the expected value.",
        weight_percent=weight,
        path=f"/root/answers/{filename}",
        sha256=sha256,
    )


CATALOG: tuple[CatalogLab, ...] = (
    CatalogLab(
        slug="log-triage",
        title="Log Triage Under Fire",
        kind="vm",
        # The Kali template already on the hypervisor. It carries the QEMU
        # guest agent, which is what lets the checker read the answer files.
        vm_template="Kali-Template",
        access_mode="no-gui",
        cpu=2,
        ram_gb=2,
        ttl_minutes_default=90,
        ttl_minutes_max=240,
        scheme_kind="diff",
        items=(
            _answer(
                "source-ip",
                "Identified the source address of the intrusion",
                25,
                "source-ip.txt",
                "6428ce79f5826e5d01b22a143e0926ff2b3bd880e1d3dfeed70ed69c3afb6e95",
            ),
            _answer(
                "account",
                "Identified the account that authenticated successfully",
                25,
                "account.txt",
                "c6f1676734b35a3c26274cdcdedc4a34ead3d0b815ab6d06afd4a58a55baf13c",
            ),
            _answer(
                "method",
                "Identified the authentication method that succeeded",
                25,
                "method.txt",
                "b05b07ded7a7373e1328d2a1585a5990a6e77e073a32c7bb01a39dcd6d8547bd",
            ),
            _answer(
                "escalated-to",
                "Identified the account privilege was escalated to",
                25,
                "escalated-to.txt",
                "53175bcc0524f37b47062fafdda28e3f8eb91d519ca0a184ca71bbebe72f969a",
            ),
        ),
    ),
)


def _owner_id(db: Session) -> str | None:
    """Labs need an owner. Prefer a real staff account over inventing one."""
    for role in (Role.superadmin, Role.admin, Role.teacher):
        owner = db.scalar(select(User).where(User.role == role).order_by(User.id))
        if owner is not None:
            return owner.id
    return None


def ensure_labs(db: Session, catalog: tuple[CatalogLab, ...] = CATALOG) -> dict:
    """Insert missing labs and their published rubrics. Never overwrites."""
    report: dict = {"created": [], "skipped": [], "error": None}

    owner_id = _owner_id(db)
    if owner_id is None:
        report["error"] = "no staff account to own the lab templates"
        return report

    for spec in catalog:
        existing = db.scalar(select(LabTemplate).where(LabTemplate.slug == spec.slug))
        if existing is not None:
            report["skipped"].append(spec.slug)
            continue

        template = LabTemplate(
            slug=spec.slug,
            title=spec.title,
            kind=spec.kind,
            access_mode=spec.access_mode,
            cpu=spec.cpu,
            ram_gb=spec.ram_gb,
            ttl_minutes_default=spec.ttl_minutes_default,
            ttl_minutes_max=spec.ttl_minutes_max,
            vm_template=spec.vm_template,
            owner_id=owner_id,
        )
        db.add(template)
        db.flush()

        total = sum(item.weight_percent for item in spec.items)
        if total != 100:
            report["error"] = f"{spec.slug}: weights total {total}, expected 100"
            return report

        scheme = GradingScheme(
            lab_template_id=template.id,
            kind=spec.scheme_kind,
            # Published, so the academy gate is live. A draft scheme has
            # editable weights and grading turned off, which would leave any
            # module bound to this lab ungated.
            status="published",
            created_by=owner_id,
        )
        db.add(scheme)
        db.flush()

        for position, item in enumerate(spec.items):
            db.add(
                RubricItem(
                    scheme_id=scheme.id,
                    key=item.key,
                    title=item.title,
                    detail=item.detail,
                    weight_percent=item.weight_percent,
                    position=position,
                    checks={
                        "files": [
                            {"path": item.path, "sha256": item.sha256, "present": True}
                        ]
                    },
                )
            )
        report["created"].append(spec.slug)

    return report


def main(argv: list[str]) -> int:
    from .db import SessionLocal

    dry_run = "--dry-run" in argv
    db = SessionLocal()
    try:
        report = ensure_labs(db)
        if report["error"]:
            print(f"error: {report['error']}", file=sys.stderr)
            db.rollback()
            return 1
        if dry_run:
            db.rollback()
        else:
            db.commit()
        print(
            f"{'would create' if dry_run else 'created'}: "
            f"{report['created'] or 'nothing'}"
        )
        if report["skipped"]:
            print(f"already present: {report['skipped']}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

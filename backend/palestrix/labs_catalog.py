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
        # A minimal Debian guest, not Kali. This lab is `grep`, `awk` and four
        # text files; the offensive toolchain buys it nothing and costs a
        # multi-gigabyte disk copy per launch. What it actually needs is the
        # QEMU guest agent, which is what lets the checker read the answers
        # back. See docs/lab-vm-templates.md for how the template is built.
        vm_template="debian12-min",
        access_mode="no-gui",
        cpu=1,
        ram_gb=1,
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
    # One capstone lab per learning path. All four clone the same minimal
    # Debian template: the student's task is to record findings read out of
    # the lesson's evidence, so the box needs a shell, the guest agent, and
    # nothing else. Adding a capstone costs a rubric here, not a new golden
    # image on the hypervisor.
    CatalogLab(
        slug="soc-capstone",
        title="SOC Capstone: 48-hour incident",
        kind="vm",
        vm_template="debian12-min",
        access_mode="no-gui",
        cpu=1,
        ram_gb=1,
        ttl_minutes_default=120,
        ttl_minutes_max=240,
        scheme_kind="diff",
        items=(
            _answer(
                "patient-zero",
                "Identified the host where the intrusion began",
                20,
                "patient-zero.txt",
                "593b947597375c7bfabd1de2c3e8c8a10dd2e84a3f42aa18d8ca449ad37e6224",
            ),
            _answer(
                "initial-access",
                "Identified the file that delivered initial access",
                20,
                "initial-access.txt",
                "435ea61c0c577783815fb2d631e2a9e94be3a65a496acd5024300cf626edb640",
            ),
            _answer(
                "service-account",
                "Identified the account used for lateral movement",
                20,
                "service-account.txt",
                "4bfbf239bb9169ff35260d889262b27cc55f2504d7d23b85ab0486db4dc2ad7f",
            ),
            _answer(
                "persistence",
                "Identified the service installed for persistence",
                20,
                "persistence.txt",
                "5b973733b1ec6a14d16bc6e33f7991662baf60bc34fc88b7188402d92de6715a",
            ),
            _answer(
                "dwell-hours",
                "Calculated dwell time from first execution to detection",
                20,
                "dwell-hours.txt",
                "654ee9da442fa353f59f11beb688fc7f76c8de62a6c18b2a181fdde2a27cc3ef",
            ),
        ),
    ),
    CatalogLab(
        slug="web-capstone",
        title="Web Capstone: chain four bugs into a shell",
        kind="vm",
        vm_template="debian12-min",
        access_mode="no-gui",
        cpu=1,
        ram_gb=1,
        ttl_minutes_default=120,
        ttl_minutes_max=240,
        scheme_kind="diff",
        items=(
            _answer(
                "api-version",
                "Identified the API version missing the ownership check",
                20,
                "api-version.txt",
                "2d27fbdf4e8ca207afbfa388ca9172fbcc6c70e534af2476b3b704f87debadcf",
            ),
            _answer(
                "leaked-field",
                "Identified the response field the old version leaked",
                20,
                "leaked-field.txt",
                "d9f9af61eae61f239fc8d32e8603c6b4e48552e5a5c0c42bd2c9f54b8e66f3af",
            ),
            _answer(
                "ssrf-target",
                "Identified the address reached through the logo importer",
                20,
                "ssrf-target.txt",
                "009985ed37b6926996731da0c228a1637b11cd1bef5a2c98e52eecbc8c0d66d9",
            ),
            _answer(
                "upload-magic",
                "Identified the signature that defeated the upload check",
                20,
                "upload-magic.txt",
                "9c5ac81c5e3d82548531794d1b7a101778d4cde999c3d3c29d3cf8a5c1a16d93",
            ),
            _answer(
                "shell-user",
                "Identified the account the resulting shell runs as",
                20,
                "shell-user.txt",
                "262a5c8733e7f896ca95130b2bb22df43b65cb28efd7c523a4daa6a84c074ea8",
            ),
        ),
    ),
    CatalogLab(
        slug="netdef-capstone",
        title="Network Defense Capstone: hold a live network",
        kind="vm",
        vm_template="debian12-min",
        access_mode="no-gui",
        cpu=1,
        ram_gb=1,
        ttl_minutes_default=120,
        ttl_minutes_max=240,
        scheme_kind="diff",
        items=(
            _answer(
                "pivot-host",
                "Identified the compromised internal address",
                20,
                "pivot-host.txt",
                "19265065d41144f3ea52a94a1eaf6a03dc76fd3067041bcede17cad2c9aa00a3",
            ),
            _answer(
                "exfil-protocol",
                "Identified the protocol carrying the bulk exfiltration",
                20,
                "exfil-protocol.txt",
                "a4d83335f568348754b1e07969c30f093994caeea6e9a1f8ee8954080cf3593a",
            ),
            _answer(
                "exfil-domain",
                "Identified the registered domain the data went to",
                20,
                "exfil-domain.txt",
                "d46dd38b0fa23fb4acaf230f4457e9972d5e83cbe2a20c660bed907bf754874a",
            ),
            _answer(
                "beacon-interval",
                "Calculated the beacon's mean interval in seconds",
                20,
                "beacon-interval.txt",
                "ab8e9a58c47abe1aeff8ae620a0ed614ee77d507ef52799d4c103d69ff35d85c",
            ),
            _answer(
                "violated-segment",
                "Identified the segment reached despite the deny rule",
                20,
                "violated-segment.txt",
                "9b47b1d1f65f93872d2b1cc222ab3a5b842c9213c0601b6fab6bf0b274b6c823",
            ),
        ),
    ),
    CatalogLab(
        slug="forensics-capstone",
        title="Forensics Capstone: a full case from image to report",
        kind="vm",
        vm_template="debian12-min",
        access_mode="no-gui",
        cpu=1,
        ram_gb=1,
        ttl_minutes_default=120,
        ttl_minutes_max=240,
        scheme_kind="diff",
        items=(
            _answer(
                "entry-file",
                "Identified the file that was downloaded and opened",
                20,
                "entry-file.txt",
                "435ea61c0c577783815fb2d631e2a9e94be3a65a496acd5024300cf626edb640",
            ),
            _answer(
                "dropped-dll",
                "Identified the library dropped on execution",
                20,
                "dropped-dll.txt",
                "5ae2837eeccc08c4de99af6819164a09bbeeb966f499eb3a2aae6b45f4433a12",
            ),
            _answer(
                "persistence-value",
                "Identified the Run value used for persistence",
                20,
                "persistence-value.txt",
                "2e705ccc697d4d60c2aa3b3db89d10e77ea065361e81f99d6ae0c95274391f48",
            ),
            _answer(
                "usb-serial",
                "Identified the serial of the device that was attached",
                20,
                "usb-serial.txt",
                "978988f6c069c8368dbc4957a9226b0ea2c98746f2ef9c5d8dacd10a5af3d40e",
            ),
            _answer(
                "wipe-tool",
                "Identified the tool used to destroy evidence",
                20,
                "wipe-tool.txt",
                "cb4942c44a4bab0c38fb092edf389353466bdc2567e5ed9336340fc2c438102b",
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

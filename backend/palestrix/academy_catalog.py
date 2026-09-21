"""The academy catalog that ships with the repository.

The four paths the landing page advertises are content, not fixtures: they
live here, in version control, and are applied to whatever database the
instance is pointed at. `ensure_catalog` runs at startup (and from
`palestrix.seed`), so a deployment that pulls this repository and restarts
the API has the catalog without anyone typing SQL or clicking through an
admin form.

Reconciliation rules, in order of how much they touch:

* A path missing from the database is created with all of its modules.
* An existing catalog path keeps its row (and therefore every completion
  pointing at it); its title and hours are refreshed from here, because
  this file is the source of truth for catalog content.
* A module is matched inside its path **by title**, so the five modules the
  old seed wrote for ``soc-analyst`` are adopted rather than duplicated.
  Missing modules are inserted, and positions are renumbered to the order
  below. Modules a teacher added by hand are never deleted; they keep their
  relative order after the catalog's.

Nothing here deletes a path, a module, or a completion.

The module counts must stay in step with the catalog preview on the landing
page (``app/(marketing)/page.tsx``): 14 / 12 / 10 / 11.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from . import academy_content_loader as content
from .models import Module, Path


@dataclass(frozen=True)
class CatalogModule:
    title: str
    palestras_award: int


@dataclass(frozen=True)
class CatalogPath:
    slug: str
    title: str
    hours: int
    modules: tuple[CatalogModule, ...] = field(default=())


def _p(slug: str, title: str, hours: int, modules: list[tuple[str, int]]) -> CatalogPath:
    return CatalogPath(
        slug=slug,
        title=title,
        hours=hours,
        modules=tuple(CatalogModule(t, award) for t, award in modules),
    )


CATALOG: tuple[CatalogPath, ...] = (
    _p(
        "soc-analyst",
        "SOC Analyst",
        38,
        [
            ("The SOC shift: alerts, queues, and escalation", 35),
            ("Reading auth logs at speed", 40),
            ("Windows event IDs that actually matter", 45),
            ("Linux audit trails and journald", 45),
            ("Sigma rules from scratch", 55),
            ("Tuning out the noise: false positives and thresholds", 50),
            ("Enriching alerts with threat intelligence", 50),
            ("Lateral movement patterns", 60),
            ("Detecting persistence on a compromised host", 60),
            ("Command-and-control beacons in network telemetry", 65),
            ("Building a triage runbook", 45),
            ("Writing the incident report", 40),
            ("Tabletop: containment under pressure", 70),
            ("Capstone: 48-hour incident", 120),
        ],
    ),
    _p(
        "web-exploitation",
        "Web Exploitation",
        30,
        [
            ("HTTP for attackers: requests, sessions, and state", 40),
            ("Mapping an application's attack surface", 45),
            ("Broken access control and IDOR", 55),
            ("Authentication flaws and session fixation", 55),
            ("SQL injection from boolean to blind", 65),
            ("NoSQL and ORM injection", 55),
            ("Cross-site scripting: reflected, stored, and DOM", 60),
            ("CSRF in the SameSite era", 45),
            ("Server-side request forgery", 60),
            ("File upload to remote code execution", 70),
            ("Deserialization and template injection", 70),
            ("Capstone: chain four bugs into a shell", 120),
        ],
    ),
    _p(
        "network-defense",
        "Network Defense",
        26,
        [
            ("Reading a packet capture without fear", 40),
            ("Segmentation, VLANs, and the flat-network problem", 50),
            ("Firewall policy as code", 55),
            ("Suricata rules in anger", 60),
            ("NetFlow and the shape of normal traffic", 55),
            ("DNS as a defensive sensor", 55),
            ("TLS inspection and what it costs you", 50),
            ("Hardening the edge: VPN and remote access", 60),
            ("Detecting exfiltration over covert channels", 70),
            ("Capstone: hold a live network for 24 hours", 120),
        ],
    ),
    _p(
        "digital-forensics",
        "Digital Forensics",
        32,
        [
            ("Evidence handling and chain of custody", 45),
            ("Disk imaging and write blockers", 50),
            ("File systems: NTFS, ext4, and what deletion leaves", 60),
            ("Timeline analysis from the artifacts up", 65),
            ("Windows registry forensics", 60),
            ("Browser and application artifacts", 50),
            ("Memory acquisition and live response", 65),
            ("Volatility: processes, injection, and rootkits", 70),
            ("Log and network forensics after the fact", 55),
            ("Anti-forensics and how it fails", 55),
            ("Capstone: a full case from image to report", 120),
        ],
    ),
)


# Arbitrary but fixed: "PLXC". Any process applying the catalog takes this
# lock, so they queue instead of colliding.
_CATALOG_LOCK_KEY = 0x504C5843


def _serialise(db: Session) -> None:
    """Queue concurrent catalog writers behind a transaction-scoped lock.

    The API runs under several uvicorn workers and every one of them applies
    the catalog in its startup lifespan. Without this they race on the
    paths.slug unique constraint: one wins and the rest take a
    UniqueViolation and roll back. The data still converged -- every worker
    applies the same catalog, so whoever commits first wins wholesale -- but
    each first restart after a catalog change logged a traceback, and a
    traceback that is normal is a traceback that hides a real failure.

    Postgres only; SQLite has no advisory locks and no concurrent startup to
    protect against. The lock releases when the transaction ends.
    """
    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _CATALOG_LOCK_KEY})


def ensure_catalog(db: Session, catalog: tuple[CatalogPath, ...] = CATALOG) -> dict:
    """Apply the catalog to `db`. Idempotent; returns what it changed.

    The caller owns the transaction: nothing is committed here.
    """
    _serialise(db)
    report = {
        "paths_created": [],
        "modules_created": [],
        "modules_renumbered": 0,
        "lessons_loaded": 0,
        "lessons_missing": [],
    }

    for spec in catalog:
        path = db.scalar(select(Path).where(Path.slug == spec.slug))
        if path is None:
            path = Path(slug=spec.slug, title=spec.title, hours=spec.hours)
            db.add(path)
            db.flush()
            report["paths_created"].append(spec.slug)
        else:
            # This file is the source of truth for catalog metadata.
            path.title = spec.title
            path.hours = spec.hours

        existing = list(
            db.scalars(
                select(Module).where(Module.path_id == path.id).order_by(Module.position)
            ).all()
        )
        by_title = {m.title: m for m in existing}

        ordered: list[Module] = []
        for spec_module in spec.modules:
            module = by_title.get(spec_module.title)
            if module is None:
                module = Module(
                    path_id=path.id,
                    title=spec_module.title,
                    position=len(ordered),
                    palestras_award=spec_module.palestras_award,
                )
                db.add(module)
                report["modules_created"].append(f"{spec.slug}/{spec_module.title}")

            # The repository is the source of truth for lesson content, so
            # this reapplies on every startup and a pull publishes an edit.
            # A module whose file is not written yet keeps whatever it has
            # rather than being blanked.
            lesson = content.load(spec.slug, len(ordered), spec_module.title)
            if lesson.empty:
                report["lessons_missing"].append(f"{spec.slug}/{spec_module.title}")
            else:
                module.summary = lesson.summary
                module.body = lesson.body
                module.lab_slug = lesson.lab_slug
                module.pass_percent = lesson.pass_percent
                report["lessons_loaded"] += 1

            ordered.append(module)

        # Whatever a teacher added by hand keeps its relative order, after
        # the catalog's modules.
        claimed = {id(m) for m in ordered}
        ordered.extend(m for m in existing if id(m) not in claimed)

        for position, module in enumerate(ordered):
            if module.position != position:
                module.position = position
                report["modules_renumbered"] += 1

    db.flush()
    return report

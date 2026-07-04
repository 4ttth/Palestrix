"""Automated checking (docs/automated-checking.md).

Two rubric sources, one checker:

- ``diff`` schemes: the teacher's published archive is the *unfinished*
  system students receive; a second, *finished* archive is the reference.
  ``analyze_archives`` does a real tar-level diff between the two, groups
  every differing file into a topic (SSH, MOTD, users, ...), and each topic
  becomes a rubric item the teacher weights.

- ``winfile`` schemes: ``generate_winfiles`` mints randomized executable
  scripts (new tokens on every generation). The teacher plants them in the
  image; executing one writes a token into a randomized marker directory.
  Each script is a rubric item.

Checking is provider-mediated: the instance's provider exposes
``read_files(db, instance, paths) -> {path: sha256 | None}`` (Docker via
``docker exec sha256sum``, Proxmox via the QEMU guest agent, demo honestly
reads everything as absent). The checker never gets shell access of its
own — the provider contract is the only door into a student's box.

Grading fires at the first of: the student's explicit hand-in, stop,
destroy, or the TTL reaper — always while the instance is still running,
because the box is the evidence. The result writes into the course
submission and rides the existing grade.posted -> Canvas passback path.
"""

from __future__ import annotations

import hashlib
import io
import logging
import posixpath
import re
import secrets
import tarfile
from typing import TYPE_CHECKING

from sqlalchemy import select

from ..events import emit
from ..models import (
    Assignment,
    Course,
    Enrollment,
    GradeCheck,
    GradingScheme,
    Instance,
    InstanceState,
    LabTemplate,
    RubricItem,
    Submission,
    User,
)
from ..providers import add_log, provider_for_kind
from ..storage import get_storage

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger("palestrix.grading")


class GradingUnavailable(RuntimeError):
    """The instance cannot be checked right now (no provider, provider
    without file inspection, or the provider failed mid-check)."""


# -- topic classifier ---------------------------------------------------------------

# First match wins. Grouping differing files into topics is what turns a raw
# file diff into the rubric a teacher recognizes ("% of correctly configured
# SSH"), so the rules favor the classic hardening surfaces.
_TOPICS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"/etc/ssh/|(^|/)sshd?_config$"), "ssh", "SSH configuration"),
    (re.compile(r"(^|/)motd([./]|$)|/etc/issue"), "motd", "Message of the day (MOTD)"),
    (re.compile(r"/etc/(passwd|shadow|group|gshadow)$"), "users", "User accounts"),
    (re.compile(r"sudoers"), "sudoers", "Sudoers policy"),
    (re.compile(r"cron"), "cron", "Scheduled tasks (cron)"),
    (re.compile(r"iptables|nftables|/ufw/|firewall"), "firewall", "Firewall rules"),
    (re.compile(r"/etc/(nginx|apache2|httpd)/"), "web", "Web server configuration"),
    (
        re.compile(r"/etc/(hosts|resolv\.conf)$|/etc/(network|netplan)/"),
        "network",
        "Network configuration",
    ),
    (re.compile(r"/etc/(pam\.d|security)/"), "pam", "PAM and login policy"),
    (re.compile(r"/etc/systemd/|/etc/init\.d/"), "services", "System services"),
]

# Build-context files that never exist on the running system.
_CONTEXT_ONLY = {"dockerfile", "docker-compose.yml", "docker-compose.yaml", ".dockerignore"}


def classify_path(path: str) -> tuple[str, str]:
    for pattern, key, title in _TOPICS:
        if pattern.search(path):
            return key, title
    base = posixpath.basename(path) or path
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-") or "file"
    return f"file-{slug}"[:64], f"File: {path}"


# -- diff analysis -------------------------------------------------------------------


def _archive_manifest(data: bytes) -> dict[str, str]:
    """{absolute path: sha256} for every regular file in a (gzipped) tar.
    Archive layout mirrors the runtime filesystem — the documented diff-mode
    convention (files are COPY'd to matching absolute paths)."""
    try:
        tar = tarfile.open(fileobj=io.BytesIO(data), mode="r:*")
    except tarfile.TarError as exc:
        raise ValueError(f"not a readable tar archive: {exc}") from exc
    manifest: dict[str, str] = {}
    with tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            name = member.name.lstrip("./")
            if not name or name.lower() in _CONTEXT_ONLY:
                continue
            fh = tar.extractfile(member)
            if fh is None:
                continue
            manifest["/" + name] = hashlib.sha256(fh.read()).hexdigest()
    return manifest


def analyze_archives(
    unfinished: bytes, finished: bytes
) -> tuple[list[dict], dict]:
    """Diff the two systems and group every difference into rubric item
    specs. Raises ValueError when either archive is unreadable or the two
    systems are identical (nothing to grade)."""
    base = _archive_manifest(unfinished)
    target = _archive_manifest(finished)

    changes: list[dict] = []
    for path, digest in sorted(target.items()):
        if path not in base:
            changes.append({"path": path, "change": "added", "sha256": digest})
        elif base[path] != digest:
            changes.append({"path": path, "change": "modified", "sha256": digest})
    for path in sorted(set(base) - set(target)):
        changes.append({"path": path, "change": "removed", "sha256": None})
    if not changes:
        raise ValueError(
            "the finished and unfinished systems are identical — nothing to grade"
        )

    _VERB = {"added": "create", "modified": "configure", "removed": "remove"}
    grouped: dict[str, dict] = {}
    for change in changes:
        key, title = classify_path(change["path"])
        item = grouped.setdefault(
            key, {"key": key, "title": title, "expectations": [], "verbs": []}
        )
        item["expectations"].append(
            {
                "path": change["path"],
                "sha256": change["sha256"],
                "present": change["change"] != "removed",
            }
        )
        item["verbs"].append(f"{_VERB[change['change']]} {change['path']}")

    specs = []
    for position, key in enumerate(sorted(grouped)):
        item = grouped[key]
        specs.append(
            {
                "key": item["key"],
                "title": item["title"],
                "detail": "; ".join(item["verbs"]),
                "position": position,
                "checks": {"files": item["expectations"]},
            }
        )
    analysis = {
        "files_unfinished": len(base),
        "files_finished": len(target),
        "differences": len(changes),
        "changes": [{"path": c["path"], "change": c["change"]} for c in changes],
    }
    return specs, analysis


# -- win files -----------------------------------------------------------------------

_WIN_SCRIPT = """#!/bin/sh
# PalestrIX win file: plant this anywhere in the lab image before
# publishing. A student proves the objective by finding and executing it
# once on the live system; execution records a marker the automated
# checker verifies at hand-in.
mkdir -p '{marker_dir}'
umask 077
printf '%s' '{token}' > '{marker}'
echo 'palestrix: objective {key} recorded'
"""


def generate_winfiles(db: "Session", scheme: GradingScheme, count: int) -> list[RubricItem]:
    """Mint ``count`` randomized win scripts for a draft scheme, replacing
    any previous generation (fresh tokens, fresh marker directory — a
    regenerate invalidates every previously downloaded script)."""
    for old in db.scalars(
        select(RubricItem).where(RubricItem.scheme_id == scheme.id)
    ).all():
        db.delete(old)
    # A world-writable, sticky base so unprivileged students can record a
    # win too (cyber-range boxes are not always root-for-all); the leaf is
    # randomized per scheme so the marker stays unguessable without the
    # script. The script's own umask keeps the marker private.
    scheme.marker_dir = f"/tmp/.plx-{secrets.token_hex(8)}"

    storage = get_storage()
    items: list[RubricItem] = []
    for i in range(1, count + 1):
        key = f"win-{i}"
        token = secrets.token_hex(16)
        filename = f"win-{i}-{secrets.token_hex(4)}.sh"
        marker = f"{scheme.marker_dir}/{key}"
        script = _WIN_SCRIPT.format(
            marker_dir=scheme.marker_dir, token=token, marker=marker, key=key
        ).encode()
        storage_key = storage.put(
            "lab-archives", f"grading/{scheme.id}/{filename}", io.BytesIO(script), len(script)
        )
        item = RubricItem(
            scheme_id=scheme.id,
            key=key,
            title=f"Win file {i}",
            detail=f"Find and execute {filename} on the lab system",
            position=i - 1,
            checks={
                "marker": marker,
                "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            },
            storage_key=storage_key,
        )
        db.add(item)
        items.append(item)
    return items


# -- checking a live instance --------------------------------------------------------


def _read_hashes(
    db: "Session", instance: Instance, template: LabTemplate, paths: list[str]
) -> dict[str, str | None]:
    provider = provider_for_kind(template.kind)
    if provider is None:
        raise GradingUnavailable(f"no active provider for kind '{template.kind}'")
    read_files = getattr(provider, "read_files", None)
    if not callable(read_files):
        raise GradingUnavailable(
            f"provider '{provider.name}' cannot inspect instance files"
        )
    try:
        return read_files(db, instance, paths)
    except Exception as exc:  # provider-specific errors become one type
        raise GradingUnavailable(f"provider check failed: {exc}") from exc


def _item_paths(item: RubricItem) -> list[str]:
    if "marker" in item.checks:
        return [item.checks["marker"]]
    return [f["path"] for f in item.checks.get("files", [])]


def _item_passed(item: RubricItem, observed: dict[str, str | None]) -> bool:
    if "marker" in item.checks:
        return observed.get(item.checks["marker"]) == item.checks["token_sha256"]
    files = item.checks.get("files", [])
    for expected in files:
        seen = observed.get(expected["path"])
        if expected["present"] and seen != expected["sha256"]:
            return False
        if not expected["present"] and seen is not None:
            return False
    return bool(files)


def run_checks(
    db: "Session",
    instance: Instance,
    template: LabTemplate,
    scheme: GradingScheme,
    trigger: str,
) -> GradeCheck:
    """One grading pass over a live instance. Records and returns the
    GradeCheck; the caller owns the commit."""
    items = db.scalars(
        select(RubricItem)
        .where(RubricItem.scheme_id == scheme.id)
        .order_by(RubricItem.position)
    ).all()
    paths = sorted({p for item in items for p in _item_paths(item)})
    observed = _read_hashes(db, instance, template, paths)

    breakdown, total = [], 0
    for item in items:
        passed = _item_passed(item, observed)
        total += item.weight_percent if passed else 0
        breakdown.append(
            {
                "key": item.key,
                "title": item.title,
                "weight_percent": item.weight_percent,
                "passed": passed,
            }
        )
    check = GradeCheck(
        scheme_id=scheme.id,
        instance_id=instance.id,
        user_id=instance.owner_id,
        total_percent=total,
        items=breakdown,
        trigger=trigger,
    )
    db.add(check)
    done = sum(1 for row in breakdown if row["passed"])
    add_log(
        db,
        instance.id,
        f"autograde ({trigger}): {total}/100 — {done} of {len(breakdown)} objectives",
        level="ok" if total == 100 else "warn",
    )
    return check


def write_back(
    db: "Session",
    instance: Instance,
    template: LabTemplate,
    scheme: GradingScheme,
    check: GradeCheck,
) -> bool:
    """Post the automated grade into every lab assignment for this template
    in a course the student is enrolled in. Returns True when at least one
    submission was written (the caller then dispatches events/passbacks)."""
    from ..integrations.passback import queue_grade_passbacks

    assignments = db.scalars(
        select(Assignment)
        .join(Enrollment, Enrollment.course_id == Assignment.course_id)
        .where(
            Assignment.lab_template_id == template.id,
            Assignment.kind == "lab",
            Enrollment.user_id == instance.owner_id,
        )
    ).all()
    student = db.get(User, instance.owner_id)
    wrote = False
    for assignment in assignments:
        submission = db.scalar(
            select(Submission).where(
                Submission.assignment_id == assignment.id,
                Submission.user_id == instance.owner_id,
            )
        )
        if submission is None:
            submission = Submission(
                assignment_id=assignment.id, user_id=instance.owner_id
            )
            db.add(submission)
            db.flush()
        submission.grade = check.total_percent
        submission.graded_by = scheme.created_by
        if check.submission_id is None:
            check.submission_id = submission.id
        course = db.get(Course, assignment.course_id)
        emit(
            db,
            "grade.posted",
            {
                "submission_id": submission.id,
                "assignment_id": assignment.id,
                "course_id": assignment.course_id,
                "student": student.handle if student else instance.owner_id,
                "grade": check.total_percent,
                "source": "autograde",
            },
        )
        queue_grade_passbacks(db, course, assignment, submission)
        wrote = True
    emit(
        db,
        "grading.result.ready",
        {
            "instance_id": instance.id,
            "scheme_id": scheme.id,
            "user_id": instance.owner_id,
            "total_percent": check.total_percent,
            "trigger": check.trigger,
        },
    )
    return wrote


def published_scheme_for(db: "Session", template_id: str) -> GradingScheme | None:
    return db.scalar(
        select(GradingScheme).where(
            GradingScheme.lab_template_id == template_id,
            GradingScheme.status == "published",
        )
    )


def autograde_if_due(
    db: "Session", instance: Instance, *, trigger: str, force: bool = False
) -> GradeCheck | None:
    """Grade the instance if its template is auto-graded and it hasn't been
    graded yet. Lifecycle triggers (stop/destroy/reaper) swallow checker
    failures — teardown must never be blocked by grading — while ``force``
    (the student's explicit hand-in) propagates GradingUnavailable so the
    API can answer honestly. The caller owns the commit."""
    template = db.get(LabTemplate, instance.template_id)
    if template is None:
        return None
    scheme = published_scheme_for(db, template.id)
    if scheme is None:
        return None
    if instance.state is not InstanceState.running:
        return None  # the box is the evidence; nothing to read once it's gone
    if not force:
        existing = db.scalar(
            select(GradeCheck).where(GradeCheck.instance_id == instance.id)
        )
        if existing is not None:
            return None
    try:
        check = run_checks(db, instance, template, scheme, trigger)
        write_back(db, instance, template, scheme, check)
        return check
    except GradingUnavailable:
        if force:
            raise
        logger.warning("autograde skipped for %s: checker unavailable", instance.id)
        add_log(db, instance.id, "autograde skipped: checker unavailable", level="warn")
        return None

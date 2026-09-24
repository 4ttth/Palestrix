"""PalestrIX relational schema (SQLAlchemy 2.0, PostgreSQL-ready).

One module on purpose: the schema is the platform's shared contract across
the API, the Phase 4 orchestration workers, and the seed/import tooling.
Domain boundaries are marked by the section comments.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def uid() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime) -> datetime:
    """Normalize datetimes read back from the database. PostgreSQL returns
    aware values for timestamptz; SQLite (dev/test) returns naive UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


class Role(str, enum.Enum):
    student = "student"
    teacher = "teacher"
    admin = "admin"
    superadmin = "superadmin"


class InstanceState(str, enum.Enum):
    requested = "requested"
    provisioning = "provisioning"
    running = "running"
    stopped = "stopped"
    expired = "expired"
    failed = "failed"
    denied = "denied"


# States that hold real (or promised) resources and count against tenant
# quota. Quota is reserved at request time and released only by leaving
# these states (docs/ephemeral-lifecycle.md).
ACTIVE_STATES = (
    InstanceState.requested,
    InstanceState.provisioning,
    InstanceState.running,
    InstanceState.stopped,
)


# --------------------------------------------------------------------------
# Tenancy and identity
# --------------------------------------------------------------------------


class Tenant(Base):
    """A class section, an event, or a single student: the isolation unit.
    The tenant fixes its instances' network (``vlan_id`` on the trunk bridge
    baremetal, subnet/namespace on cloud), naming prefix, and quota pool
    (docs/ephemeral-lifecycle.md §Multitenancy invariants). ``cloud_ref`` is
    the Phase 7 cloud layer's handle for the materialized objects (OpenNebula
    group/VDC, CloudStack domain/account); archived tenants keep their row —
    ledger and instance history reference it — but can no longer launch."""

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # slug
    name: Mapped[str] = mapped_column(String(128))
    instance_quota: Mapped[int] = mapped_column(Integer, default=3)
    cpu_cap: Mapped[int] = mapped_column(Integer, default=48)
    ram_cap_gb: Mapped[int] = mapped_column(Integer, default=96)
    network_cidr: Mapped[str] = mapped_column(String(32), default="")
    vlan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cloud_ref: Mapped[str] = mapped_column(String(256), default="")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    handle: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    email: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.student)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    credentials: Mapped[list[WebAuthnCredential]] = relationship(back_populates="user")


class WebAuthnCredential(Base):
    __tablename__ = "webauthn_credentials"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    credential_id: Mapped[str] = mapped_column(String(512), unique=True)  # b64url
    public_key: Mapped[str] = mapped_column(Text)  # b64url
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    transports: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="credentials")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    prefix: Mapped[str] = mapped_column(String(16), index=True)  # plx_ + 8 chars
    key_hash: Mapped[str] = mapped_column(String(64))  # sha256 hex
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OAuthClient(Base):
    __tablename__ = "oauth_clients"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    client_id: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    secret_hash: Mapped[str] = mapped_column(String(64))  # sha256 hex
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(128))
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------
# Courses
# --------------------------------------------------------------------------


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    code: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(256))
    section: Mapped[str] = mapped_column(String(64), default="")
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), nullable=True)
    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("course_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    title: Mapped[str] = mapped_column(String(256))
    kind: Mapped[str] = mapped_column(String(16), default="file")  # file|quiz|lab|writeup
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lab_template_id: Mapped[str | None] = mapped_column(
        ForeignKey("lab_templates.id"), nullable=True
    )
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Lifecycle. "open" accepts submissions; "closed" keeps the assignment
    # visible and graded but refuses new ones; "archived" also hides it from
    # the student's course view. Deleting is a separate, destructive act —
    # closing is what a teacher usually means, and it keeps the gradebook.
    status: Mapped[str] = mapped_column(String(16), default="open")


ASSIGNMENT_STATUSES = ("open", "closed", "archived")


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("assignment_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    assignment_id: Mapped[str] = mapped_column(ForeignKey("assignments.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    grade: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0-100
    graded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------
# Academy
# --------------------------------------------------------------------------


class Path(Base):
    __tablename__ = "paths"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(128))
    hours: Mapped[int] = mapped_column(Integer, default=0)


class Module(Base):
    """One lesson in a path.

    ``body`` is Markdown shipped in the repository (academy_content/) rather
    than authored through the API, so lessons version with the code that
    grades them. ``lab_slug`` binds the module to a lab template: when that
    lab has a published grading scheme, completion is earned by passing it
    rather than claimed by pressing a button.
    """

    __tablename__ = "modules"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    path_id: Mapped[str] = mapped_column(ForeignKey("paths.id"), index=True)
    title: Mapped[str] = mapped_column(String(256))
    position: Mapped[int] = mapped_column(Integer, default=0)
    palestras_award: Mapped[int] = mapped_column(Integer, default=40)
    summary: Mapped[str] = mapped_column(String(512), default="")
    body: Mapped[str] = mapped_column(Text, default="")  # Markdown
    # Bound by slug, not id: lab templates are per-deployment rows, so the
    # repository catalog cannot know their ids, and a module may name a lab
    # that has not been imported here yet.
    lab_slug: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pass_percent: Mapped[int] = mapped_column(Integer, default=80)


class ModuleCompletion(Base):
    __tablename__ = "module_completions"
    __table_args__ = (UniqueConstraint("module_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    module_id: Mapped[str] = mapped_column(ForeignKey("modules.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------
# Labs and ephemeral instances
# --------------------------------------------------------------------------


class LabTemplate(Base):
    __tablename__ = "lab_templates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    slug: Mapped[str] = mapped_column(String(128), unique=True)  # log-triage:1.4
    title: Mapped[str] = mapped_column(String(256))
    kind: Mapped[str] = mapped_column(String(16), default="container")  # container|vm
    access_mode: Mapped[str] = mapped_column(String(16), default="no-gui")  # gui|no-gui
    ttl_minutes_default: Mapped[int] = mapped_column(Integer, default=90)
    ttl_minutes_max: Mapped[int] = mapped_column(Integer, default=240)
    # Per-instance resource spec, charged against the tenant's cpu_cap /
    # ram_cap_gb while the instance is in an active state (Phase 7).
    cpu: Mapped[int] = mapped_column(Integer, default=1)
    ram_gb: Mapped[int] = mapped_column(Integer, default=1)
    archive_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    vm_template: Mapped[str | None] = mapped_column(String(128), nullable=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Instance(Base):
    __tablename__ = "instances"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # lab-XXXX
    template_id: Mapped[str] = mapped_column(ForeignKey("lab_templates.id"))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    state: Mapped[InstanceState] = mapped_column(
        Enum(InstanceState), default=InstanceState.requested, index=True
    )
    node: Mapped[str] = mapped_column(String(64), default="")
    host: Mapped[str] = mapped_column(String(64), default="")
    port: Mapped[int] = mapped_column(Integer, default=0)
    proto: Mapped[str] = mapped_column(String(16), default="ssh")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    destroyed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InstanceLog(Base):
    __tablename__ = "instance_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    instance_id: Mapped[str] = mapped_column(ForeignKey("instances.id"), index=True)
    t: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    level: Mapped[str] = mapped_column(String(8), default="info")  # info|ok|warn
    msg: Mapped[str] = mapped_column(Text)


# --------------------------------------------------------------------------
# Automated checking (grading). A rubric attached to a lab template: the
# checker (palestrix/grading/) fills it from a real artifact diff or from
# generated win files, the teacher weights it to exactly 100%, and every
# student instance is scored against it at hand-in, stop, destroy, or TTL
# expiry — whichever comes first (docs/automated-checking.md).
# --------------------------------------------------------------------------


class GradingScheme(Base):
    """One rubric per lab template. ``diff`` schemes carry the finished
    reference artifact (the template's own archive is the unfinished system
    students receive); ``winfile`` schemes carry generated win scripts the
    teacher embeds and students must find and execute. Weights are editable
    while ``draft``; ``published`` locks the rubric and turns grading on."""

    __tablename__ = "grading_schemes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    lab_template_id: Mapped[str] = mapped_column(
        ForeignKey("lab_templates.id"), unique=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(16))  # diff|winfile
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft|published
    finished_archive_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # winfile mode: the randomized directory the win scripts write their
    # execution markers into. Random per scheme so markers can't be guessed
    # without finding a script.
    marker_dir: Mapped[str] = mapped_column(String(128), default="")
    analysis: Mapped[dict] = mapped_column(JSON, default=dict)  # diff summary
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class RubricItem(Base):
    """One gradeable objective. ``checks`` is the machine half the student
    never sees: for diff items a list of file expectations
    (``{"path", "sha256", "present"}``) taken from the finished system; for
    winfile items the marker path and the SHA-256 of the token the win
    script writes when executed."""

    __tablename__ = "rubric_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    scheme_id: Mapped[str] = mapped_column(ForeignKey("grading_schemes.id"), index=True)
    key: Mapped[str] = mapped_column(String(64))  # ssh, motd, win-1, ...
    title: Mapped[str] = mapped_column(String(256))
    detail: Mapped[str] = mapped_column(Text, default="")
    weight_percent: Mapped[int] = mapped_column(Integer, default=0)
    position: Mapped[int] = mapped_column(Integer, default=0)
    checks: Mapped[dict] = mapped_column(JSON, default=dict)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)  # win script


class GradeCheck(Base):
    """One grading run of one instance against its template's scheme.
    ``items`` is the student-safe breakdown (key, title, weight, passed);
    ``total_percent`` is the sum of passed weights. ``submission_id`` links
    the course submission the grade was written to, when one exists."""

    __tablename__ = "grade_checks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    scheme_id: Mapped[str] = mapped_column(ForeignKey("grading_schemes.id"), index=True)
    instance_id: Mapped[str] = mapped_column(ForeignKey("instances.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    submission_id: Mapped[str | None] = mapped_column(
        ForeignKey("submissions.id"), nullable=True
    )
    total_percent: Mapped[int] = mapped_column(Integer, default=0)
    items: Mapped[list] = mapped_column(JSON, default=list)
    trigger: Mapped[str] = mapped_column(String(16), default="student")  # student|stop|destroy|reaper
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------
# Gamification (append-only ledger + streak state; rules in gamification.py)
# --------------------------------------------------------------------------


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    delta: Mapped[int] = mapped_column(Integer)  # positive earn, negative spend
    reason: Mapped[str] = mapped_column(String(64))  # module.completed, flag.captured, ...
    ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Streak(Base):
    """Per-user daily-activity streak. One row per user, mutated in place by
    the gamification service (the ledger stays append-only; this is derived
    state, safe to recompute). ``weeks_paid`` records how many weekly
    checkpoints have already been rewarded so the same week is never paid
    twice; it resets to 0 whenever a gap breaks the streak."""

    __tablename__ = "streaks"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    current_days: Mapped[int] = mapped_column(Integer, default=0)
    longest_days: Mapped[int] = mapped_column(Integer, default=0)
    last_active_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    weeks_paid: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


# --------------------------------------------------------------------------
# Community
# --------------------------------------------------------------------------


class Writeup(Base):
    __tablename__ = "writeups"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(256))
    body_md: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    writeup_id: Mapped[str] = mapped_column(ForeignKey("writeups.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Vote(Base):
    __tablename__ = "votes"
    __table_args__ = (UniqueConstraint("writeup_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    writeup_id: Mapped[str] = mapped_column(ForeignKey("writeups.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    value: Mapped[int] = mapped_column(Integer, default=1)  # 1 or -1


# --------------------------------------------------------------------------
# Compete (CTF)
# --------------------------------------------------------------------------


class CtfEvent(Base):
    __tablename__ = "ctf_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    title: Mapped[str] = mapped_column(String(256))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class Challenge(Base):
    __tablename__ = "challenges"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    event_id: Mapped[str] = mapped_column(ForeignKey("ctf_events.id"), index=True)
    title: Mapped[str] = mapped_column(String(256))
    category: Mapped[str] = mapped_column(String(32))
    points: Mapped[int] = mapped_column(Integer, default=100)
    flag_hash: Mapped[str] = mapped_column(String(64))  # sha256 hex of exact flag
    palestras_award: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class FlagSubmission(Base):
    __tablename__ = "flag_submissions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    challenge_id: Mapped[str] = mapped_column(ForeignKey("challenges.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    correct: Mapped[bool] = mapped_column(Boolean, default=False)
    first_blood: Mapped[bool] = mapped_column(Boolean, default=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------
# Malware sandbox (Phase 6). A self-contained module: student-submitted
# samples detonate on a dedicated, network-isolated host and stream their
# file-system and network behavior back. Only these rows and the API contract
# cross into the rest of the platform (docs/sandbox-security.md).
# --------------------------------------------------------------------------


class SandboxVerdict(str, enum.Enum):
    unknown = "unknown"
    clean = "clean"
    suspicious = "suspicious"
    malicious = "malicious"


class SandboxRunState(str, enum.Enum):
    queued = "queued"
    static = "static"  # static pre-check; the sample has not executed
    detonating = "detonating"  # dynamic analysis inside the isolated container
    completed = "completed"
    failed = "failed"


# Runs that are still doing work; they hold the detonation slot.
SANDBOX_LIVE_STATES = (
    SandboxRunState.queued,
    SandboxRunState.static,
    SandboxRunState.detonating,
)


class SandboxSample(Base):
    """A submitted artifact, keyed by SHA-256 so re-submissions dedup to the
    same row (docs/sandbox-security.md, abuse: dropbox for classmates). The
    bytes live in the ``sandbox-samples`` bucket, encrypted at rest; only the
    metadata is relational."""

    __tablename__ = "sandbox_samples"

    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    filename: Mapped[str] = mapped_column(String(256))
    size: Mapped[int] = mapped_column(Integer, default=0)
    media_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    magic: Mapped[str] = mapped_column(String(64), default="")  # sniffed file type
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SandboxRun(Base):
    """One analysis of one sample. The report id is what the UI and the
    ``sandbox.report.ready`` webhook reference. Reports are private to the
    submitter unless ``shared`` opens them to the submitter's tenant."""

    __tablename__ = "sandbox_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # sbx-XXXXXX
    sample_sha256: Mapped[str] = mapped_column(
        ForeignKey("sandbox_samples.sha256"), index=True
    )
    submitter_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    tenant_id: Mapped[str | None] = mapped_column(
        ForeignKey("tenants.id"), nullable=True, index=True
    )
    detonator: Mapped[str] = mapped_column(String(32), default="")
    state: Mapped[SandboxRunState] = mapped_column(
        Enum(SandboxRunState), default=SandboxRunState.queued, index=True
    )
    verdict: Mapped[SandboxVerdict] = mapped_column(
        Enum(SandboxVerdict), default=SandboxVerdict.unknown
    )
    score: Mapped[int] = mapped_column(Integer, default=0)  # 0-100 threat score
    family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")  # SOC-handoff summary
    mitre: Mapped[list] = mapped_column(JSON, default=list)  # ATT&CK technique ids
    iocs: Mapped[dict] = mapped_column(JSON, default=dict)  # urls / ips / domains
    static: Mapped[dict] = mapped_column(JSON, default=dict)  # pre-check findings
    report_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    shared: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SandboxEvent(Base):
    """One behavior-trace line. ``category`` maps to a UI panel: ``process``
    (the live process tree), ``file`` (file-system diff), ``network`` (the
    fake-internet flows), ``static`` (pre-check findings), ``system`` (the
    coordinator's own status). ``data`` carries the structured detail the
    panel renders; ``msg`` is the human-readable line for the log view."""

    __tablename__ = "sandbox_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    run_id: Mapped[str] = mapped_column(ForeignKey("sandbox_runs.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)  # monotonic within a run
    t: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    category: Mapped[str] = mapped_column(String(16), default="system")
    level: Mapped[str] = mapped_column(String(8), default="info")  # info|ok|warn|alert
    msg: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


# --------------------------------------------------------------------------
# Plugins
# --------------------------------------------------------------------------


class PluginRecord(Base):
    __tablename__ = "plugin_records"

    plugin_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[str] = mapped_column(String(32), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    granted_scopes: Mapped[list] = mapped_column(JSON, default=list)
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # secrets encrypted
    oauth_client_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


# --------------------------------------------------------------------------
# Webhooks
# --------------------------------------------------------------------------


class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    url: Mapped[str] = mapped_column(String(1024))
    secret: Mapped[str] = mapped_column(String(64))  # HMAC key, shown once
    events: Mapped[list] = mapped_column(JSON, default=list)  # ["flag.captured", ...]
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    subscription_id: Mapped[str] = mapped_column(
        ForeignKey("webhook_subscriptions.id"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    signature: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|delivered|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------
# External platforms (Phase 8). Canvas LMS is the reference adapter
# (docs/integrations-canvas-lms.md): these rows are everything the core
# stores about an external platform — external ids, line-item ids, receipts.
# Platform tokens are never persisted; adapters mint them per call.
# --------------------------------------------------------------------------


class ExternalIdentity(Base):
    """One platform identity mapped onto a PalestrIX account. The mapping key
    is the LTI ``sub`` claim + issuer; ``email`` records what the platform
    asserted when the mapping was made (roster sync or first-launch claim)."""

    __tablename__ = "external_identities"
    __table_args__ = (UniqueConstraint("platform", "issuer", "subject"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    platform: Mapped[str] = mapped_column(String(32))  # "canvas-lms"
    issuer: Mapped[str] = mapped_column(String(256))
    subject: Mapped[str] = mapped_column(String(256))  # LTI sub claim
    email: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExternalCourseLink(Base):
    """A PalestrIX course bound to a platform course. The teacher creates the
    link with the platform's course id (``external_course_id``); the LTI
    context id and the NRPS membership URL are captured from the first launch
    out of that context (the launch claims are authoritative)."""

    __tablename__ = "external_course_links"
    __table_args__ = (UniqueConstraint("platform", "course_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    platform: Mapped[str] = mapped_column(String(32))
    external_course_id: Mapped[str] = mapped_column(String(64))  # e.g. Canvas course id
    context_id: Mapped[str] = mapped_column(String(256), default="")  # LTI context claim
    context_title: Mapped[str] = mapped_column(String(256), default="")
    nrps_url: Mapped[str] = mapped_column(String(1024), default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LtiResourceLink(Base):
    """One deep-linked content item as launched from the platform: maps the
    platform's resource link to the lab template it targets and the course's
    lab assignment for that template (grade passback needs the assignment).
    The AGS line-item URL arrives with the first launch and is refreshed on
    every launch after that."""

    __tablename__ = "lti_resource_links"
    __table_args__ = (UniqueConstraint("platform", "resource_link_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    platform: Mapped[str] = mapped_column(String(32))
    resource_link_id: Mapped[str] = mapped_column(String(256))
    link_id: Mapped[str | None] = mapped_column(
        ForeignKey("external_course_links.id"), nullable=True, index=True
    )
    lab_template_id: Mapped[str | None] = mapped_column(
        ForeignKey("lab_templates.id"), nullable=True
    )
    assignment_id: Mapped[str | None] = mapped_column(
        ForeignKey("assignments.id"), nullable=True, index=True
    )
    lineitem_url: Mapped[str] = mapped_column(String(1024), default="")
    title: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GradePassback(Base):
    """The grade-passback queue. A row is queued when a grade is posted on a
    linked course for a mapped student whose assignment has a bound line item;
    the dispatcher (integrations/passback.py) delivers with exponential
    backoff and keeps the receipt. Failures stay queryable in the teacher's
    course view, never silent (docs/integrations-canvas-lms.md)."""

    __tablename__ = "grade_passbacks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    platform: Mapped[str] = mapped_column(String(32))
    link_id: Mapped[str] = mapped_column(ForeignKey("external_course_links.id"), index=True)
    assignment_id: Mapped[str] = mapped_column(ForeignKey("assignments.id"), index=True)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)  # the student
    lineitem_url: Mapped[str] = mapped_column(String(1024))
    external_user_id: Mapped[str] = mapped_column(String(256))  # LTI sub on the platform
    score_given: Mapped[int] = mapped_column(Integer)  # 0-100 (GradeIn's scale)
    score_maximum: Mapped[int] = mapped_column(Integer, default=100)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending|delivered|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    receipt: Mapped[str] = mapped_column(String(256), default="")  # platform's ack
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

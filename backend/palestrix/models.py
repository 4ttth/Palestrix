"""PalestrIX relational schema (SQLAlchemy 2.0, PostgreSQL-ready).

One module on purpose: the schema is the platform's shared contract across
the API, the Phase 4 orchestration workers, and the seed/import tooling.
Domain boundaries are marked by the section comments.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
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


# --------------------------------------------------------------------------
# Tenancy and identity
# --------------------------------------------------------------------------


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # slug
    name: Mapped[str] = mapped_column(String(128))
    instance_quota: Mapped[int] = mapped_column(Integer, default=3)
    cpu_cap: Mapped[int] = mapped_column(Integer, default=48)
    ram_cap_gb: Mapped[int] = mapped_column(Integer, default=96)
    network_cidr: Mapped[str] = mapped_column(String(32), default="")
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
    __tablename__ = "modules"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    path_id: Mapped[str] = mapped_column(ForeignKey("paths.id"), index=True)
    title: Mapped[str] = mapped_column(String(256))
    position: Mapped[int] = mapped_column(Integer, default=0)
    palestras_award: Mapped[int] = mapped_column(Integer, default=40)


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
# Gamification (ledger only in Phase 2; rules land in Phase 3)
# --------------------------------------------------------------------------


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    delta: Mapped[int] = mapped_column(Integer)  # positive earn, negative spend
    reason: Mapped[str] = mapped_column(String(64))  # module.completed, flag.captured, ...
    ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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

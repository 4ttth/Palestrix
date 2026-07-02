"""Pydantic request/response models for /api/v1. Response models never leak
hashes, secrets (beyond one-time reveals), or other principals' data."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import InstanceState, Role


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# -- auth ----------------------------------------------------------------------


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    handle: str = Field(pattern=r"^[a-z0-9_-]{3,20}$")
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(ORMModel):
    id: str
    handle: str
    name: str
    email: EmailStr
    role: Role
    tenant_id: str | None


class PublicProfileOut(ORMModel):
    handle: str
    name: str
    role: Role


class WebAuthnVerifyIn(BaseModel):
    credential: str  # JSON string from navigator.credentials


class WebAuthnLoginOptionsIn(BaseModel):
    email: EmailStr


class ApiKeyCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    scopes: list[str]


class ApiKeyOut(ORMModel):
    id: str
    name: str
    prefix: str
    scopes: list[str]
    revoked: bool
    created_at: datetime


class ApiKeyCreatedOut(ApiKeyOut):
    key: str  # full key, shown exactly once


class OAuthClientCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    scopes: list[str]


class OAuthClientCreatedOut(BaseModel):
    client_id: str
    client_secret: str  # shown exactly once
    name: str
    scopes: list[str]


class ClientTokenIn(BaseModel):
    grant_type: str = "client_credentials"
    client_id: str
    client_secret: str


# -- courses --------------------------------------------------------------------


class CourseIn(BaseModel):
    code: str
    title: str
    section: str = ""
    tenant_id: str | None = None


class CourseOut(ORMModel):
    id: str
    code: str
    title: str
    section: str
    tenant_id: str | None
    teacher_id: str


class AssignmentIn(BaseModel):
    title: str
    kind: str = Field(default="file", pattern="^(file|quiz|lab|writeup)$")
    due_at: datetime | None = None
    lab_template_id: str | None = None


class AssignmentOut(ORMModel):
    id: str
    course_id: str
    title: str
    kind: str
    due_at: datetime | None
    lab_template_id: str | None
    storage_key: str | None


class SubmissionOut(ORMModel):
    id: str
    assignment_id: str
    user_id: str
    grade: int | None
    submitted_at: datetime


class GradeIn(BaseModel):
    grade: int = Field(ge=0, le=100)


# -- academy ----------------------------------------------------------------------


class PathOut(ORMModel):
    id: str
    slug: str
    title: str
    hours: int


class ModuleOut(ORMModel):
    id: str
    path_id: str
    title: str
    position: int
    palestras_award: int


# -- labs and instances -------------------------------------------------------------


class LabTemplateOut(ORMModel):
    id: str
    slug: str
    title: str
    kind: str
    access_mode: str
    ttl_minutes_default: int
    ttl_minutes_max: int


class InstanceCreateIn(BaseModel):
    template_id: str
    ttl_minutes: int | None = Field(default=None, ge=15, le=480)


class InstanceOut(ORMModel):
    id: str
    template_id: str
    owner_id: str
    tenant_id: str
    state: InstanceState
    node: str
    host: str
    port: int
    proto: str
    expires_at: datetime | None
    created_at: datetime


class InstanceLogOut(ORMModel):
    t: datetime
    level: str
    msg: str


class ExtendIn(BaseModel):
    minutes: int = Field(default=30, ge=15, le=120)


# -- gamification --------------------------------------------------------------------


class BalanceOut(BaseModel):
    user_id: str
    palestras: int


class LedgerEntryOut(ORMModel):
    delta: int
    reason: str
    ref: str | None
    created_at: datetime


# -- community -----------------------------------------------------------------------


class WriteupIn(BaseModel):
    title: str = Field(min_length=4, max_length=256)
    body_md: str = ""
    tags: list[str] = []
    published: bool = False


class WriteupOut(ORMModel):
    id: str
    author_id: str
    title: str
    body_md: str
    tags: list[str]
    published: bool
    created_at: datetime
    votes: int = 0


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


# -- compete -------------------------------------------------------------------------


class CtfEventIn(BaseModel):
    title: str
    starts_at: datetime
    ends_at: datetime
    tenant_id: str | None = None


class CtfEventOut(ORMModel):
    id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    tenant_id: str | None


class ChallengeIn(BaseModel):
    title: str
    category: str
    points: int = Field(ge=1, le=1000)
    flag: str = Field(min_length=4)  # hashed at rest, never returned
    palestras_award: int = Field(default=0, ge=0, le=1000)


class ChallengeOut(ORMModel):
    id: str
    event_id: str
    title: str
    category: str
    points: int
    solves: int = 0
    first_blood: str | None = None  # handle


class FlagSubmitIn(BaseModel):
    flag: str


class FlagResultOut(BaseModel):
    correct: bool
    first_blood: bool = False
    points: int = 0
    palestras: int = 0


class LeaderboardRowOut(BaseModel):
    rank: int
    handle: str
    score: int
    first_bloods: int


# -- admin ----------------------------------------------------------------------------


class TenantIn(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]{3,64}$")
    name: str
    instance_quota: int = Field(default=3, ge=0, le=1024)
    cpu_cap: int = 48
    ram_cap_gb: int = 96
    network_cidr: str = ""


class TenantOut(ORMModel):
    id: str
    name: str
    instance_quota: int
    cpu_cap: int
    ram_cap_gb: int
    network_cidr: str


class RoleChangeIn(BaseModel):
    role: Role


# -- plugins ------------------------------------------------------------------


class PluginOut(BaseModel):
    id: str
    name: str
    version: str
    api: str
    source: str
    state: str
    error: str | None = None
    scopes: list[str]  # requested by the manifest
    granted_scopes: list[str] = []
    config_required: list[str] = []
    config_optional: list[str] = []
    config_secret: list[str] = []


class PluginEnableIn(BaseModel):
    config: dict = {}
    approve_scopes: list[str] | None = None


# -- webhooks -----------------------------------------------------------------------


class WebhookCreateIn(BaseModel):
    url: str = Field(pattern=r"^https?://")
    events: list[str]


class WebhookOut(ORMModel):
    id: str
    url: str
    events: list[str]
    active: bool
    created_at: datetime


class WebhookCreatedOut(WebhookOut):
    secret: str  # shown exactly once


class WebhookDeliveryOut(ORMModel):
    id: str
    event_type: str
    status: str
    attempts: int
    created_at: datetime

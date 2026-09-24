"""Pydantic request/response models for /api/v1. Response models never leak
hashes, secrets (beyond one-time reveals), or other principals' data."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import InstanceState, Role, SandboxRunState, SandboxVerdict


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
    created_at: datetime | None = None


class UserCreateIn(BaseModel):
    """Staff-created account (users:manage). Unlike self-registration the
    role is chosen up front; rbac rules in the endpoint keep admins from
    minting admin/superadmin accounts."""

    name: str = Field(min_length=2, max_length=128)
    handle: str = Field(pattern=r"^[a-z0-9_.-]{3,32}$")
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    role: Role = Role.student
    tenant_id: str | None = None


class UserTenantIn(BaseModel):
    tenant_id: str | None = None  # None clears the assignment


class ProfilePatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=128)


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=256)


class PublicProfileOut(ORMModel):
    handle: str
    name: str
    role: Role
    community_score: int = 0  # recency-decayed contribution (gamification.py)


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
    students: int = 0  # enrollment count
    assignments: int = 0


class AssignmentIn(BaseModel):
    title: str
    kind: str = Field(default="file", pattern="^(file|quiz|lab|writeup)$")
    due_at: datetime | None = None
    lab_template_id: str | None = None


class AssignmentUpdateIn(BaseModel):
    """Every field optional: a PATCH carries only what changed, and
    ``None`` on an optional column is a real value (clear the due date),
    so the endpoint distinguishes "absent" from "null" via
    ``model_fields_set`` rather than treating None as absent."""

    title: str | None = None
    kind: str | None = Field(default=None, pattern="^(file|quiz|lab|writeup)$")
    due_at: datetime | None = None
    lab_template_id: str | None = None
    status: str | None = Field(default=None, pattern="^(open|closed|archived)$")


class AssignmentOut(ORMModel):
    id: str
    course_id: str
    title: str
    kind: str
    due_at: datetime | None
    lab_template_id: str | None
    storage_key: str | None
    status: str = "open"
    submissions: int = 0
    graded: int = 0


class SubmissionOut(ORMModel):
    id: str
    assignment_id: str
    user_id: str
    grade: int | None
    submitted_at: datetime


class GradeIn(BaseModel):
    grade: int = Field(ge=0, le=100)


class EnrollIn(BaseModel):
    handle: str = Field(min_length=3, max_length=32)


class RosterRowOut(BaseModel):
    """One enrolled student in the teacher's roster panel."""

    user_id: str
    handle: str
    name: str
    email: EmailStr
    enrolled_at: datetime


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
    completed: bool = False  # by the calling principal
    summary: str = ""
    has_body: bool = False   # a lesson is written; the list links to it
    lab_slug: str | None = None
    pass_percent: int = 80
    gated: bool = False      # completion requires passing the lab


class ModuleLabOut(BaseModel):
    """The caller's standing against a module's lab."""

    slug: str
    title: str = ""
    available: bool = False          # the template exists on this deployment
    scheme_published: bool = False   # grading is on, so the gate is live
    pass_percent: int = 80
    best_percent: int | None = None  # this caller's best run
    passed: bool = False


class ModuleDetailOut(ModuleOut):
    body: str = ""                   # Markdown; empty until the lesson is written
    lab: ModuleLabOut | None = None
    locked_reason: str = ""          # why complete would be refused, if it would


# -- labs and instances -------------------------------------------------------------


class LabTemplateOut(ORMModel):
    id: str
    slug: str
    title: str
    kind: str
    access_mode: str
    ttl_minutes_default: int
    ttl_minutes_max: int
    cpu: int
    ram_gb: int
    owner_id: str


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
    # Display enrichment (filled by the router from the template and owner
    # rows) so clients never need N+1 follow-up requests.
    kind: str = ""
    access_mode: str = ""
    template_slug: str = ""
    template_title: str = ""
    owner_handle: str = ""


class InstanceLogOut(ORMModel):
    t: datetime
    level: str
    msg: str


class ExtendIn(BaseModel):
    minutes: int = Field(default=30, ge=15, le=120)


# -- automated checking (grading) ---------------------------------------------------


class RubricItemOut(ORMModel):
    """Teacher view of one objective. ``paths`` summarizes what the checker
    will inspect; the expected hashes stay server-side."""

    id: str
    key: str
    title: str
    detail: str
    weight_percent: int
    position: int
    paths: list[str] = []
    win_filename: str | None = None


class RubricItemPublicOut(BaseModel):
    """Student view: the rubric they are graded on, never the answers —
    no paths, no marker locations, no hashes."""

    key: str
    title: str
    weight_percent: int


class GradingSchemeOut(ORMModel):
    id: str
    lab_template_id: str
    kind: str
    status: str
    analysis: dict = {}
    items: list[RubricItemOut] = []
    created_at: datetime
    published_at: datetime | None = None


class GradingWeightsIn(BaseModel):
    weights: dict[str, int]  # rubric item id -> percent


class GradeCheckOut(ORMModel):
    id: str
    instance_id: str
    total_percent: int
    trigger: str
    items: list = []
    created_at: datetime


class InstanceGradingOut(BaseModel):
    """What a student sees on their lab page: the rubric (if the template is
    auto-graded) and their latest result (if a check has run)."""

    scheme_kind: str | None = None
    scheme_status: str | None = None
    rubric: list[RubricItemPublicOut] = []
    result: GradeCheckOut | None = None


class GradebookRowOut(BaseModel):
    """One student row in the teacher's per-assignment gradebook."""

    submission_id: str
    user_id: str
    handle: str
    name: str
    grade: int | None
    submitted_at: datetime
    auto: GradeCheckOut | None = None


# -- gamification --------------------------------------------------------------------


class BalanceOut(BaseModel):
    user_id: str
    palestras: int


class LedgerEntryOut(ORMModel):
    delta: int
    reason: str
    ref: str | None
    created_at: datetime


class StreakOut(ORMModel):
    current_days: int
    longest_days: int
    last_active_on: date | None
    weeks_paid: int


class GamificationSummaryOut(BaseModel):
    user_id: str
    handle: str
    palestras: int  # current spendable balance
    lifetime_earned: int
    spent: int
    streak_days: int
    longest_streak: int
    community_score: int
    first_bloods: int
    rank: int | None  # position on the global Palestras board (None for staff)


class LeaderboardEntryOut(BaseModel):
    rank: int
    handle: str
    score: int  # lifetime earned Palestras, or community score for that board
    delta: int  # last 7 days' earnings (Palestras board); 0 on the community board
    first_bloods: int
    streak_days: int


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
    author_handle: str = ""
    comments: int = 0


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class CommentOut(ORMModel):
    id: str
    body: str
    created_at: datetime
    author_handle: str = ""


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
    first_blood_at: datetime | None = None
    solved: bool = False  # by the calling principal


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


# -- sandbox ---------------------------------------------------------------------------


class SandboxReportOut(ORMModel):
    id: str
    sample_sha256: str
    filename: str = ""  # from the sample row (enrichment)
    size: int = 0
    media_type: str = ""
    magic: str = ""
    detonator: str
    state: SandboxRunState
    verdict: SandboxVerdict
    score: int
    family: str | None
    summary: str
    mitre: list[str] = []
    iocs: dict = {}
    static: dict = {}
    shared: bool
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None
    # Enrichment so the list view needs no follow-up requests.
    submitter_handle: str = ""
    events: int = 0
    resubmission: bool = False  # this exact SHA-256 was analyzed before


class SandboxEventOut(ORMModel):
    seq: int
    t: datetime
    category: str
    level: str
    msg: str
    data: dict = {}


class SandboxArtifactOut(BaseModel):
    key: str
    size: int
    last_modified: datetime | None = None


class SandboxShareIn(BaseModel):
    shared: bool


class SandboxCommandIn(BaseModel):
    """A command-line submission.

    The command is analysed and detonated exactly like an uploaded script --
    it is stored as the sample's bytes, so dedup, sealing, the report and the
    artifact trail all work unchanged. Obfuscated input is expected and is the
    normal case, not an error.
    """

    command: str = Field(min_length=1, max_length=64_000)
    shell: str = Field(default="powershell", pattern=r"^powershell$")


class RemoteAccessOut(BaseModel):
    """How a student is expected to reach a lab endpoint in this deployment.

    Lab instances live on an isolated tenant VLAN, so the address the lab page
    prints is unreachable from wherever the student is sitting until they join
    the overlay. This is what the connection help renders; ``configured`` is
    False when no overlay is set up, and the UI then says so plainly instead
    of printing instructions that cannot work."""

    kind: str = "netbird"
    configured: bool
    management_url: str = ""
    network_name: str = ""
    setup_key_url: str = ""
    docs_url: str = ""
    # The shared join key and a ready-to-run command, present only when the
    # deployment configured a key. The modal renders the command as one
    # copy-paste step instead of sending the student to the NetBird console
    # for a key of their own — this deployment shares one.
    setup_key: str = ""
    join_command: str = ""


class NetBirdPeerOut(BaseModel):
    id: str
    name: str
    ip: str = ""
    connected: bool
    last_seen: datetime | None = None
    os: str = ""
    groups: list[str] = []
    is_student: bool = False
    is_protected: bool = False


class NetBirdStatusOut(BaseModel):
    """The superadmin overlay console: is NetBird wired, and how full is it.

    ``configured`` is False when no API token is set — the overlay still works
    (native reaping does not need this token), but the live view and the manual
    reap are off. ``error`` carries a NetBird-side failure so the console shows
    why it is blank instead of an empty list."""

    configured: bool
    management_url: str = ""
    network_name: str = ""
    peer_limit: int = 0
    total: int = 0
    connected: int = 0
    students: int = 0
    reapable: int = 0
    peers: list[NetBirdPeerOut] = []
    error: str | None = None


class NetBirdReapOut(BaseModel):
    reaped: list[str] = []  # peer names removed
    kept: int = 0  # student peers still online, deliberately spared
    errors: list[str] = []


class SandboxStatusOut(BaseModel):
    """What the /sandbox surface renders instead of guessing from a 501: is a
    live detonation host wired, or is the demo detonator answering?"""

    enabled: bool
    detonator: str
    live: bool  # True only when a real isolated host is configured
    max_sample_mb: int
    wall_clock_seconds: int
    max_command_chars: int = 64_000
    shells: list[str] = []          # command kinds this deployment detonates


# -- admin ----------------------------------------------------------------------------


class TenantIn(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]{3,64}$")
    name: str
    instance_quota: int = Field(default=3, ge=0, le=1024)
    cpu_cap: int = Field(default=48, ge=0, le=4096)
    ram_cap_gb: int = Field(default=96, ge=0, le=16384)
    network_cidr: str = ""  # blank: carved from PALESTRIX_TENANT_CIDR_POOL


class TenantPatchIn(BaseModel):
    """Quota/naming edits. The id, VLAN, and CIDR are fixed at creation —
    reissuing a tenant's network would break the isolation invariants
    (docs/ephemeral-lifecycle.md)."""

    name: str | None = None
    instance_quota: int | None = Field(default=None, ge=0, le=1024)
    cpu_cap: int | None = Field(default=None, ge=0, le=4096)
    ram_cap_gb: int | None = Field(default=None, ge=0, le=16384)


class TenantOut(ORMModel):
    id: str
    name: str
    instance_quota: int
    cpu_cap: int
    ram_cap_gb: int
    network_cidr: str
    vlan_id: int | None
    cloud_ref: str
    archived: bool
    instances_active: int = 0
    cpu_active: int = 0
    ram_active_gb: int = 0


class CloudOut(BaseModel):
    """The active multitenant cloud layer (local, opennebula, cloudstack)."""

    name: str
    tenants: int = 0
    tenants_archived: int = 0


class RoleChangeIn(BaseModel):
    role: Role


class StoredObjectOut(BaseModel):
    key: str
    size: int
    last_modified: datetime | None = None
    # Where this copy lives. "storage" is Palestrix's own object store;
    # "cluster" is the hypervisor's ISO storage, which is what provisioning
    # can actually boot from. An ISO uploaded through Palestrix reaches both
    # and is reported once, as "both".
    source: str = "storage"


class VmTemplateOut(BaseModel):
    """A bootable template on the hypervisor, offered to the lab-template
    editor so ``vm_template`` is picked from a list instead of typed."""

    name: str
    vmid: int
    cpu: int = 0
    ram_mb: int = 0


class ProviderOut(BaseModel):
    name: str
    kinds: list[str]
    instances_active: int = 0


class ProviderCheckOut(BaseModel):
    """Result of a provider connectivity self-test (admin console)."""

    name: str
    ok: bool
    detail: str


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


# -- integrations (Phase 8) -----------------------------------------------------------


class IntegrationPlatformOut(BaseModel):
    """One active external platform. ``ephemeral_key`` warns that the tool
    signing key was generated at startup (dev mode; launches break when a
    restart rotates the published JWKS)."""

    id: str
    name: str
    issuer: str
    features: list[str] = []
    ephemeral_key: bool = False


class ExternalLinkIn(BaseModel):
    course_id: str
    platform: str = "canvas-lms"
    external_course_id: str = Field(min_length=1, max_length=64)


class ExternalLinkOut(ORMModel):
    id: str
    course_id: str
    platform: str
    external_course_id: str
    context_id: str
    context_title: str
    last_synced_at: datetime | None
    created_at: datetime
    # Grade-queue counts so the course view renders health at a glance.
    grades_pending: int = 0
    grades_delivered: int = 0
    grades_failed: int = 0


class RosterSyncOut(BaseModel):
    roster: int  # members the platform reported
    added: int  # new enrollments
    provisioned: int  # accounts pre-created (claimed on first launch)
    removed: int  # drops (platform-mapped students no longer on the roster)
    skipped: int  # members without an e-mail to key an account on


class GradePassbackOut(ORMModel):
    id: str
    assignment_id: str
    user_id: str
    score_given: int
    score_maximum: int
    status: str  # pending | delivered | failed
    attempts: int
    next_attempt_at: datetime
    receipt: str
    error: str | None
    created_at: datetime
    delivered_at: datetime | None
    # Enrichment for the teacher's course view.
    student_handle: str = ""
    assignment_title: str = ""


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

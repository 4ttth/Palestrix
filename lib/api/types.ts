/*
 * Wire types for /api/v1, mirroring backend/palestrix/schemas.py
 * (snake_case, exactly as serialized). These are the single source of
 * truth for what the live API returns; lib/mock.ts shapes are retired
 * from the product surfaces as of Phase 5.
 */

export type Role = "student" | "teacher" | "admin" | "superadmin";

export type InstanceState =
  | "requested"
  | "provisioning"
  | "running"
  | "stopped"
  | "expired"
  | "failed";

// -- auth ---------------------------------------------------------------------

export type TokenOut = { access_token: string; token_type: string };

export type UserOut = {
  id: string;
  handle: string;
  name: string;
  email: string;
  role: Role;
  tenant_id: string | null;
  created_at?: string | null;
};

export type ApiKeyOut = {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  revoked: boolean;
  created_at: string;
};

/** POST /auth/api-keys response; `key` is shown exactly once. */
export type ApiKeyCreatedOut = ApiKeyOut & { key: string };

export type PasskeyOut = {
  id: string;
  created_at: string;
  transports: string[];
};

export type PublicProfileOut = {
  handle: string;
  name: string;
  role: Role;
  community_score: number;
};

// -- courses ------------------------------------------------------------------

export type CourseOut = {
  id: string;
  code: string;
  title: string;
  section: string;
  tenant_id: string | null;
  teacher_id: string;
  students: number;
  assignments: number;
};

export type AssignmentKind = "file" | "quiz" | "lab" | "writeup";

/** open accepts submissions; closed keeps it visible but refuses new ones;
 * archived also drops it off the student's course page. */
export type AssignmentStatus = "open" | "closed" | "archived";

export type AssignmentOut = {
  id: string;
  course_id: string;
  title: string;
  kind: AssignmentKind;
  due_at: string | null;
  lab_template_id: string | null;
  storage_key: string | null;
  status: AssignmentStatus;
  submissions: number;
  graded: number;
};

// -- academy ------------------------------------------------------------------

export type PathOut = {
  id: string;
  slug: string;
  title: string;
  hours: number;
};

export type ModuleOut = {
  id: string;
  path_id: string;
  title: string;
  position: number;
  palestras_award: number;
  completed: boolean;
  summary: string;
  has_body: boolean;            // a lesson is written for this module
  lab_slug: string | null;
  pass_percent: number;
  gated: boolean;               // completion requires passing the lab
};

export type ModuleLabOut = {
  slug: string;
  title: string;
  available: boolean;           // the template exists on this deployment
  scheme_published: boolean;    // grading is on, so the gate is live
  pass_percent: number;
  best_percent: number | null;
  passed: boolean;
};

export type ModuleDetailOut = ModuleOut & {
  body: string;                 // Markdown
  lab: ModuleLabOut | null;
  locked_reason: string;
};

// -- labs and instances ---------------------------------------------------------

/* GET /instances/access — how a student reaches a lab endpoint in this
 * deployment. Lab VMs sit on an isolated tenant VLAN, so the address the lab
 * page prints is unreachable until the client joins the overlay.
 * `configured: false` means no overlay is set up; render that plainly rather
 * than printing steps that cannot work. */
export type RemoteAccessOut = {
  kind: string;
  configured: boolean;
  management_url: string;
  network_name: string;
  setup_key_url: string;
  docs_url: string;
  /** The shared reusable join key and a ready-to-run command, present only
   * when the deployment configured a key (this one shares one key for the
   * whole cohort rather than a NetBird user per student). */
  setup_key: string;
  join_command: string;
  /** Shared SSH login for a lab VM, shown in the connect modal. */
  lab_username: string;
  lab_password: string;
};

export type NetBirdPeerOut = {
  id: string;
  name: string;
  ip: string;
  connected: boolean;
  last_seen: string | null;
  os: string;
  groups: string[];
  is_student: boolean;
  is_protected: boolean;
};

export type NetBirdStatusOut = {
  configured: boolean;
  management_url: string;
  network_name: string;
  peer_limit: number;
  total: number;
  connected: number;
  students: number;
  reapable: number;
  peers: NetBirdPeerOut[];
  error: string | null;
};

export type NetBirdReapOut = {
  reaped: string[];
  kept: number;
  errors: string[];
};


export type LabTemplateOut = {
  id: string;
  slug: string;
  title: string;
  kind: string;
  access_mode: "gui" | "no-gui";
  ttl_minutes_default: number;
  ttl_minutes_max: number;
  cpu: number;
  ram_gb: number;
  owner_id: string;
};

export type InstanceOut = {
  id: string;
  template_id: string;
  owner_id: string;
  tenant_id: string;
  state: InstanceState;
  node: string;
  host: string;
  port: number;
  proto: string;
  expires_at: string | null;
  created_at: string;
  kind: string;
  access_mode: string;
  template_slug: string;
  template_title: string;
  owner_handle: string;
};

export type InstanceLogOut = {
  t: string;
  level: "info" | "ok" | "warn";
  msg: string;
};

// -- gamification ----------------------------------------------------------------

export type BalanceOut = { user_id: string; palestras: number };

export type LedgerEntryOut = {
  delta: number;
  reason: string;
  ref: string | null;
  created_at: string;
};

export type StreakOut = {
  current_days: number;
  longest_days: number;
  last_active_on: string | null;
  weeks_paid: number;
};

export type GamificationSummaryOut = {
  user_id: string;
  handle: string;
  palestras: number;
  lifetime_earned: number;
  spent: number;
  streak_days: number;
  longest_streak: number;
  community_score: number;
  first_bloods: number;
  rank: number | null;
};

export type LeaderboardEntryOut = {
  rank: number;
  handle: string;
  score: number;
  delta: number;
  first_bloods: number;
  streak_days: number;
};

// -- course rosters -----------------------------------------------------------

export type RosterRowOut = {
  user_id: string;
  handle: string;
  name: string;
  email: string;
  enrolled_at: string;
};

// -- community -------------------------------------------------------------------

export type CommentOut = {
  id: string;
  body: string;
  created_at: string;
  author_handle: string;
};

export type WriteupOut = {
  id: string;
  author_id: string;
  title: string;
  body_md: string;
  tags: string[];
  published: boolean;
  created_at: string;
  votes: number;
  author_handle: string;
  comments: number;
};

// -- compete ---------------------------------------------------------------------

export type CtfEventOut = {
  id: string;
  title: string;
  starts_at: string;
  ends_at: string;
  tenant_id: string | null;
};

export type ChallengeOut = {
  id: string;
  event_id: string;
  title: string;
  category: string;
  points: number;
  solves: number;
  first_blood: string | null;
  first_blood_at: string | null;
  solved: boolean;
};

export type FlagResultOut = {
  correct: boolean;
  first_blood: boolean;
  points: number;
  palestras: number;
};

export type LeaderboardRowOut = {
  rank: number;
  handle: string;
  score: number;
  first_bloods: number;
};

// -- admin -----------------------------------------------------------------------

export type TenantOut = {
  id: string;
  name: string;
  instance_quota: number;
  cpu_cap: number;
  ram_cap_gb: number;
  network_cidr: string;
  vlan_id: number | null;
  cloud_ref: string;
  archived: boolean;
  instances_active: number;
  cpu_active: number;
  ram_active_gb: number;
};

/** The active multitenant cloud layer (local, opennebula, cloudstack). */
export type CloudOut = {
  name: string;
  tenants: number;
  tenants_archived: number;
};

export type StoredObjectOut = {
  key: string;
  size: number;
  last_modified: string | null;
  /** Which store holds it: Palestrix's object storage, the hypervisor's
   * ISO storage (what provisioning can actually attach), or both. */
  source: "storage" | "cluster" | "both";
};

/** GET /admin/vm-templates — the hypervisor's own bootable templates. */
export type VmTemplateOut = {
  name: string;
  vmid: number;
  cpu: number;
  ram_mb: number;
};

export type ProviderOut = {
  name: string;
  kinds: string[];
  instances_active: number;
};

/** POST /admin/providers/{name}/check — provider connectivity self-test. */
export type ProviderCheckOut = {
  name: string;
  ok: boolean;
  detail: string;
};

// -- plugins (superadmin console) ---------------------------------------------

export type PluginOut = {
  id: string;
  name: string;
  version: string;
  api: string;
  source: string;
  state: string;
  error: string | null;
  scopes: string[];
  granted_scopes: string[];
  config_required: string[];
  config_optional: string[];
  config_secret: string[];
};

// -- sandbox (Phase 6) -----------------------------------------------------------

export type SandboxVerdict = "unknown" | "clean" | "suspicious" | "malicious";

export type SandboxRunState =
  | "queued"
  | "static"
  | "detonating"
  | "completed"
  | "failed";

export type SandboxIocs = {
  urls?: string[];
  ips?: string[];
  domains?: string[];
};

export type SandboxStatic = {
  file_type?: string;
  media_type?: string;
  size?: number;
  entropy?: number;
  packed?: boolean;
  is_eicar?: boolean;
  strings_sample?: string[];
  notes?: string[];
};

export type SandboxReportOut = {
  id: string;
  sample_sha256: string;
  filename: string;
  size: number;
  media_type: string;
  magic: string;
  detonator: string;
  state: SandboxRunState;
  verdict: SandboxVerdict;
  score: number;
  family: string | null;
  summary: string;
  mitre: string[];
  iocs: SandboxIocs;
  static: SandboxStatic;
  shared: boolean;
  error: string | null;
  created_at: string;
  completed_at: string | null;
  submitter_handle: string;
  events: number;
  resubmission: boolean;
};

export type SandboxEventOut = {
  seq: number;
  t: string;
  category: "process" | "file" | "network" | "static" | "memory" | "system";
  level: "info" | "ok" | "warn" | "alert";
  msg: string;
  data: Record<string, unknown>;
};

export type SandboxArtifactOut = {
  key: string;
  size: number;
  last_modified: string | null;
};

export type SandboxStatusOut = {
  enabled: boolean;
  detonator: string;
  live: boolean;
  max_sample_mb: number;
  wall_clock_seconds: number;
  max_command_chars: number;
  shells: string[];          // command kinds this deployment detonates
};

/* -- integrations (Phase 8) ------------------------------------------------ */

export type IntegrationPlatformOut = {
  id: string;
  name: string;
  issuer: string;
  features: string[];
  ephemeral_key: boolean;
};

export type ExternalLinkOut = {
  id: string;
  course_id: string;
  platform: string;
  external_course_id: string;
  context_id: string;
  context_title: string;
  last_synced_at: string | null;
  created_at: string;
  grades_pending: number;
  grades_delivered: number;
  grades_failed: number;
};

export type RosterSyncOut = {
  roster: number;
  added: number;
  provisioned: number;
  removed: number;
  skipped: number;
};

export type GradePassbackOut = {
  id: string;
  assignment_id: string;
  user_id: string;
  score_given: number;
  score_maximum: number;
  status: "pending" | "delivered" | "failed";
  attempts: number;
  next_attempt_at: string;
  receipt: string;
  error: string | null;
  created_at: string;
  delivered_at: string | null;
  student_handle: string;
  assignment_title: string;
};

// -- automated checking (grading) ----------------------------------------------

export type RubricItemOut = {
  id: string;
  key: string;
  title: string;
  detail: string;
  weight_percent: number;
  position: number;
  paths: string[];
  win_filename: string | null;
};

export type GradingSchemeOut = {
  id: string;
  lab_template_id: string;
  kind: "diff" | "winfile";
  status: "draft" | "published";
  analysis: {
    differences?: number;
    changes?: { path: string; change: "added" | "modified" | "removed" }[];
  };
  items: RubricItemOut[];
  created_at: string;
  published_at: string | null;
};

export type RubricItemPublic = {
  key: string;
  title: string;
  weight_percent: number;
};

export type GradeCheckItem = {
  key: string;
  title: string;
  weight_percent: number;
  passed: boolean;
};

export type GradeCheckOut = {
  id: string;
  instance_id: string;
  total_percent: number;
  trigger: "student" | "stop" | "destroy" | "reaper";
  items: GradeCheckItem[];
  created_at: string;
};

export type InstanceGradingOut = {
  scheme_kind: "diff" | "winfile" | null;
  scheme_status: string | null;
  rubric: RubricItemPublic[];
  result: GradeCheckOut | null;
};

export type GradebookRowOut = {
  submission_id: string;
  user_id: string;
  handle: string;
  name: string;
  grade: number | null;
  submitted_at: string;
  auto: GradeCheckOut | null;
};

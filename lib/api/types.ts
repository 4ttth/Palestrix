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

export type AssignmentOut = {
  id: string;
  course_id: string;
  title: string;
  kind: "file" | "quiz" | "lab" | "writeup";
  due_at: string | null;
  lab_template_id: string | null;
  storage_key: string | null;
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
};

// -- labs and instances ---------------------------------------------------------

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

// -- community -------------------------------------------------------------------

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
};

export type ProviderOut = {
  name: string;
  kinds: string[];
  instances_active: number;
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

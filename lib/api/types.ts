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
  instances_active: number;
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

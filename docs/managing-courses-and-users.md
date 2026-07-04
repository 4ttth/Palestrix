# Managing Courses, Modules, and Users

The how-to companion to [rbac-matrix.md](rbac-matrix.md): that document says
*who may* do what; this one says *how* the everyday operations are actually
performed — creating a class, publishing course content, getting students
into a class, and managing accounts and roles. Each flow lists the UI path
(when one exists) and the raw `/api/v1` calls, which also work for scripted
onboarding.

Vocabulary, because the words overlap:

- A **course** (a "class" in school terms) is the container a teacher owns:
  code, title, section, roster, assignments. Model: `Course`.
- **Course content** — what a teacher publishes into a course — is an
  **assignment** (`file`, `quiz`, `lab`, `writeup`) and, for live labs, a
  **lab template** (the environment students launch).
- The **academy** (`/academy`) is the separate curriculum roadmap: `Path`
  rows containing `Module` rows that pay Palestras on completion. These are
  platform curriculum, **not teacher-authored** — see the limitations
  section at the end.

All examples use a session token from password login; passkey sessions and
API keys with the covering scope work identically.

```bash
TOKEN=$(curl -s http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"delacruz@example.edu","password":"palestrix-dev-only!"}' \
  | jq -r .access_token)
AUTH="Authorization: Bearer $TOKEN"
```

Seed accounts for every role are in `backend/palestrix/seed.py`
(`sir.delacruz` teacher, `admin.ops` admin, `root` superadmin, three
students; shared dev password `palestrix-dev-only!`).

## Creating a class (course)

**Who:** teachers and superadmins (`courses:write`). Plain admins are
deliberately denied — the matrix separates infrastructure power from
course power. A course is owned by whoever created it (`teacher_id`), and
every ownership check (assignments, grading, rosters, Canvas linking)
follows that column.

**UI:** sign in as a teacher → **Courses** (`/courses`). A teacher with no
courses yet sees the *Create your first course* card: fill **Code**
(`CS 3712`), **Title**, optional **Section**, press **Create course**.

> Known gap: the create form only renders in the empty state. A teacher
> who already owns a course must use the API to create the next one until
> the form is surfaced permanently.

**API:**

```bash
curl -s http://localhost:8000/api/v1/courses -H "$AUTH" \
  -H 'Content-Type: application/json' \
  -d '{"code":"CS 3712","title":"Defensive Operations 201","section":"BSCS 3A"}'
```

`tenant_id` may be included in the body to pin the course to a tenant;
otherwise it is null. There is currently no way to create a course *on
behalf of* a teacher — a superadmin-created course is owned by the
superadmin account, so the intended teacher should create it from their
own session.

## Publishing modules (course content)

**Who:** the owning teacher, or a superadmin (`courses:write` +
ownership).

**UI:** `/courses` → select the course → the **publishing panel** on the
right (`components/course/upload-panel.tsx`). It has two modes:

- **Basic** — a file handout. Creates an assignment
  (`kind: "file"`) and attaches the uploaded file to object storage.
- **Advanced** — a live environment. Publishes a **lab template** and, when
  a course is selected, files a matching `kind: "lab"` assignment so the
  roster sees it. Fields:
  - **Slug** `name:version` (e.g. `log-triage:1.4`), unique per platform.
  - **Kind** `container` (upload a Dockerfile/compose archive) or `vm`
    (name an admin-built Proxmox template). Plugin providers can register
    further kinds.
  - **Access mode** `gui` / `no-gui`, and **TTL** default/max (15–480 min).

**API equivalents:**

```bash
# Basic: assignment + attachment
AID=$(curl -s http://localhost:8000/api/v1/courses/$COURSE/assignments \
  -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"title":"Reading auth logs","kind":"file"}' | jq -r .id)
curl -s http://localhost:8000/api/v1/courses/$COURSE/assignments/$AID/attachment \
  -H "$AUTH" -F file=@handout.pdf

# Advanced: live environment, then the lab assignment pointing at it
TID=$(curl -s http://localhost:8000/api/v1/labs/templates -H "$AUTH" \
  -F slug=log-triage:1.5 -F 'title=Log Triage Under Fire' \
  -F kind=container -F access_mode=no-gui \
  -F ttl_minutes_default=90 -F ttl_minutes_max=240 \
  -F cpu=2 -F ram_gb=2 -F archive=@bundle.tar.gz | jq -r .id)
curl -s http://localhost:8000/api/v1/courses/$COURSE/assignments \
  -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"title\":\"Log triage lab\",\"kind\":\"lab\",\"lab_template_id\":\"$TID\"}"
```

`quiz` and `writeup` assignment kinds are accepted by the API but have no
upload-panel mode yet. `cpu`/`ram_gb` on the template are what tenant
quota enforcement charges at launch (Phase 7), so declare them honestly.

## Getting students into a class

Three paths exist today, none of them a button in the teacher's UI:

1. **Student self-enrollment (API):** the student calls
   `POST /api/v1/courses/{course_id}/enroll` with their own session
   (capability `courses:enroll`, student-only). Idempotence is enforced
   with a 409 on re-enrollment.
2. **Canvas roster sync (recommended for LMS classes):** link the course
   in the Canvas panel (`/courses` → course → **Canvas LMS**), then
   **Sync roster** — NRPS pre-provisions mapped students and enrolls them;
   it also un-enrolls only students it mapped itself
   ([integrations-canvas-lms.md](integrations-canvas-lms.md)).
3. **Scripted onboarding:** an API key with `courses:write` +
   student-session enroll calls, for bulk setups without an LMS.

> Known gap: there is no teacher/admin "add student to my course"
> endpoint, and no student-facing course browser to discover and join a
> class. The `/courses` empty-state copy ("Your teacher enrolls you")
> describes the intended flow, not the implemented one. Until then, use
> Canvas sync or the self-enroll API.

## Managing users (admin / superadmin)

**Account creation** is self-service: `/register` (or
`POST /api/v1/auth/register`) always creates a **student** with no tenant.
There is no admin create-user endpoint; elevation is a second, explicit
step by an admin. Identities arriving through Canvas LTI map by
`sub` + issuer and are pre-provisioned only by roster sync — never by a
bare launch.

**These operations are API-only today** — the admin console
(`/admin/infrastructure`) covers nodes, instances, ISOs, and tenants, but
has no Users tab yet.

List everyone (`users:manage` — admin or superadmin):

```bash
curl -s http://localhost:8000/api/v1/users -H "$AUTH"
```

Change a role:

```bash
curl -s -X PATCH http://localhost:8000/api/v1/users/$USER_ID/role \
  -H "$AUTH" -H 'Content-Type: application/json' -d '{"role":"teacher"}'
```

The boundary, enforced in `api/users.py`:

| Actor          | student ↔ teacher | grant/revoke admin, superadmin |
| -------------- | ----------------- | ------------------------------ |
| **admin**      | Y                 | 403 — in either direction      |
| **superadmin** | Y                 | Y                              |

"Either direction" means an admin can neither promote anyone *to*
admin/superadmin nor touch a user who already *holds* one of those roles.

Assign a user to a tenant (the quota/VLAN domain used at instance launch;
`infra:manage`):

```bash
curl -s -X POST \
  http://localhost:8000/api/v1/admin/tenants/hau-bscs-3a/assign/rafalmz \
  -H "$AUTH"
```

Machine principals follow the same ceiling: an API key or OAuth client can
never hold a scope its creating account's role does not cover
(`allowed_scopes_for_role`), so a teacher's key cannot manage users no
matter what scopes are requested.

## Current limitations (honest list)

- **Academy paths/modules are seed-only.** No API or UI creates `Path` /
  `Module` rows; teachers author course content, not academy curriculum.
  Authoring endpoints are future work.
- **Course create form only appears when the teacher has zero courses.**
- **No enrollment UI**: no teacher add-student action and no student
  course browser; Canvas sync or the self-enroll API are the working paths.
- **No admin user CRUD beyond roles**: no create, deactivate, delete, or
  password-reset endpoint, and no Users surface in the admin console.
- **No create-course-on-behalf-of**: course ownership is always the
  creating principal.

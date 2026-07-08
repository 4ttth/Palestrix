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

**UI:** sign in as a teacher → **Courses** (`/courses`). The *New course*
card is always present: fill **Code** (`CS 3712`), **Title**, optional
**Section**, press **Create course**.

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

1. **Teacher roster panel (UI):** `/courses` → select the course → the
   **Roster** panel lists everyone enrolled; type a student's handle and
   press **Enroll**, or remove one with the × on their row. The endpoints
   behind it (`courses:write`, ownership-checked):

   ```bash
   curl -s http://localhost:8000/api/v1/courses/$COURSE/roster -H "$AUTH"
   curl -s http://localhost:8000/api/v1/courses/$COURSE/enrollments \
     -H "$AUTH" -H 'Content-Type: application/json' -d '{"handle":"rafalmz"}'
   curl -s -X DELETE \
     http://localhost:8000/api/v1/courses/$COURSE/enrollments/$USER_ID -H "$AUTH"
   ```

   Only accounts with the `student` role can be enrolled (422 otherwise).
2. **Student self-enrollment (API):** the student calls
   `POST /api/v1/courses/{course_id}/enroll` with their own session
   (capability `courses:enroll`, student-only). Idempotence is enforced
   with a 409 on re-enrollment.
3. **Canvas roster sync (recommended for LMS classes):** link the course
   in the Canvas panel (`/courses` → course → **Canvas LMS**), then
   **Sync roster** — NRPS pre-provisions mapped students and enrolls them;
   it also un-enrolls only students it mapped itself
   ([integrations-canvas-lms.md](integrations-canvas-lms.md)).
4. **Scripted onboarding:** an API key with `courses:write` +
   student-session enroll calls, for bulk setups without an LMS.

## Managing users (admin / superadmin)

**UI: the Users console** (`/admin/users`, sidebar → Admin → Users;
capability `users:manage`). It carries the full flow: create an account
with any permitted role and an optional tenant, filter/search all
accounts, change a role from the inline dropdown, and assign or clear a
user's tenant. Role changes apply on the user's next request — session
principals resolve role and tenant from the database, not from JWT claims.

**Self-registration** at `/register` (or `POST /api/v1/auth/register`)
always creates a **student**. Its tenant follows the auto-tenancy rule:
`PALESTRIX_DEFAULT_TENANT_ID` if it names an active tenant, else the sole
active tenant when exactly one exists, else unassigned. Identities
arriving through Canvas LTI map by `sub` + issuer and are pre-provisioned
only by roster sync — never by a bare launch.

The same operations over the API — list everyone (`users:manage`):

```bash
curl -s http://localhost:8000/api/v1/users -H "$AUTH"
```

Create an account (role rules below apply):

```bash
curl -s http://localhost:8000/api/v1/users -H "$AUTH" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Teodoro Dela Cruz","handle":"sir.delacruz",
       "email":"delacruz@example.edu","password":"a-long-password-123",
       "role":"teacher","tenant_id":"hau-bscs-3a"}'
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

Assign a user to a tenant (the quota/VLAN domain used at instance launch).
Two equivalent endpoints — by tenant + handle (`infra:manage`) or by user
id (`users:manage`, `null` clears the assignment):

```bash
curl -s -X POST \
  http://localhost:8000/api/v1/admin/tenants/hau-bscs-3a/assign/rafalmz \
  -H "$AUTH"
curl -s -X PATCH http://localhost:8000/api/v1/users/$USER_ID/tenant \
  -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"tenant_id":"hau-bscs-3a"}'
```

Machine principals follow the same ceiling: an API key or OAuth client can
never hold a scope its creating account's role does not cover
(`allowed_scopes_for_role`), so a teacher's key cannot manage users no
matter what scopes are requested.

## Self-service account settings

Every signed-in user has **Settings** (`/settings`): display name
(`PATCH /api/v1/auth/me`), password rotation (`POST /api/v1/auth/password`,
current password required), passkey enrollment/removal, and personal API
keys. Handle, email, role, and tenant are staff-managed in the users
console by design.

## Current limitations (honest list)

- **Academy paths/modules are seed-only.** No API or UI creates `Path` /
  `Module` rows; teachers author course content, not academy curriculum.
  Authoring endpoints are future work.
- **No student course browser**: students cannot discover and join a class
  themselves in the UI; the teacher roster panel, Canvas sync, or the
  self-enroll API are the working paths.
- **No deactivate/delete or admin password reset**: an account can be
  created and re-roled from the console, but not disabled; password resets
  are self-service only.
- **No create-course-on-behalf-of**: course ownership is always the
  creating principal.

# Public API

Every core function of PalestrIX is exposed as a versioned REST API under
`/api/v1`. The frontend consumes the same contract as plugins and external
tools: there are no private endpoints for the UI. FastAPI auto-generates the
OpenAPI spec at `/api/v1/openapi.json` (Swagger UI at `/api/v1/docs`).

## Authentication

| Client type | Mechanism |
|---|---|
| Browser session | Cookie session established by passkey (WebAuthn) or password login |
| Server-to-server / plugins | API key (`X-Api-Key`) with scopes |
| External platforms | OAuth2 client-credentials, token with scopes |

Scopes mirror the RBAC matrix (rbac-matrix.md), for example:
`instances:launch`, `instances:read`, `courses:write`, `flags:submit`,
`ledger:read`, `webhooks:manage`. A key or token can never exceed the role of
the account that issued it.

## Resource groups

```
/api/v1/auth          register, login, WebAuthn ceremonies, sessions
/api/v1/users         profiles, roles (admin), handles
/api/v1/courses       courses, enrollment, assignments, submissions, grades
/api/v1/academy       paths, modules, completion, certification state
/api/v1/labs          lab templates (teacher publishing, incl. archives)
/api/v1/grading       automated-checking rubrics (schemes, weights, win files)
/api/v1/instances     ephemeral instances: launch, state, extend, destroy, grade
/api/v1/gamification  Palestras ledger, balances, streaks, leaderboards
/api/v1/community     writeups, comments, votes, community score
/api/v1/compete       events, challenges, flag submission, first blood
/api/v1/sandbox       sample submission, reports, events
/api/v1/admin         tenants, quotas, nodes, ISO library, reaper controls
/api/v1/plugins       registry, enablement, plugin config (superadmin)
/api/v1/webhooks      subscription management
/api/v1/integrations  external-platform links (LTI launch/JWKS, roster sync,
                      grade passback queue)
```

## Display enrichment (Phase 5)

The live UI renders API responses directly, so several response models carry
caller-scoped or denormalized fields the server fills in — additive only,
never a breaking change:

```
ModuleOut.completed            true when the caller completed the module
ChallengeOut.solved            true when the caller solved the challenge
ChallengeOut.first_blood_at    timestamp behind the first-blood feed
WriteupOut.author_handle       author display handle
WriteupOut.comments            comment count
CourseOut.students             enrollment count
CourseOut.assignments          assignment count
AssignmentOut.submissions      submission count (and .graded)
InstanceOut.kind / access_mode / template_slug / template_title /
            owner_handle      registry rows render without follow-up requests
TenantOut.instances_active / cpu_active / ram_active_gb
                              live usage against all three tenant quotas
```

Two admin read endpoints (both `infra:manage`) complete the infrastructure
console:

```
GET /api/v1/admin/isos        objects in the isos bucket (key, size, mtime)
GET /api/v1/admin/providers   active instance providers, their kinds, and
                              how many live instances each carries
```

## Tenant lifecycle (Phase 7)

Tenants are the isolation unit (ephemeral-lifecycle.md §Multitenancy
invariants). Creating one materializes it through the active cloud layer
(`backend/palestrix/tenancy/`): the local backend allocates the VLAN tag and
tenant CIDR in the registry; the OpenNebula and CloudStack adapters
additionally create the group/VDC/network or domain/account/network and push
the quotas. All endpoints require `infra:manage`.

```
POST   /api/v1/admin/tenants             create + materialize. Body: id (slug),
                                         name, instance_quota, cpu_cap,
                                         ram_cap_gb, network_cidr (blank: a /24
                                         is carved from the pool; given: pinned)
GET    /api/v1/admin/tenants             all tenants (archived included — history
                                         references them) with live usage
PATCH  /api/v1/admin/tenants/{id}        edit name/quotas; pushed through the
                                         cloud layer. VLAN and CIDR are fixed at
                                         creation and cannot be patched
DELETE /api/v1/admin/tenants/{id}        archive, not delete: refused with 409
                                         while the tenant holds active instances;
                                         afterwards its members cannot launch and
                                         its VLAN/CIDR stay reserved forever
POST   /api/v1/admin/tenants/{id}/assign/{handle}   move a user into the tenant
GET    /api/v1/admin/cloud               the active cloud layer (local |
                                         opennebula | cloudstack) and tenant counts
```

`POST /api/v1/admin/isos` stores the ISO in object storage and — while the
Proxmox adapter owns the "vm" kind — forwards it to the Proxmox ISO storage
(`PALESTRIX_PROXMOX_ISO_STORAGE`), returning
`{ "stored": "isos/kali.iso", "forwarded_to": "local:iso/kali.iso" }`; a
forwarding failure keeps the object-storage copy and reports `forward_error`
instead of failing the upload.

## Gamification surface

The gamification service (Phase 3) owns the Palestras ledger and is the only
component that mints or burns currency; every earn/spend elsewhere posts to it
with a reason code, and every non-zero entry fires `palestras.changed`.

```
GET /api/v1/gamification/balance      current spendable balance
GET /api/v1/gamification/ledger       own append-only ledger (newest first)
GET /api/v1/gamification/summary      profile card: balance, lifetime earned,
                                      spent, streak, community score, first
                                      bloods, global rank
GET /api/v1/gamification/streak       current/longest streak, last active day
GET /api/v1/gamification/leaderboard?board=palestras|community
                                      global, student-only ranking (staff have
                                      no earn path and never appear)
```

Balance rules (student-only earning, per-source daily caps, solve-count-scaled
flag awards, the first-blood bonus, weekly streak checkpoints, and
recency-decayed community score) are documented in rbac-matrix.md.

## Worked example: the instance lifecycle over HTTP

```http
POST /api/v1/instances
{ "template_id": "log-triage:1.4", "ttl_minutes": 90 }
-> 201 { "id": "lab-3427", "state": "requested", ... }
-> 409 { "error": "quota_exceeded", "quota": "cpu",
         "limit": 3, "used": 2, "requested": 2 }
   (quota names whichever of instances | cpu | ram blocked, checked in that
    order; used/requested are in that quota's unit — count, vCPU, or GB.
    Templates declare their spec at publish time: cpu, ram_gb)

GET  /api/v1/instances/lab-3427
-> { "state": "running", "access": { "mode": "no-gui",
     "host": "10.24.7.31", "port": 2211, "proto": "ssh" },
     "expires_at": "2026-07-02T10:44:22+08:00" }

GET  /api/v1/instances/lab-3427/logs/stream        (Server-Sent Events)
data: {"t":"09:14:03","level":"info","msg":"docker: pulling ..."}

POST /api/v1/instances/lab-3427/extend
{ "minutes": 30 }
-> 200 { "expires_at": "...", "palestras_spent": 150 }

DELETE /api/v1/instances/lab-3427
-> 202 { "state": "stopped" }   (destroy follows asynchronously)
```

## Sandbox surface (Phase 6)

The malware sandbox is a self-contained module (docs/sandbox-security.md).
Submissions detonate behind a detonator abstraction — the demo detonator in
dev, an isolated-host coordinator in a deployment — and the same HTTP contract
holds either way.

```
GET  /api/v1/sandbox/status              is the module enabled, and is a live
                                         detonation host wired or the demo
                                         detonator answering?
POST /api/v1/sandbox/samples             multipart upload; returns a report in
                                         `queued` (or already `completed` on the
                                         inline queue). Cap: 100 MB.
                                         Capability: sandbox:submit
GET  /api/v1/sandbox/reports             own reports, plus reports a teammate
                                         shared into your tenant. ?all_reports=
                                         true is admin-only (sandbox:read-all)
GET  /api/v1/sandbox/reports/{id}        verdict, threat score, family, static
                                         pre-check, IOCs, MITRE ids, summary
GET  /api/v1/sandbox/reports/{id}/events full behavior timeline (process, file,
                                         network, memory, static, system)
GET  /api/v1/sandbox/reports/{id}/events/stream    the same rows over SSE while
                                         the run detonates; closes with a
                                         `state` event (same reader as the
                                         instance log stream)
POST /api/v1/sandbox/reports/{id}/share  open/close the report to your tenant
                                         (submitter only)
GET  /api/v1/sandbox/reports/{id}/artifacts        archived report/capture/
                                         dropped-file list
GET  /api/v1/sandbox/reports/{id}/artifacts/download?key=
                                         export one artifact; admin-only
                                         (sandbox:export). Raw samples are never
                                         served; artifacts are sealed at rest
```

A report is private to its submitter until shared with the tenant; `verdict`
is one of `unknown|clean|suspicious|malicious`; `state` moves
`queued -> static -> detonating -> completed` (or `failed`). Completion fires
`sandbox.report.ready` on the event bus (below). When the module is disabled
the whole surface answers `501`.

## Integrations surface (Phase 8)

External platforms plug in behind the `ExternalPlatform` contract
(docs/integrations-canvas-lms.md); Canvas LMS is the reference adapter. Two
trust models share the `/integrations` prefix:

```
GET  /api/v1/integrations/platforms       active platforms (id, name, issuer,
                                          features). Requires a session —
                                          nothing else on this surface does

GET  /canvas/jwks                        the tool's public keyset Canvas pins
GET/POST /canvas/login                   OIDC third-party initiation -> 302 to
                                          Canvas with a signed state + nonce
POST /canvas/launch                      validates the id_token; a resource
                                          launch hands the browser a session,
                                          a deep-linking launch renders the
                                          lab picker. 401 on a bad signature,
                                          unknown nonce, or a replayed one
POST /canvas/deep-link                   picker submission -> signed
                                          LtiDeepLinkingResponse auto-posted
                                          back to Canvas
```

The four `canvas/*` routes are public by protocol — the browser arrives
carrying platform- or PalestrIX-signed tokens, and those signatures are the
authentication, not a session. Everything below is ordinary authenticated
API, teacher-owned like `/courses` (`courses:write` + course ownership):

```
POST   /api/v1/integrations/links               link a course to a platform
GET    /api/v1/integrations/links?course_id=     list links (own courses,
                                                 all for admin/superadmin),
                                                 each with pending/delivered/
                                                 failed grade counts
DELETE /api/v1/integrations/links/{id}           unlink. Mapped identities and
                                                 delivered receipts stay
POST   /api/v1/integrations/links/{id}/sync      pull the roster now; returns
                                                 {roster, added, provisioned,
                                                 removed, skipped}. Fires
                                                 roster.synced
GET    /api/v1/integrations/links/{id}/grades    the link's grade-passback
                                                 queue, newest first
POST   /api/v1/integrations/grades/{id}/retry    requeue a failed row and
                                                 attempt delivery immediately;
                                                 409 if already delivered
```

Grade passback is queued right after a teacher grades a submission (one row
per linked platform the student is mapped on and whose assignment has a
bound AGS line item), then delivered asynchronously — immediately as a
background task and again on every reaper heartbeat — with exponential
backoff (`2^attempts` minutes) up to `PALESTRIX_GRADE_PASSBACK_MAX_ATTEMPTS`,
after which the row parks as `failed` for a manual retry. Delivery fires
`grade.delivered`.

## Webhooks

Subscriptions are per-account, scoped, and signed (HMAC-SHA256 over the body
with a per-subscription secret, `X-Palestrix-Signature` header). Deliveries
retry with exponential backoff for 24 hours.

| Event | Fires when |
|---|---|
| `instance.provisioned` | An instance reaches `running` |
| `instance.expired` | The reaper destroys an instance |
| `flag.captured` | A correct flag is accepted (includes first-blood flag) |
| `palestras.changed` | Any ledger entry posts |
| `grade.posted` | A teacher grades a submission |
| `writeup.published` | A community writeup goes live |
| `sandbox.report.ready` | A detonation report is complete |
| `roster.synced` | A linked course's roster sync completes |
| `grade.delivered` | A queued grade passback is delivered to the platform |

The same events flow on an internal bus consumed by UI live updates and by
plugins (`on_event`, see plugin-development.md); webhooks are the external
mirror of that bus.

### Where a webhook may point

A subscription is a URL the platform fetches on the subscriber's behalf, and
any student may create one — so an unrestricted one is a server-side request
forgery primitive against the lab networks and the cloud metadata service.
Destinations are therefore restricted to routable internet addresses:

- `http`/`https` only, on port 80, 443, 8080, or 8443.
- The host is resolved and every address it returns is checked. Loopback,
  RFC1918, CGNAT, link-local (`169.254.169.254` and its IPv6 twin),
  multicast, and reserved ranges are refused, as is a host that resolves to
  a mix of public and private addresses.
- The check runs again immediately before **every** delivery attempt, not
  only at subscribe time, so a name cannot be re-pointed inward after the
  fact (DNS rebinding). Redirects are never followed.

A refused URL fails `POST /webhooks` with `422` and the reason.
`PALESTRIX_ALLOW_PRIVATE_WEBHOOKS=1` lifts the address rule for a site whose
collector genuinely is internal; the port rule still applies, and the
production boot guard reports the setting.

## Versioning and stability

- Breaking changes require `/api/v2`; `/api/v1` then enters a 12-month
  deprecation window with `Deprecation` headers.
- Additive changes (new fields, new endpoints, new event types) are allowed
  within v1; clients must ignore unknown fields.
- The OpenAPI spec is committed to the repo per release and diffed in CI so
  accidental breaking changes fail the build.

## Rate limits

Enforced by the API itself (`palestrix/ratelimit.py`), per caller per
minute. A caller is the API key, else the bearer token, else the peer
address — so a shared campus NAT does not put a whole class in one bucket
once they have signed in.

| Bucket | Default | Covers |
| --- | --- | --- |
| `auth` | 20/min | `/auth/login`, `/register`, `/token`, `/password`, the passkey login ceremony |
| `launch` | 60/min | `POST /instances`, `POST /instances/{id}/extend` |
| `flag` | 10/min | `POST /compete/challenges/{id}/submit` |
| `general` | 600/min | everything else |

Each is `PALESTRIX_RATE_LIMIT_<BUCKET>_PER_MINUTE`; `0` disables one, and
`PALESTRIX_RATE_LIMIT_ENABLED=0` disables all of them (the production boot
guard reports that). A `429` carries `Retry-After` and a structured body:

```json
{"detail": {"error": "rate_limited", "bucket": "auth", "limit": 20,
            "window_seconds": 60, "retry_after": 37}}
```

The `flag` bucket sits on top of the per-challenge cooldown: the cooldown
paces guessing at one challenge, the bucket paces the account across all of
them.

The limiter counts **per process**, so a deployment running several uvicorn
workers allows roughly that many times each number. The edge proxy (Caddy or
Traefik, see the runbooks) remains the authoritative limiter for a site;
this is the floor that still holds when the API is reached directly.

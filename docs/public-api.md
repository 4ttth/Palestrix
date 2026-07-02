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
/api/v1/instances     ephemeral instances: launch, state, extend, destroy
/api/v1/gamification  Palestras ledger, balances, streaks, leaderboards
/api/v1/community     writeups, comments, votes, community score
/api/v1/compete       events, challenges, flag submission, first blood
/api/v1/sandbox       sample submission, reports, events
/api/v1/admin         tenants, quotas, nodes, ISO library, reaper controls
/api/v1/plugins       registry, enablement, plugin config (superadmin)
/api/v1/webhooks      subscription management
```

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
-> 409 { "error": "quota_exceeded", "quota": "instances", "limit": 3 }

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

The same events flow on an internal bus consumed by UI live updates and by
plugins (`on_event`, see plugin-development.md); webhooks are the external
mirror of that bus.

## Versioning and stability

- Breaking changes require `/api/v2`; `/api/v1` then enters a 12-month
  deprecation window with `Deprecation` headers.
- Additive changes (new fields, new endpoints, new event types) are allowed
  within v1; clients must ignore unknown fields.
- The OpenAPI spec is committed to the repo per release and diffed in CI so
  accidental breaking changes fail the build.

## Rate limits

Defaults, per key/session: 600 requests/minute general, 60/minute for
launch/extend, 10/minute for flag submission (plus the per-challenge
cooldown). `429` responses carry `Retry-After`.

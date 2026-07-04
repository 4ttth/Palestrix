# PalestrIX Architecture

PalestrIX is a gamified cybersecurity training platform in the spirit of
TryHackMe, HackTheBox, and the KYPO cyber range, assembled entirely from
open-source components. This document is the system-level map; the other
documents in this folder go deep on each subsystem.

## Design goals

1. **Real infrastructure for every exercise.** Students get actual VMs and
  containers, never simulations.
2. **Ephemeral by default.** Every instance carries a TTL and is destroyed by
  a reaper. Idle capacity is reclaimed automatically.
3. **Multitenant isolation.** A class section, an event, or a single student
  is a tenant with its own network, quotas, and naming.
4. **API-first.** Every function the UI performs exists as a versioned REST
  endpoint first (see public-api.md). Plugins and external tools consume the
   same contract.
5. **Deployable two ways.** On owned baremetal behind a public IP or domain
  (usecase-a-baremetal.md), or on cloud services with generic and AWS
   names side by side (usecase-b-cloud-aws.md).



## Component overview

```
                       +--------------------------+
                       |  Edge proxy (Traefik or  |
                       |  Caddy): TLS, routing    |
                       +------------+-------------+
                                    |
              +---------------------+---------------------+
              |                                           |
   +----------v-----------+                  +------------v-----------+
   |  Frontend (Next.js)  |                  |  Core API (FastAPI)    |
   |  landing, auth,      +----- REST ------>+  /api/v1, OpenAPI,     |
   |  product surfaces    |  SSE/WebSocket   |  webhooks, RBAC        |
   +----------------------+                  +-----+------+-----+-----+
                                                   |      |     |
                              +--------------------+      |     +--------------------+
                              |                           |                          |
                   +----------v---------+      +----------v----------+    +----------v---------+
                   |  PostgreSQL        |      |  Redis + workers    |    |  MinIO / S3        |
                   |  users, courses,   |      |  (Celery/RQ): jobs, |    |  ISOs, archives,   |
                   |  ledger, flags     |      |  TTL reaper, queues |    |  writeup assets    |
                   +--------------------+      +----------+----------+    +--------------------+
                                                          |
                                         +----------------+----------------+
                                         |                                 |
                              +----------v----------+          +-----------v-----------+
                              |  Proxmox VE adapter |          |  Docker adapter       |
                              |  (VMs, ISO attach,  |          |  (containers, builds, |
                              |  noVNC consoles)    |          |  compose stacks)      |
                              +----------+----------+          +-----------+-----------+
                                         |                                 |
                              +----------v---------------------------------v----------+
                              |  Multitenant cloud layer: OpenNebula OR CloudStack    |
                              |  (tenants, quotas, VDC/domain isolation)              |
                              +-------------------------------------------------------+

   Separate, network-isolated:  +---------------------------+
                                |  Malware sandbox module   |
                                |  (hardened Docker host)   |
                                +---------------------------+
```



## Services



### Frontend

Next.js (App Router, React Server Components) with Tailwind v4. Two visual
treatments on one locked theme:

- Landing and auth: marketing-grade composition, Motion for entrances, an
isolated Three.js hero leaf.
- Product surfaces (dashboard, academy, courses, labs, sandbox, community,
compete, admin): dense, customized shadcn-style components. Geist Mono
renders every technical value (IPs, ports, timers, scores, hashes).

Theme tokens live in `components/theme/tokens.css` and are the single source
of truth for both light and dark mode.

### Core API

Python / FastAPI. Serves `/api/v1` with an auto-generated OpenAPI spec.
Responsibilities: authentication (WebAuthn passkeys via py_webauthn, password
fallback, OIDC-ready), RBAC enforcement, courses and assignments, community
content, CTF events and flags, the gamification service, and the webhook/event
bus. Details in public-api.md and rbac-matrix.md.

### Gamification service

Owns the Palestras ledger (append-only, double-entry: every earn and spend is
a transaction with a reason code), streaks, and the community score. Balancing
rules and anti-abuse (rate caps per source, decay, duplicate-flag detection)
are part of this service so no other component mints currency.

### Orchestration service

Async workers (Celery or RQ on Redis) behind a provider interface:

```python
class InstanceProvider(Protocol):
    def provision(self, spec: InstanceSpec) -> InstanceRef: ...
    def expose(self, ref: InstanceRef) -> AccessInfo: ...      # noVNC or ip:port
    def stop(self, ref: InstanceRef) -> None: ...
    def destroy(self, ref: InstanceRef) -> None: ...
    def stream_logs(self, ref: InstanceRef) -> Iterator[LogLine]: ...
```

Adapters: Proxmox VE (VM clone from template, ISO attach, noVNC ticket) and
Docker (image build from teacher archives, compose stacks). The TTL reaper is
a scheduled worker that scans for expired instances, stops and destroys them,
and releases tenant quota. Full state machine in ephemeral-lifecycle.md.

### Multitenant cloud layer

Proxmox VE is the hypervisor base. For multitenancy (per-class isolation,
quotas, self-service within limits) the deployment fronts it with either
OpenNebula (VDCs and groups) or Apache CloudStack (domains and accounts).
Both are documented in usecase-a-baremetal.md; pick one per site.

Implemented in Phase 7 (`backend/palestrix/tenancy/`) behind a `TenantCloud`
contract that mirrors the Phase 4 provider and Phase 6 detonator registries:
`ensure_tenant` on create, `sync_quota` on quota edits, `retire_tenant` on
archive — all idempotent, all called only by the admin API. The built-in
`LocalCloud` does registry-side allocation (a VLAN tag from
`PALESTRIX_TENANT_VLAN_MIN..MAX`, a /24 carved from
`PALESTRIX_TENANT_CIDR_POOL`), which the Phase 4 adapters turn into real
isolation: Proxmox tags `net0` with the tenant VLAN on the trunk bridge,
Docker pins the tenant bridge to the tenant CIDR. Setting
`PALESTRIX_CLOUD_BACKEND=opennebula|cloudstack` swaps in an adapter that
additionally materializes each tenant in that manager — group + VDC +
VLAN-backed virtual network, or domain + account + isolated network — and
pushes quota edits through. The API enforces all three tenant quotas
(instances, vCPU, RAM) at launch either way; archived tenants keep their
row, VLAN, and CIDR forever (ephemeral-lifecycle.md §Multitenancy
invariants).

### Deployment hardening

`backend/palestrix/hardening.py` is the part of the runbooks the app
verifies itself. `production_readiness()` reports every configuration that
must not survive into production — the dev secret, SQLite, a plain-HTTP
origin, wildcard or plaintext CORS origins, TLS verification switched off
on any adapter, the inline queue, a disabled reaper, local-folder storage —
and `PALESTRIX_ENVIRONMENT=production` arms the boot guard: the API refuses
to start while any finding stands, so a misconfigured deployment dies
loudly at boot instead of serving traffic. Every response carries baseline
security headers (nosniff, frame-deny, no-referrer, a Permissions-Policy;
HSTS in production only) without relying on the edge proxy. Additive schema
upgrades for databases seeded by earlier phases run at startup in both the
API and the worker (`palestrix/migrations.py`); anything beyond ADD COLUMN
ships with real Alembic migrations when the need first arises.

### Malware sandbox module

A self-contained module on a dedicated, network-isolated Docker host.
Submissions detonate in instrumented containers; file-system and network
events stream back to the UI. It shares only the API contract with the rest
of the platform. Hardening spec in sandbox-security.md. Implemented in Phase 6
(`backend/palestrix/sandbox/`): a detonator abstraction with a built-in demo
detonator (real static pre-check, simulated dynamic trace) and a coordinator
adapter for the isolated host; verdict + MITRE mapping; an SSE behavior-event
stream; samples and reports sealed at rest. See sandbox-security.md
§Implementation status and public-api.md §Sandbox surface.

### External integrations

Implemented in Phase 8 (`backend/palestrix/integrations/`) behind an
`ExternalPlatform` contract that mirrors the Phase 4/6/7 registries: nothing
answers by default, and `activate_configured_platforms` (called from the API
lifespan and the worker) registers whichever adapters the environment
configures — Canvas LMS is the reference adapter, so the next platform
(Moodle, Google Classroom) follows the same path. Adapters are pure platform
clients; the API owns the registry rows, the same split as `TenantCloud`.
Three flows ride the contract: LTI 1.3 launch with identity mapping by
`sub`+issuer (an unmapped identity claims an account by asserted e-mail, or
lands on an "ask your teacher to sync" page — never silent creation), NRPS
roster sync that pre-provisions and un-enrolls only the students this
platform mapped, and an AGS grade-passback queue that delivers on the reaper
heartbeat with exponential backoff and parks exhausted rows as `failed` for
a manual retry in the teacher's course panel. Full contract in
integrations-canvas-lms.md and public-api.md §Integrations surface.

### Storage

PostgreSQL for relational data. MinIO (S3-compatible) for objects: admin
ISO uploads, teacher environment archives, writeup assets, sandbox reports.

### Extensibility

- Plugin framework with a versioned manifest, capability scopes, and
lifecycle hooks (plugin-development.md).
- Public API plus webhooks for external tools (public-api.md).
- An `ExternalPlatform` adapter layer for LMS integrations, Canvas first
(integrations-canvas-lms.md).



## Roles

Student, Teacher, Administrator, Superadministrator. Every screen and every
endpoint is role-gated; the full permission matrix is rbac-matrix.md.

## Build order


| Phase | Deliverable                                                                                                                                        |
| ----- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1     | Frontend templates, locked theme, this documentation set                                                                                           |
| 2     | Core API, Postgres schema, passkey auth, RBAC, object storage                                                                                      |
| 2b    | Plugin framework and reference plugins                                                                                                             |
| 3     | Gamification: ledger, streaks, ranking                                                                                                             |
| 4     | Orchestration abstraction, Proxmox and Docker adapters, TTL reaper                                                                                 |
| 5     | Feature surfaces wired to live data                                                                                                                |
| 6     | Malware sandbox module                                                                                                                             |
| 7     | Multitenant cloud layer, both deployment runbooks hardened                                                                                         |
| 8     | External integrations, Canvas LMS adapter, and a detailed (GitHub formatted) step-by-step installation and setup documentation for both use cases. |



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

### Malware sandbox module

A self-contained module on a dedicated, network-isolated Docker host.
Submissions detonate in instrumented containers; file-system and network
events stream back to the UI. It shares only the API contract with the rest
of the platform. Hardening spec in sandbox-security.md.

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



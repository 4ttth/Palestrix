# PalestrIX

A gamified cybersecurity training platform (TryHackMe + HackTheBox + KYPO
cyber range, for classrooms), built entirely from open-source components.
Students train on real ephemeral VMs and containers, earn and spend the
Palestras currency, and compete in a CTF arena; teachers publish labs
without touching infrastructure; admins run the range from one console.

**Status: Phase 8 complete.** The repository contains the full frontend on
a locked design theme (Phase 1), the implementation documentation for both
deployment use cases, the FastAPI core API (Phase 2): passkey auth, RBAC,
the versioned `/api/v1` surface, API-key + OAuth2 client-credentials auth,
the webhook/event bus, and object storage wiring — the plugin framework
(Phase 2b): server-plugin discovery, capability scoping, config encryption,
crash isolation, the UI slot system, and both reference plugins under
`plugins/` — the gamification service (Phase 3): the append-only Palestras
ledger as the single minter/burner, per-source daily caps,
solve-count-scaled flag awards, the first-blood bonus, writeup earning,
streaks with a weekly checkpoint, recency-decayed community score, and the
student-only leaderboards — orchestration (Phase 4): the provider
abstraction, Docker and Proxmox VE adapters, the SSE log stream, and the
TTL reaper — and the live feature surfaces (Phase 5): every product screen
wired to `/api/v1` through a typed client (`lib/api/`), real passkey
ceremonies, session-guarded routing, launch/stop/extend/destroy with
server-authoritative TTL countdowns, live flag submission, votes and
writeups, teacher publishing, and the admin console — and the malware
sandbox module (Phase 6): a self-contained detonation service behind a
detonator abstraction (`backend/palestrix/sandbox/`), real static
pre-analysis of every submission (magic-byte typing, Shannon entropy,
string/IOC extraction, EICAR detection), a verdict with a MITRE ATT&CK
mapping, a behavior-event timeline streamed over SSE, samples and reports
sealed at rest, and admin-gated artifact export — with the live `/sandbox`
surface wired to all of it — and the multitenant layer with hardened
deployments (Phase 7): the `TenantCloud` contract
(`backend/palestrix/tenancy/`) with the registry-only LocalCloud as the
default — the single Proxmox VE workstation path — plus optional OpenNebula
and CloudStack adapters for a hypervisor fleet, full tenant lifecycle from the
admin console (create materializes VLAN + CIDR, quota edits sync through,
archive requires an idle tenant), instances/vCPU/RAM quota enforcement at
launch with the blocking quota named, tenant VLAN tags on the Proxmox adapter
(isolated by the host's VLAN-aware bridge) and tenant subnets on the Docker
adapter, admin ISO forwarding to Proxmox ISO storage, additive startup
migrations, security headers on every response,
and a production boot guard that refuses to start misconfigured — and Canvas
LMS integration (Phase 8): an `ExternalPlatform` adapter layer
(`backend/palestrix/integrations/`) with Canvas as the reference adapter —
LTI 1.3 launch, NRPS roster sync, AGS grade passback with retry, and Deep
Linking 2.0 — wired to a live Canvas panel in the course manager, plus a
detailed, GitHub-formatted step-by-step install guide for both deployment
use cases. See [backend/README.md](backend/README.md) to run the API and
[docs/plugin-development.md](docs/plugin-development.md) to write a plugin.

## Run it

```bash
# Terminal 1: the core API (see backend/README.md for the venv setup)
cd backend
python -m palestrix.seed                        # demo tenant, users, event
uvicorn palestrix.main:app --reload --port 8000

# Terminal 2: the frontend
npm install
npm run dev        # http://localhost:3000
npm run build      # production build (all 14 routes compile)
```

Sign in with the development seed account `rafaela@example.edu` /
`palestrix-dev-only!` (see `backend/palestrix/seed.py` for the other
roles). The frontend reads `NEXT_PUBLIC_PALESTRIX_API` for the API origin,
defaulting to `http://localhost:8000`.

Screens:


| Route                   | Surface                                                    |
| ----------------------- | ---------------------------------------------------------- |
| `/`                     | Marketing landing (Three.js hero, taste-skill treatment)   |
| `/login`, `/register`   | Passkey-first auth gateway                                 |
| `/dashboard`            | Student dashboard: active instance, progress, leaderboard  |
| `/academy`              | Paths, module roadmap, certification state                 |
| `/courses`              | Teacher course manager + progressive-disclosure lab upload |
| `/labs/lab-3427`        | Active ephemeral lab: connection, TTL, real log stream     |
| `/sandbox`              | Malware sandbox: submission + behavior traces              |
| `/community`            | Writeups, profiles, community score                        |
| `/compete`              | CTF arena: board, flags, first blood, leaderboard          |
| `/admin/infrastructure` | Nodes, instance registry, ISO library, tenants             |


Every product surface renders live `/api/v1` responses (Phase 5): the wire
types live in [lib/api/types.ts](lib/api/types.ts), the client and session
layer in [lib/api/](lib/api/). `lib/mock.ts` retains only the marketing
page's demo log replay.

## Design system

One locked theme for every surface, defined in
`components/theme/tokens.css`: zinc-family neutrals in light and dark
(auto via `prefers-color-scheme`), one calm electric blue accent, amber
reserved for Palestras, pastel semantic pairs for the instance lifecycle
(provisioning / running / stopped / expired), Geist Sans + Geist Mono, and
a fixed radius scale (cards 12px, inputs 8px, CTAs pill). Marketing and
auth follow the design-taste skill; dense product surfaces use customized
shadcn-style primitives in `components/ui/`.

Key components:

- `components/three/HeroModel.tsx`: isolated, lazy-loaded 3D hero leaf.
- `components/lab/ProvisioningLog.tsx`: real provisioning log stream over
authenticated SSE (fetch-based; EventSource cannot carry the bearer
token). No fake bars.
- `components/lab/Countdown.tsx`: TTL countdown off the server's expiry
timestamp; re-syncs on extend.
- `components/course/upload-panel.tsx`: teacher basic/advanced publishing,
wired to assignments + `/labs/templates`.



## Documentation


| Document                                                           | Contents                                                                                           |
| ------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| [docs/architecture.md](docs/architecture.md)                       | System map, services, build order                                                                  |
| [docs/usecase-a-baremetal.md](docs/usecase-a-baremetal.md)         | Single Proxmox VE 9.1.1 workstation runbook: registry-driven tenancy, ZFS, MinIO, Caddy, public IP/domain |
| [docs/usecase-b-cloud-aws.md](docs/usecase-b-cloud-aws.md)         | Cloud runbook with generic and AWS names for every service                                         |
| [docs/ephemeral-lifecycle.md](docs/ephemeral-lifecycle.md)         | Instance state machine, TTL reaper, multitenancy invariants                                        |
| [docs/rbac-matrix.md](docs/rbac-matrix.md)                         | Full role/capability matrix + gamification rules                                                   |
| [docs/managing-courses-and-users.md](docs/managing-courses-and-users.md) | How-to: create classes, publish modules, enroll students, manage users/roles                 |
| [docs/automated-checking.md](docs/automated-checking.md)           | Rubric autograding: finished-vs-unfinished diff, win files, provider probes, gradebook             |
| [docs/sandbox-security.md](docs/sandbox-security.md)               | Malware sandbox isolation and hardening                                                            |
| [docs/public-api.md](docs/public-api.md)                           | `/api/v1` surface, auth, webhooks, versioning                                                      |
| [docs/plugin-development.md](docs/plugin-development.md)           | Plugin manifest, lifecycle hooks, UI slots, sandboxing                                             |
| [docs/integrations-canvas-lms.md](docs/integrations-canvas-lms.md) | `ExternalPlatform` adapter layer, Canvas LMS reference                                             |




## Plugins (Phase 2b)

Server plugins are Python packages on a versioned manifest with capability
scopes, encrypted config, and crash isolation
([backend/palestrix/plugins/](backend/palestrix/plugins/)). UI plugins
mount lazy, code-split widgets into declared slots through
`@palestrix/plugin-sdk` ([lib/plugins/](lib/plugins/),
[components/plugins/PluginSlot.tsx](components/plugins/PluginSlot.tsx)).
Two reference plugins live under [plugins/](plugins/) and double as
contract tests:

- `palestrix-provider-demo`: an instant echo instance provider; the
provider-authoring tutorial, exercised by the backend test suite.
- `palestrix-widget-firstblood`: a first-blood feed widget on the
`dashboard.widgets` slot; the UI-slot tutorial.



## Roadmap

Phase 3: gamification. **Done** — ledger, caps, streaks, community score, and
ranking in [backend/palestrix/gamification.py](backend/palestrix/gamification.py).

Phase 4: orchestration + TTL reaper. **Done** — 6 tests in test_orchestration.py:
SSE log stream replay, stop/destroy transitions, TTL reaper pass (quota
release), provision failure retry policy (up to 2 attempts), Docker adapter
(CLI-driven with recorded runner), and Proxmox VE adapter (httpx MockTransport).

Phase 5: live feature surfaces. **Done** — typed API client + session layer
(`lib/api/`), passkey login/enrollment via SimpleWebAuthn, and every surface
live: dashboard (launch panel, ledger, leaderboard), academy (per-caller
module completion), courses (role-aware, live counts, wired publishing),
labs (SSE log stream, TTL, stop/extend/destroy), compete (solved state,
cooldown handling, first-blood feed), community (votes, composer),
admin (providers, registry, ISO library, tenants, reaper trigger), and an
honest 501 state for the sandbox. The plugin `ScopedApi` now fetches the
real API on the same signature. Backend: display-enrichment fields +
`GET /admin/isos` + `GET /admin/providers` (docs/public-api.md §Display
enrichment). Full test suite: 42 tests pass.

Phase 6: sandbox module. **Done** — 11 tests in test_sandbox.py. The
detonator abstraction (`backend/palestrix/sandbox/`) mirrors the Phase 4
provider registry: the built-in demo detonator runs real static analysis
and a clearly-labelled synthetic dynamic trace, and setting
`PALESTRIX_SANDBOX_COORDINATOR_URL` swaps in the coordinator adapter that
drives an isolated detonation host over its single permitted port. Static
pre-check (magic bytes, entropy, strings, IOC extraction, EICAR) is real
and never executes the sample; the verdict carries a threat score, family,
MITRE ATT&CK ids, and an SOC-handoff summary. The behavior timeline streams
over SSE on the same reader as the provisioning log; samples and report
artifacts are sealed at rest so a host AV cannot quarantine them; reports
are private to the submitter until shared with their tenant; raw samples are
never served and artifact export is admin-only. The `/sandbox` surface is
live end to end, and `sandbox.report.ready` fires on the webhook/event bus.
Full test suite: 53 tests pass.

Phase 7: multitenant layer + hardened deployments. **Done** — 8 tests in
test_tenancy.py. The `TenantCloud` contract (`backend/palestrix/tenancy/`)
mirrors the Phase 4/6 registries: LocalCloud (the default) allocates the
tenant VLAN tag and a /24 from the configured pools in the registry, and
`PALESTRIX_CLOUD_BACKEND` swaps in the OpenNebula adapter (group + VDC +
VLAN-backed network over XML-RPC) or the CloudStack adapter (domain +
account + isolated network over signed REST). Tenant lifecycle is fully
API-driven: create materializes, PATCH syncs quotas through, DELETE archives
(refused while instances are active; the VLAN/CIDR stay reserved forever).
Launch enforces all three tenant quotas — instances, vCPU, RAM against each
template's declared `cpu`/`ram_gb` — and the 409 names the blocking quota;
the Proxmox adapter tags `net0` with the tenant VLAN (isolated by the host's
VLAN-aware bridge, no external switch on a single box), the Docker adapter
pins the tenant bridge subnet, and admin ISO uploads forward to Proxmox ISO
storage. Hardened deployments: additive startup migrations
(`migrations.py`), security headers on every response, and the
`PALESTRIX_ENVIRONMENT=production` boot guard (`hardening.py`) that refuses
to start on any readiness finding. Both runbooks updated with the tenancy
wiring and hardening steps; the admin console gained the full tenants
surface (create, quota edits, archive, live usage, active cloud layer).
Full test suite: 63 tests pass.

Phase 8: Canvas LMS integration and step-by-step install documentation.
**Done** — 8 tests in test_integrations.py, full suite 71 green. The
`ExternalPlatform` contract (`backend/palestrix/integrations/`) mirrors the
Phase 4/6/7 registries: nothing answers until `PALESTRIX_CANVAS_ISSUER` +
`_CLIENT_ID` activate the Canvas adapter, so the next platform (Moodle,
Google Classroom) follows the same path. Canvas covers all four LTI
protocols — 1.3 launch (OIDC initiation, RS256 id_token validation, single-use
nonces), NRPS roster sync, AGS grade passback, and Deep Linking 2.0 for the
teacher's lab picker. Identity maps by `sub`+issuer with no silent account
creation; roster sync pre-provisions and un-enrolls only the students it
mapped itself; the grade-passback queue retries on the reaper heartbeat with
exponential backoff and parks exhausted rows as `failed` for a one-click
retry in the course panel. The frontend gained a live Canvas panel
(link/sync/grade-queue) in the course manager and the LTI login handoff;
`lib/api/types.ts` carries the wire types. Both runbooks
([docs/install-usecase-a-baremetal.md](docs/install-usecase-a-baremetal.md),
[docs/install-usecase-b-cloud-aws.md](docs/install-usecase-b-cloud-aws.md))
now walk every step from bare OS to a running platform, GitHub-formatted.
Full test suite: 71 tests pass; production build: all 14 routes compile.

Details in [docs/architecture.md](docs/architecture.md).
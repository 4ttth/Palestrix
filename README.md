# PalestrIX

A gamified cybersecurity training platform (TryHackMe + HackTheBox + KYPO
cyber range, for classrooms), built entirely from open-source components.
Students train on real ephemeral VMs and containers, earn and spend the
Palestras currency, and compete in a CTF arena; teachers publish labs
without touching infrastructure; admins run the range from one console.

**Status: Phase 6 complete.** The repository contains the full frontend on
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
surface wired to all of it. See [backend/README.md](backend/README.md) to
run the API and [docs/plugin-development.md](docs/plugin-development.md) to
write a plugin. Next: Phase 7 (multitenant layer + hardened deployments).

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
| [docs/usecase-a-baremetal.md](docs/usecase-a-baremetal.md)         | Baremetal runbook: Proxmox VE + OpenNebula/CloudStack, ZFS, MinIO, Traefik/Caddy, public IP/domain |
| [docs/usecase-b-cloud-aws.md](docs/usecase-b-cloud-aws.md)         | Cloud runbook with generic and AWS names for every service                                         |
| [docs/ephemeral-lifecycle.md](docs/ephemeral-lifecycle.md)         | Instance state machine, TTL reaper, multitenancy invariants                                        |
| [docs/rbac-matrix.md](docs/rbac-matrix.md)                         | Full role/capability matrix + gamification rules                                                   |
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

Phase 7: multitenant layer + hardened deployments. 

Phase 8: Canvas LMS integration and a detailed (GitHub formatted) step-by-step installation and setup documentation for both use cases.

Details in [docs/architecture.md](docs/architecture.md).
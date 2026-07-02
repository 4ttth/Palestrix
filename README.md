# PalestrIX

A gamified cybersecurity training platform (TryHackMe + HackTheBox + KYPO
cyber range, for classrooms), built entirely from open-source components.
Students train on real ephemeral VMs and containers, earn and spend the
Palestras currency, and compete in a CTF arena; teachers publish labs
without touching infrastructure; admins run the range from one console.

**Status: Phase 2 complete.** The repository contains the full frontend
template set on a locked design theme (Phase 1), the implementation
documentation for both deployment use cases, and the FastAPI core API
(Phase 2): passkey auth, RBAC, the versioned `/api/v1` surface, API-key +
OAuth2 client-credentials auth, the webhook/event bus, and object storage
wiring. See [backend/README.md](backend/README.md) to run it. Next:
Phase 2b (plugin framework) and Phase 3 (gamification rules).

## Run the templates

```bash
npm install
npm run dev        # http://localhost:3000
npm run build      # production build (all 13 routes compile statically)
```

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


All product data is sample data from `lib/mock.ts`, replaced by live API
responses from Phase 2 onward.

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
- `components/lab/ProvisioningLog.tsx`: real provisioning log stream
(SSE contract for Phase 4; sample replay in templates). No fake bars.
- `components/lab/Countdown.tsx`: server-authoritative TTL countdown.
- `components/course/upload-panel.tsx`: teacher basic/advanced publishing.



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




## Roadmap

Phase 2b: plugin framework. (Backend tests (discovery, scoping, echo provider, crash isolation, config)

- UI slot system + reference widget (palestrix-widget-firstblood)
- Verify (pytest + next build), update docs/READMEs

)  
Phase 3: gamification. Phase 4: orchestration + TTL reaper. Phase 5: live feature surfaces. Phase 6: sandbox module. Phase 7: multitenant layer + hardened deployments. Phase 8: Canvas LMS integration. Details in [docs/architecture.md](docs/architecture.md).
# PalestrIX

A gamified, multitenant, deployment-agnostic cyber training range for
institutional learning — assembled entirely from open-source components.

Students train on real but ephemeral virtual machines and containers, earn the
Palestras currency for genuine progress, and compete in a capture-the-flag
arena. Teachers publish labs without touching infrastructure. Administrators
run the whole range from one console. Every class section is an isolated
tenant with its own network and quota.

PalestrIX is the software artifact of an undergraduate research study at Holy
Angel University. The paper that specifies it is the project's contract: where
this codebase and that paper disagree, the paper wins.

> **Working here?** Read **[PLAN.md](PLAN.md)** first. It carries the
> reconciliation ledger, the active workstreams, and the progress log. This
> README describes what the platform *is*; PLAN.md describes what is *left*.

---

## Status

All eight development increments are functionally built and the backend suite
passes **146 tests**. What remains is the evaluation apparatus the study
requires — a Track A performance harness and the ISO/IEC 25010 questionnaire —
neither of which exists yet. See [PLAN.md §6](PLAN.md).

| # | Increment | State |
| --- | --- | --- |
| 1 | Frontend surfaces, locked design system, deployment docs | Built |
| 2 | Core service: passkey auth, RBAC, versioned API, webhook/event bus, object storage | Built |
| 3 | Plugin framework: discovery, capability scoping, encrypted config, crash isolation, UI slots | Built |
| 4 | Gamification: ledger, caps, streaks, community score, leaderboards | Built |
| 5 | Orchestration: provider abstraction, Docker + Proxmox VE adapters, log stream, TTL reaper | Built |
| 6 | Feature surfaces wired to the versioned API | Built |
| 7 | Malware sandbox: static pre-analysis, ATT&CK verdict, sealed storage | Built |
| 8 | Multitenancy, hardening, and Canvas LTI 1.3 | Built |
| — | **Track A performance harness** | **Not started** |
| — | **ISO/IEC 25010 instrument** | **Not started** |
| — | **VirtualBox demo adapter** (low-spec demo path) | **Not started** |

---

## Run it

```bash
# 1 — backend dependencies, plus the reference plugin
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements-dev.txt
pip install -e plugins/palestrix-provider-demo    # required: entry-point discovery

# 2 — verify
pytest backend/tests -q                           # → 146 passed

# 3 — the core API
python -m palestrix.seed                          # demo tenant, users, event
uvicorn palestrix.main:app --reload --port 8000   # run from backend/

# 4 — the frontend
npm install && npm run dev                        # http://localhost:3000
```

Sign in with the seed account `rafaela@example.edu` / `palestrix-dev-only!`
(other roles in `backend/palestrix/seed.py`). The frontend reads
`NEXT_PUBLIC_PALESTRIX_API`, defaulting to `http://localhost:8000`.

> Skipping the `pip install -e` step makes four plugin tests fail. They are not
> defects — the reference plugin is discovered through entry points and must be
> installed. Tracked as G-06 in [PLAN.md](PLAN.md).

> **Development defaults are not evaluation defaults.** Out of the box the
> queue runs inline, storage is a local folder, the reaper is off, and the
> database is SQLite. The study's Track A requires Redis, MinIO, an active
> reaper, and PostgreSQL. `hardening.py` warns on each. Measuring under the
> defaults measures something the paper does not describe — see G-05.

---

## Surfaces

| Route | Surface |
| --- | --- |
| `/` | Marketing landing |
| `/login`, `/register` | Passkey-first authentication gateway |
| `/dashboard` | Active instance, progress, Palestras balance, leaderboard |
| `/academy` | Four shipped paths, module roadmap, certification state |
| `/courses` | Teacher course manager and lab publishing |
| `/labs/[id]` | Active ephemeral lab: connection, TTL countdown, live log stream |
| `/sandbox` | Malware sandbox: submission, verdict, behavior timeline |
| `/community` | Writeups, profiles, community score |
| `/compete` | CTF arena: board, flags, first blood, leaderboard |
| `/admin/*` | Infrastructure, users, plugins, tenants |

Every product surface renders live `/api/v1` responses through the typed client
in [`lib/api/`](lib/api/). The TTL countdown reads the server's expiry
timestamp; the provisioning log is a real authenticated SSE stream.

### The academy catalog

The four learning paths the landing page advertises — **SOC Analyst** (14
modules), **Web Exploitation** (12), **Network Defense** (10), and **Digital
Forensics** (11) — are content in version control, not demo fixtures. They live
in [`backend/palestrix/academy_catalog.py`](backend/palestrix/academy_catalog.py)
and the API applies them at startup, so publishing catalog changes to a running
deployment is `git pull` and a restart. No seed run, no SQL, no admin form.

Applying is insert-and-reconcile: a missing path is created, an existing one
keeps its row (and every completion pointing at it) while its title, hours, and
module order are refreshed from the file, and modules are matched by title so a
database seeded by an earlier release is adopted rather than duplicated. Nothing
is ever deleted, and a module a teacher added by hand keeps its place after the
catalog's. Set `PALESTRIX_ACADEMY_CATALOG_AUTOLOAD=0` to freeze the catalog and
manage paths through the API alone.

---

## Architecture

A layered system, API-first — every function exists as a versioned endpoint
before any screen calls it, so plugins and external tools consume exactly the
contract the platform's own interface does.

```
Next.js surfaces  →  FastAPI core (/api/v1)  →  PostgreSQL · Redis · MinIO
                            │
                            ├── provider abstraction → Proxmox VE (KVM/LXC) · Docker
                            ├── tenancy contract     → network + quota per tenant
                            ├── external platform    → Canvas (LTI 1.3)
                            └── detonator abstraction → sandbox (network-isolated)
```

The orchestration logic is written once and stays independent of the hypervisor
beneath it. The malware sandbox is deliberately outside this stack: a separate,
network-isolated service reached through the detonator abstraction.

Four algorithms carry the behavior that distinguishes the platform from a
conventional web application:

- **Ephemeral lifecycle + TTL reaper** — instances move
  `requested → provisioning → running → stopped → expired`; the reaper destroys
  what has lapsed and releases the tenant quota — including instances stranded
  before `running` by a dead worker, which settle as `failed` — while a slower
  reconciliation pass compares provider state against the registry so an orphan
  can never pin capacity in either direction.
- **Quota admission** — instances, vCPU, and memory are checked before a job is
  queued, and a refusal *names the quota that blocked it*.
- **Palestras ledger** — append-only, single minter and burner, daily cap per
  source, awards scaled by prior solve count, first-blood bonus. Currency
  cannot be farmed by repetition, only earned by progress.
- **Community score** — decays with recency, so standing reflects present
  contribution rather than accumulated history.

---

## Deployment paths

Three paths, and they are **not** interchangeable.

| Path | Role | Isolation mechanism | Produces reportable data? |
| --- | --- | --- | --- |
| **Proxmox VE workstation** | **Final / reference deployment** | VLAN tag on a VLAN-aware trunk bridge | **Yes** — this is the study's measurement surface |
| **Cloud** | Documented alternative for renting capacity | Per-tenant subnet / namespace | Documented, not the focus |
| **VirtualBox** | **Demo only**, for low-specification machines | Per-tenant internal network, no host NIC path | **No** |

The VirtualBox path exists so the platform can be demonstrated end to end on a
laptop. It is deliberately **not a measurement surface**: no telemetry captured
under it may be reported as study performance data, and the performance harness
refuses to emit reference-grade output when running under it. Container and VM
costs differ, hosts differ, and the study reports no figure as a property of
the platform independent of the machine that produced it.

VirtualBox also isolates tenants differently. Proxmox tags a VLAN on a trunk
bridge; VirtualBox attaches each tenant to an internal network with no path to
a physical NIC. That is arguably stricter, but it does not trunk, does not span
hosts, and is not the mechanism the study describes — so a VirtualBox demo must
never be presented as having demonstrated VLAN-backed isolation.

Planning and open items for this path: [PLAN.md §W5 and G-11](PLAN.md).

---

## Documentation

| Document | Contents |
| --- | --- |
| [PLAN.md](PLAN.md) | **Re-plan, reconciliation ledger, progress** |
| [docs/architecture.md](docs/architecture.md) | System map, services, build order |
| [docs/ephemeral-lifecycle.md](docs/ephemeral-lifecycle.md) | Instance state machine, reaper, tenancy invariants |
| [docs/rbac-matrix.md](docs/rbac-matrix.md) | Role/capability matrix and gamification rules |
| [docs/public-api.md](docs/public-api.md) | `/api/v1` surface, auth, webhooks, versioning |
| [docs/install-usecase-a-baremetal.md](docs/install-usecase-a-baremetal.md) | Step-by-step install: single Proxmox VE workstation |
| [docs/install-usecase-b-cloud-aws.md](docs/install-usecase-b-cloud-aws.md) | Step-by-step install: cloud |
| [docs/usecase-a-baremetal.md](docs/usecase-a-baremetal.md) | Bare-metal runbook (the study's reference deployment) |
| [docs/usecase-b-cloud-aws.md](docs/usecase-b-cloud-aws.md) | Cloud runbook |
| [docs/lab-networking.md](docs/lab-networking.md) | Lab isolation, VLANs, student access |
| [docs/sandbox-security.md](docs/sandbox-security.md) | Sandbox isolation and hardening |
| [docs/managing-courses-and-users.md](docs/managing-courses-and-users.md) | Classes, modules, enrollment, roles |
| [docs/automated-checking.md](docs/automated-checking.md) | Rubric autograding → gradebook → Canvas passback |
| [docs/integrations-canvas-lms.md](docs/integrations-canvas-lms.md) | `ExternalPlatform` adapter, Canvas reference |
| [docs/plugin-development.md](docs/plugin-development.md) | Manifest, lifecycle hooks, UI slots, sandboxing |

---

## Stack

Every component is open-source — a requirement of the study, not a
convenience, since the platform must be deployable without a licensing budget.

| Layer | Components |
| --- | --- |
| Web interface | Next.js, React, TypeScript, Tailwind CSS |
| Core service | FastAPI, Python, Pydantic, SQLAlchemy |
| Authentication | WebAuthn (passkeys), Argon2 |
| Database | PostgreSQL |
| Queue and worker | Redis, RQ |
| Object storage | MinIO |
| Virtualization | Proxmox VE (KVM and LXC), Docker |
| Demo virtualization | VirtualBox — low-spec demo only, not a measurement surface |
| Managed cloud *(optional)* | OpenNebula, Apache CloudStack |
| Edge | Caddy or Traefik |
| Integration | LTI 1.3, Canvas LMS |
| Analysis | Jamovi, sysstat, docker stats |

---

## Plugins

Server plugins are Python packages on a versioned manifest with capability
scopes, encrypted config, and crash isolation. UI plugins mount lazy,
code-split widgets into declared slots. Two reference plugins under
[`plugins/`](plugins/) double as contract tests:

- **`palestrix-provider-demo`** — an instant echo instance provider; the
  provider-authoring tutorial, exercised by the backend suite.
- **`palestrix-widget-firstblood`** — a first-blood feed widget on the
  `dashboard.widgets` slot; the UI-slot tutorial.

See [docs/plugin-development.md](docs/plugin-development.md).

---

## Branches

| Branch | Purpose |
| --- | --- |
| `master` | Mainline |
| `archive` | Frozen pre-replan snapshot @ `e008971`. **Never force-push.** |
| `claude/replan-archive-docs-4d6ahv` | Active re-plan work |

---

## Scope and limits

PalestrIX is a **training and educational platform**, not a production security
product for defending a live network.

The sandbox performs real static analysis, but its built-in detonator produces
a **clearly labelled simulated** dynamic trace unless a separate live
detonation host is attached. Operating a public malware-analysis service is
outside the study.

The reference deployment targets a single Proxmox VE workstation; the
OpenNebula and CloudStack adapters are optional and not the focus. The
VirtualBox path is a demonstration convenience for low-specification machines
and carries no reportable performance data. Canvas is the only LMS integrated —
others can be added through the same adapter design. Paid subscriptions,
billing, and native mobile applications are out of scope.

Because the platform runs real machines, provisioning latency and concurrent
capacity are a direct function of the host hardware and are always reported
alongside the specification of the machine that produced them.

---

## Authors

Raji Miguel Z. Dizon · Alexandra Sofia P. Flores · Justin Carl C. Garcia ·
Francisco V. Olpindo IV — Holy Angel University, Cyber Security.

The contribution claimed is the design and integration of open-source
components into a platform with the properties described above, not the
authorship of those components. Component licenses are observed and attributed.

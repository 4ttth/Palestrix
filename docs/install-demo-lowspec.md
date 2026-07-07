# Installing PalestrIX — Demo / Low-Spec Workstation (Docker Compose)

The full PalestrIX service topology on one ordinary machine — a laptop, a
lab desktop, a spare mini-PC — with a single command. No hypervisor, no
VLAN switch, no public domain. This is the path for evaluating the
platform, developing against it, or running a classroom demo before
committing hardware; the production runbooks are
[install-usecase-a-baremetal.md](install-usecase-a-baremetal.md) (your own
servers) and [install-usecase-b-cloud-aws.md](install-usecase-b-cloud-aws.md)
(AWS).

**What you end up with:** PostgreSQL, Redis + a real orchestration worker,
MinIO object storage, the FastAPI core API, and the Next.js frontend — the
same six-service shape as production — seeded with demo accounts for all
four roles. Optionally (§6), real container labs running on your machine's
own Docker Engine, with per-tenant networks and TTL reaping.

**What is real and what is simulated:**

| Surface | In this stack |
|---|---|
| Auth (password, passkeys), RBAC, sessions | Real (passkeys work on `localhost`) |
| Courses, assignments, grading, writeups, votes | Real |
| Gamification: ledger, streaks, leaderboards, first blood | Real |
| CTF events, flag submission, cooldowns | Real |
| Orchestration queue, worker, TTL reaper | Real (Redis + RQ, as in production) |
| Container labs | Simulated by default; **real** with the §6 overlay |
| VM labs (Proxmox) | Simulated (no hypervisor on a workstation) |
| Multitenancy: tenants, VLAN/CIDR allocation, quotas | Real registry + quota enforcement; VLANs are records, not switch config |
| Sandbox static analysis (typing, entropy, strings, IOCs) | Real |
| Sandbox dynamic trace | Simulated by the demo detonator, labelled as such |
| Canvas LMS | Off (needs a URL Canvas can reach; see §8) |

## Contents

1. [Prerequisites](#1-prerequisites)
2. [Get the code](#2-get-the-code)
3. [Start the stack](#3-start-the-stack)
4. [Sign in](#4-sign-in)
5. [A guided tour](#5-a-guided-tour)
6. [Real container labs (opt-in)](#6-real-container-labs-opt-in)
7. [Passkeys on localhost](#7-passkeys-on-localhost)
8. [Canvas LMS from a workstation](#8-canvas-lms-from-a-workstation)
9. [Operating the stack](#9-operating-the-stack)
10. [What this demo deliberately is not](#10-what-this-demo-deliberately-is-not)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Prerequisites

| You need | Details |
|---|---|
| Docker | Docker Desktop (Windows/macOS) or Docker Engine + Compose v2 (Linux). Verify: `docker compose version` |
| CPU / RAM | 2 cores / 4 GB free for the stack itself; 8 GB total machine RAM is comfortable. Apple Silicon and x86-64 both work (all images are multi-arch) |
| Disk | ~10 GB free (images + volumes) |
| Ports free | 3000 (frontend), 8000 (API), 9001 (MinIO console) — all bound to `127.0.0.1` only |

Windows: install Docker Desktop with the WSL 2 backend (its default).
Everything below runs the same in PowerShell or a WSL shell.

## 2. Get the code

```sh
git clone https://github.com/<your-org>/palestrix.git
cd palestrix
```

## 3. Start the stack

```sh
docker compose up --build -d
```

The first run builds two images (a few minutes: `npm ci` + `next build`
dominate) and pulls four (PostgreSQL 16, Redis 7, MinIO, the Docker CLI
stage). Subsequent starts are seconds. Then:

```sh
docker compose ps        # all services Up, api "healthy"
curl http://localhost:8000/healthz    # {"ok":true}
```

On first boot the API creates the schema, runs the additive migrations, and
seeds the demo data (tenant, four role accounts, a course, a learning path,
a CTF event, lab templates, a sandbox report). The seed is idempotent —
restarts never duplicate it.

What is where:

| URL | What |
|---|---|
| http://localhost:3000 | The product |
| http://localhost:8000/api/v1/docs | Swagger UI on the live API |
| http://localhost:9001 | MinIO console (`palestrix` / `palestrix-minio-demo`) |

## 4. Sign in

Open <http://localhost:3000> and sign in. Every demo account's password is
`palestrix-dev-only!`:

| Role | Email | See |
|---|---|---|
| Student | `rafaela@example.edu` | Dashboard, labs, compete, academy, sandbox |
| Teacher | `delacruz@example.edu` | Course manager, publishing, Canvas panel |
| Admin | `odessa@example.edu` | Admin → Infrastructure (registry, ISOs, tenants) |
| Superadmin | `root@example.edu` | Everything + the plugin console |

> These credentials exist for local demos only and are printed by the seed;
> never expose this stack to a network with them in place.

## 5. A guided tour

Fifteen minutes, one surface at a time — this exercises every live
subsystem:

1. **Student** (`rafaela@…`): the dashboard shows a real Palestras balance,
   streak, and rank from the gamification service. Open **Labs**, launch
   *Blue Team: Log Triage Under Fire* — the launch goes through the Redis
   queue to the worker; watch the provisioning log stream and the
   server-authoritative TTL countdown. Extend it (spends Palestras),
   then destroy it.
2. Open **Compete**, pick the seeded event, submit a wrong flag (watch the
   cooldown), then study a challenge and submit the right one — the ledger,
   leaderboard, and first-blood logic are all real. (Flags for the seeded
   challenges are in `backend/palestrix/seed.py`.)
3. Open **Sandbox**, upload any file. The static pre-check (file typing,
   entropy, strings, IOC extraction) is real analysis; the behavior
   timeline is the demo detonator's clearly-labelled simulation streaming
   over SSE.
4. **Teacher** (`delacruz@…`): open **Courses** — assignments, submission
   counts, and grading are live. Publish a quiz from the panel; grade a
   submission and watch the student's Palestras move.
5. **Admin** (`odessa@…`): **Admin → Infrastructure**. Create a tenant —
   it materializes a VLAN tag and a /24 from the pools on the spot. Edit
   its quotas; try archiving it. Upload an ISO to the library (stored in
   MinIO; on production it would also forward to the Proxmox cluster).
6. **Superadmin** (`root@…`): the plugin console lists the reference
   plugins; enable `provider-demo` and its widget slots appear.

## 6. Real container labs (opt-in)

By default, lab launches are simulated by the demo provider so the stack
touches nothing on your machine. To run **real container labs** on your
workstation's own Docker Engine, restart with the labs overlay:

```sh
docker compose -f docker-compose.yml -f docker-compose.labs.yml up -d
```

> **Security trade, stated plainly:** the overlay mounts your Docker socket
> into the API and worker containers, which is root-equivalent on this
> machine. Acceptable on a personal workstation running a local demo;
> not on a shared or internet-reachable box. The default stack mounts
> nothing.

Then, end to end:

1. Sign in as the teacher, open **Courses → publishing panel**, switch to
   the advanced (environment) mode, and publish a container lab. The
   archive is a gzipped tar containing at minimum a `Dockerfile`. A
   ready-made example:

   ```sh
   mkdir lab && printf 'FROM python:3.11-slim\nEXPOSE 80\nCMD ["python", "-m", "http.server", "80"]\n' > lab/Dockerfile
   tar -czf lab.tar.gz -C lab Dockerfile
   ```

2. Sign in as the student and launch it. The worker builds the image from
   the archive and starts the container with the tenant's dedicated bridge
   network (`net-<tenant-id>` — check `docker network ls`) and a published
   port on `127.0.0.1`. The instance card shows the port; the container
   itself is visible in `docker ps` labelled `palestrix.instance=<id>`.

3. Let the TTL lapse (or destroy it) — the reaper removes the real
   container and releases the tenant quota.

Resource limits per lab container default to 512 MB / 1 CPU
(`PALESTRIX_DOCKER_MEMORY_LIMIT` / `_CPU_LIMIT` in the overlay if you need
to change them).

## 7. Passkeys on localhost

`localhost` is a secure context, so **passkey enrollment and login work in
this stack** (Windows Hello, Touch ID, or a security key): sign in with the
password once, enroll a passkey from the session, sign out, and sign back
in with it. This is the same WebAuthn ceremony production uses — only the
RP ID differs.

## 8. Canvas LMS from a workstation

The Canvas adapter needs URLs that the Canvas server can fetch (JWKS,
launch, login), which `localhost` is not. For a demo against a real Canvas
instance, put a tunnel in front of the API (for example `ngrok http 8000`
or Tailscale Funnel), set `PALESTRIX_ORIGIN`/`PALESTRIX_CORS_ORIGINS` and
the frontend build arg to the tunnel origin, and follow
[integrations-canvas-lms.md](integrations-canvas-lms.md) with the tunnel
URL in place of the production domain. This is workable for a
demonstration; treat it as throwaway, not as a deployment.

## 9. Operating the stack

```sh
docker compose logs -f api          # or worker, web, db, redis, minio
docker compose restart api          # safe anytime; seed is idempotent
docker compose down                 # stop; data volumes survive
docker compose down -v              # stop AND erase all data (fresh next boot)
```

**Updating** after a `git pull`:

```sh
docker compose up --build -d        # rebuilds what changed, migrations run at boot
```

**Changing configuration:** edit the environment block in
`docker-compose.yml` (every key is documented in
[backend/.env.example](../backend/.env.example)) and `docker compose up -d`
to apply. The one value that is *not* runtime-changeable is the frontend's
API origin (`NEXT_PUBLIC_PALESTRIX_API`): it is baked into the browser
bundle at image build time, so changing it means rebuilding `web`.

## 10. What this demo deliberately is not

- **Not hardened.** `PALESTRIX_ENVIRONMENT` stays `development`: the stack
  runs on plain http with printed demo credentials, which the production
  boot guard exists to refuse. The API logs its readiness findings at
  startup — that list is exactly the gap between this demo and the
  baremetal runbook.
- **No VM labs.** The Proxmox adapter needs a hypervisor; VM-kind templates
  stay on the demo provider here. Everything else about them (publishing,
  quotas, TTLs, the registry) behaves identically.
- **VLANs are bookkeeping.** Tenant VLAN tags and subnets allocate and
  enforce quotas for real, but nothing programs a switch on a laptop.
  Container-lab tenant isolation (§6) uses per-tenant Docker networks,
  which *is* real network separation on this machine.
- **The sandbox does not detonate.** Static analysis is real; the dynamic
  trace is synthesized and labelled. Real detonation requires the isolated
  host (docs/sandbox-security.md) — never run one on your workstation.
- **Bound to localhost.** All published ports bind `127.0.0.1`; exposing
  this stack to a LAN requires the production runbook, not a compose edit.

## 11. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `port is already allocated` | Something on 3000/8000/9001 | Stop it, or change the left side of the port mapping in `docker-compose.yml` |
| `Cannot connect to the Docker daemon` | Docker Desktop not running / no perms | Start Docker Desktop; on Linux add yourself to the `docker` group |
| First build very slow | `npm ci` + `next build` | Normal once; later builds hit cache |
| `api` unhealthy, logs show DB errors | Boot raced Postgres init on a slow disk | `docker compose up -d` again; healthchecks order the retry |
| Login fails with demo accounts | Volume from an older checkout | `docker compose down -v && docker compose up --build -d` |
| Lab stuck `provisioning` with the labs overlay | Socket not mounted / arch mismatch in your lab image | Confirm both overlay files in the `-f` flags; check `docker compose logs worker` |
| Passkey prompt never appears | Browser blocks WebAuthn outside secure context | Use `http://localhost:3000` exactly — not a LAN IP |
| Frontend can't reach API after editing ports | `NEXT_PUBLIC_PALESTRIX_API` is baked at build time | Rebuild: `docker compose build web && docker compose up -d` |

**Acceptance check** (mirrors the production runbook's, scoped to the demo):

- [ ] All six services `Up`, `api` healthy; `/healthz` answers.
- [ ] Password and passkey sign-in both work from a clean browser.
- [ ] A lab launch streams provisioning logs and counts down its TTL.
- [ ] A flag submission moves Palestras and the leaderboard.
- [ ] A sandbox upload returns a report with real static findings.
- [ ] A tenant create materializes a VLAN + /24; quota edits stick.
- [ ] (Overlay) a published container lab serves real HTTP on its port and
      is destroyed by the reaper at TTL.

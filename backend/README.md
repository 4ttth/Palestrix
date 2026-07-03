# PalestrIX Core API (Phase 2 + 2b + 3 + 4 + 5 + 6 + 7)

Python / FastAPI backend: passkey-first auth, RBAC, the versioned `/api/v1`
surface, API-key and OAuth2 client-credentials auth for machines, the
webhook/event bus, object storage wiring, the plugin framework (discovery,
capability scoping, encrypted config, crash isolation), the gamification
service (Phase 3): the append-only Palestras ledger, per-source daily caps,
solve-count-scaled flag awards, streaks with a weekly checkpoint, community
score, and the student-only leaderboards, orchestration (Phase 4): the
job queue (inline or Redis), the Docker/Proxmox adapters, the SSE log stream,
and the TTL reaper with reconciliation, the malware sandbox module
(Phase 6, `palestrix/sandbox/`), and the multitenant layer with hardened
deployments (Phase 7): the `TenantCloud` contract with LocalCloud /
OpenNebula / CloudStack adapters, full tenant lifecycle over the admin API,
instances/vCPU/RAM quota enforcement at launch, tenant VLAN and subnet
wiring in the Proxmox/Docker adapters, additive startup migrations, security
headers, and the production boot guard. The web UI, plugins, and external
tools all consume this same contract (docs/public-api.md).

## Quickstart

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows (source .venv/bin/activate elsewhere)
pip install -r requirements-dev.txt
python -m palestrix.seed           # demo tenant, users, course, event
uvicorn palestrix.main:app --reload --port 8000
```

- Swagger UI: http://localhost:8000/api/v1/docs
- OpenAPI spec: http://localhost:8000/api/v1/openapi.json
- Demo login (development only): `rafaela@example.edu` / `palestrix-dev-only!`

To run the full product (Phase 5, live feature surfaces), start the frontend
in a second terminal — it consumes this API at `http://localhost:8000` by
default (`NEXT_PUBLIC_PALESTRIX_API` overrides):

```bash
npm install && npm run dev        # repository root; http://localhost:3000
```

CORS allows `http://localhost:3000` out of the box (`PALESTRIX_CORS_ORIGINS`).

Configuration comes from the environment or `.env` (see `.env.example`).
SQLite is the dev default; set `PALESTRIX_DATABASE_URL` to PostgreSQL for a
real deployment. Storage defaults to a local folder; set
`PALESTRIX_STORAGE_BACKEND=minio` for MinIO/S3.

## Tests

```bash
.venv\Scripts\python.exe -m pytest tests -q
```

63 tests cover registration/login, API-key scope limits and revocation,
OAuth2 client credentials, WebAuthn ceremony endpoints, the RBAC matrix over
HTTP, course/enrollment ownership, the CTF flow (first blood, cooldown,
duplicate solves, leaderboard), instance quotas and TTL extension spend, the
gamification rules (solve-count-scaled flag awards, the first-blood bonus as
its own ledger line, writeup earning under the staff no-earn rule, per-source
daily caps, streak accrual with the weekly checkpoint, community score, and
the student-only leaderboards), webhook fan-out with HMAC signature
verification, the plugin framework (entry-point + path discovery, the
contract version gate, capability-scoped service principals, required/secret
config with encryption at rest, the echo provider end to end, and crash
isolation), and orchestration (SSE log stream replay, stop/destroy transitions,
TTL reaper pass with quota release, provision failure retry policy, Docker
adapter with recorded CLI, and Proxmox VE adapter with mocked API), and the
Phase 5 surface contract (per-caller `completed`/`solved` flags, writeup and
course count enrichment, instance display enrichment, tenant usage, and the
admin ISO/provider read endpoints with their RBAC gates), the sandbox module
(Phase 6, 11 tests in test_sandbox.py), and the multitenant layer (Phase 7,
8 tests in test_tenancy.py: tenant materialization and lifecycle over the
API, the full instances/vCPU/RAM quota check with the named denial, the
Proxmox tenant-VLAN tag and admin ISO forwarding, the OpenNebula and
CloudStack adapters against mocked managers, the additive migrations, the
security headers, and the production boot guard). Plugin tests load
the installed `plugins/palestrix-provider-demo` package plus throwaway
fixtures under `tests/fixtures/`.

## Layout

| Module | Responsibility |
|---|---|
| `palestrix/models.py` | Full relational schema (all domains) |
| `palestrix/rbac.py` | Capability matrix, Principal, scope rules |
| `palestrix/security.py` | argon2id passwords, JWTs, API keys |
| `palestrix/webauthn_flow.py` | Passkey ceremonies (py_webauthn) |
| `palestrix/gamification.py` | The only minter/burner of Palestras: caps, streaks, community score, ranking |
| `palestrix/events.py` | Event bus + signed webhook deliveries |
| `palestrix/storage.py` | Object storage (local / MinIO) |
| `palestrix/providers.py` | Instance provider registry (demo + plugin-owned kinds) |
| `palestrix/orchestration/` | Job queue (inline/redis), handlers, TTL reaper, Docker/Proxmox adapters |
| `palestrix/tenancy/` | Multitenant cloud layer: TenantCloud contract, LocalCloud, OpenNebula/CloudStack adapters |
| `palestrix/hardening.py` | Production boot guard + security-headers middleware |
| `palestrix/migrations.py` | Additive startup migrations for pre-Phase-7 databases |
| `palestrix/plugins/` | Plugin framework: manifest, contract, registry (docs/plugin-development.md) |
| `palestrix/api/` | One router per resource group under `/api/v1` |
| `palestrix/seed.py` | Idempotent demo data (mirrors frontend mocks) |

## Phase boundaries honored here

- Instances route through **adapters** (Phase 4 complete):
  `palestrix/orchestration/docker.py` (CLI-driven, injectable runner),
  `palestrix/orchestration/proxmox.py` (httpx client, injectable for testing),
  plus a demo provider during early development. The queue backend
  (`palestrix/orchestration/queue.py`) is swappable: `inline` for dev/test
  (jobs run immediately), `redis` for production (workers consume async).
  Job handlers (`palestrix/orchestration/jobs.py`) manage provision retries
  (up to 2 attempts on failure). The reaper (`palestrix/orchestration/reaper.py`)
  runs scheduled (daemon thread for inline, loop in Redis worker) and fires
  whenever `expires_at < now()`, or manually via admin endpoint. HTTP contract
  stays as-is across all backends.
- The Palestras **ledger** and its balancing rules are live in
  `palestrix/gamification.py` — the single component allowed to mint or burn
  currency. Earn sources (module completion, solve-count-scaled flag capture,
  first-blood bonus, writeup publication, weekly streak checkpoint), spend
  sinks (TTL extensions), per-source daily caps, the student-only earn path,
  community-score decay, and the leaderboards all live there. Every other
  service posts a request to it with a reason code.
- The **malware sandbox** module is live in `palestrix/sandbox/` (Phase 6):
  a detonator abstraction (demo detonator with real static pre-check +
  simulated dynamic trace; coordinator adapter for an isolated host), the
  `/sandbox` API, a behavior-event SSE stream, and samples/reports sealed at
  rest. Set `PALESTRIX_SANDBOX_COORDINATOR_URL` to attach a live detonation
  host; leave it unset for the demo detonator. See docs/sandbox-security.md.
- The **multitenant cloud layer** is live in `palestrix/tenancy/` (Phase 7):
  a tenant is materialized at create time (VLAN tag + tenant CIDR from the
  registry pools; group/VDC/network on OpenNebula or domain/account/network
  on CloudStack when `PALESTRIX_CLOUD_BACKEND` names one), quota edits sync
  through, and archiving retires the manager objects while the row, VLAN,
  and CIDR stay reserved. The API enforces the instances/vCPU/RAM quotas at
  launch against each template's declared `cpu`/`ram_gb` spec, and the
  denial names the blocking quota. Deployments harden themselves: setting
  `PALESTRIX_ENVIRONMENT=production` arms the boot guard
  (`palestrix/hardening.py`) that refuses to start on dev secrets, SQLite,
  plaintext origins, disabled TLS verification, the inline queue, a
  disabled reaper, or local-folder storage; every response carries baseline
  security headers either way.

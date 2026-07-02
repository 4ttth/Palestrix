# PalestrIX Core API (Phase 2 + 2b)

Python / FastAPI backend: passkey-first auth, RBAC, the versioned `/api/v1`
surface, API-key and OAuth2 client-credentials auth for machines, the
webhook/event bus, object storage wiring, and the plugin framework
(discovery, capability scoping, encrypted config, crash isolation). The web
UI, plugins, and external tools all consume this same contract
(docs/public-api.md).

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

Configuration comes from the environment or `.env` (see `.env.example`).
SQLite is the dev default; set `PALESTRIX_DATABASE_URL` to PostgreSQL for a
real deployment. Storage defaults to a local folder; set
`PALESTRIX_STORAGE_BACKEND=minio` for MinIO/S3.

## Tests

```bash
.venv\Scripts\python.exe -m pytest tests -q
```

24 tests cover registration/login, API-key scope limits and revocation,
OAuth2 client credentials, WebAuthn ceremony endpoints, the RBAC matrix over
HTTP, course/enrollment ownership, the CTF flow (first blood, cooldown,
duplicate solves, leaderboard), instance quotas and TTL extension spend,
webhook fan-out with HMAC signature verification, and the plugin framework
(entry-point + path discovery, the contract version gate, capability-scoped
service principals, required/secret config with encryption at rest, the echo
provider end to end, and crash isolation). Plugin tests load the installed
`plugins/palestrix-provider-demo` package plus throwaway fixtures under
`tests/fixtures/`.

## Layout

| Module | Responsibility |
|---|---|
| `palestrix/models.py` | Full relational schema (all domains) |
| `palestrix/rbac.py` | Capability matrix, Principal, scope rules |
| `palestrix/security.py` | argon2id passwords, JWTs, API keys |
| `palestrix/webauthn_flow.py` | Passkey ceremonies (py_webauthn) |
| `palestrix/events.py` | Event bus + signed webhook deliveries |
| `palestrix/storage.py` | Object storage (local / MinIO) |
| `palestrix/providers.py` | Instance provider registry (demo + plugin-owned kinds) |
| `palestrix/plugins/` | Plugin framework: manifest, contract, registry (docs/plugin-development.md) |
| `palestrix/api/` | One router per resource group under `/api/v1` |
| `palestrix/seed.py` | Idempotent demo data (mirrors frontend mocks) |

## Phase boundaries honored here

- Instances run on a **demo provider** (instant provision, real registry,
  quotas, logs, states). Phase 4 swaps in the Proxmox/Docker adapters, the
  Redis job queue, the SSE log stream, and the TTL reaper; the HTTP
  contract stays as-is.
- The Palestras **ledger** is live (module completions and flag captures
  earn; TTL extensions spend). Phase 3 adds streaks, caps, decay, and the
  balancing rules.
- `/sandbox` endpoints are reserved (501) until the Phase 6 module.

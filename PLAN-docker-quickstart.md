# PLAN: Docker Compose quickstart — one command to a full demo stack

**Leverage rank: 5 of 5.** Today the only ways to run PalestrIX are the dev
two-terminal setup or the full multi-hour systemd runbooks
(`docs/install-usecase-a-baremetal.md` is ~580 lines). There is no
`Dockerfile` or `docker-compose.yml` anywhere in the repo. A
`docker compose up` path that boots Postgres + Redis + MinIO + API + worker
+ frontend, seeded with the demo data, is the difference between "clone and
evaluate in 5 minutes" and "read a runbook" — the highest-impact thing for
adoption, demos, and classroom pilots. Ranked last only because the other
four protect or complete existing work; this adds new surface.

## Goal

`docker compose up --build` from the repo root yields a working platform at
`http://localhost:3000` with the demo login
(`rafaela@example.edu` / `palestrix-dev-only!`), running on the
production-shaped service topology (PostgreSQL, Redis queue + worker,
MinIO) rather than the SQLite/inline shortcuts.

This is explicitly a **demo/eval stack**, not production: it keeps
`PALESTRIX_ENVIRONMENT=development` (see edge case 1) and http origins.

## Files to touch

1. `backend/Dockerfile` — new.
2. `Dockerfile.web` — new, repo root (the frontend build context is the
   whole repo root: `app/`, `components/`, `lib/`, configs).
3. `docker-compose.yml` — new, repo root.
4. `.dockerignore` — new, repo root.
5. `README.md` — a short "Run it with Docker" subsection under "## Run it".

## Step-by-step implementation order

### Step 1 — `.dockerignore`

```
node_modules
.next
backend/.venv
backend/palestrix.db
backend/.objects
**/__pycache__
.git
```

### Step 2 — `backend/Dockerfile`

Build context will be the **repo root** (the API image must also contain
`plugins/palestrix-provider-demo` for entry-point plugin parity with the
test suite and demo):

```dockerfile
FROM python:3.11-slim
WORKDIR /srv
COPY backend/requirements.txt backend/requirements-dev.txt backend/
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY plugins/palestrix-provider-demo plugins/palestrix-provider-demo
RUN pip install --no-cache-dir -e plugins/palestrix-provider-demo
COPY backend/palestrix backend/palestrix
WORKDIR /srv/backend
EXPOSE 8000
CMD ["uvicorn", "palestrix.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Step 3 — `Dockerfile.web`

`NEXT_PUBLIC_*` variables are **inlined at build time** by Next.js, so the
API origin must arrive as a build arg, not a runtime env:

```dockerfile
FROM node:22-slim
WORKDIR /srv
COPY package.json package-lock.json ./
RUN npm ci
COPY next.config.ts tsconfig.json postcss.config.mjs ./
COPY app app
COPY components components
COPY lib lib
ARG NEXT_PUBLIC_PALESTRIX_API=http://localhost:8000
ENV NEXT_PUBLIC_PALESTRIX_API=$NEXT_PUBLIC_PALESTRIX_API
RUN npm run build
EXPOSE 3000
CMD ["npm", "run", "start"]
```

Before finalizing, check `next.config.ts` and `package.json` for anything
else the build reads (e.g. `public/` — if a `public/` directory exists in
the repo, COPY it too; check first with `ls`).

### Step 4 — `docker-compose.yml`

Services (names matter — they become DNS hostnames referenced in env vars):

- **db**: `postgres:16-alpine`; env `POSTGRES_USER=palestrix`,
  `POSTGRES_PASSWORD=palestrix`, `POSTGRES_DB=palestrix`; volume
  `pgdata:/var/lib/postgresql/data`; healthcheck
  `pg_isready -U palestrix` (interval 2s, retries 30).
- **redis**: `redis:7-alpine`; healthcheck `redis-cli ping`.
- **minio**: `minio/minio`, command `server /data --console-address :9001`;
  env `MINIO_ROOT_USER=palestrix`, `MINIO_ROOT_PASSWORD=palestrix-minio`;
  volume `miniodata:/data`; healthcheck against
  `http://localhost:9000/minio/health/live` (use `mc ready local` or
  curl — check what the image ships; busybox wget works:
  `wget -q --spider http://localhost:9000/minio/health/live`).
- **api**: build `context: .`, `dockerfile: backend/Dockerfile`; ports
  `8000:8000`; `depends_on` all three with `condition: service_healthy`;
  environment (every name verified against `backend/palestrix/config.py`):
  ```yaml
  PALESTRIX_DATABASE_URL: postgresql+psycopg://palestrix:palestrix@db:5432/palestrix
  PALESTRIX_QUEUE_BACKEND: redis
  PALESTRIX_REDIS_URL: redis://redis:6379/0
  PALESTRIX_STORAGE_BACKEND: minio
  PALESTRIX_MINIO_ENDPOINT: minio:9000
  PALESTRIX_MINIO_ACCESS_KEY: palestrix
  PALESTRIX_MINIO_SECRET_KEY: palestrix-minio
  PALESTRIX_CORS_ORIGINS: http://localhost:3000
  PALESTRIX_ORIGIN: http://localhost:3000
  PALESTRIX_SECRET_KEY: compose-demo-secret-0123456789abcdef   # 32+ chars, demo only
  PALESTRIX_REAPER_ENABLED: "false"    # the worker owns the reaper loop
  ```
  Command override to seed then serve (seed is idempotent — safe on every
  boot; it prints and skips existing rows):
  ```yaml
  command: sh -c "python -m palestrix.seed && uvicorn palestrix.main:app --host 0.0.0.0 --port 8000"
  ```
- **worker**: same build as api; command `python -m palestrix.worker`;
  same environment block as api but `PALESTRIX_REAPER_ENABLED: "true"`
  (read `backend/palestrix/worker.py` — it refuses to start unless
  `PALESTRIX_QUEUE_BACKEND=redis`, which is exactly what we set);
  `depends_on: api` (`service_started` is fine — the API's seed run creates
  the schema first; use `condition: service_healthy` on api if you add an
  api healthcheck hitting `/healthz`).
- **web**: build `context: .`, `dockerfile: Dockerfile.web`, build arg
  `NEXT_PUBLIC_PALESTRIX_API: http://localhost:8000`; ports `3000:3000`;
  `depends_on: api`.
- Top-level `volumes: pgdata: {} miniodata: {}`.

### Step 5 — Reaper split check

The API's `reaper_enabled` default is `true` and the reaper also dispatches
grade passbacks. Read `backend/palestrix/main.py` and
`backend/palestrix/orchestration/reaper.py` to confirm where the reaper
starts in redis mode; the worker docstring says it "owns the TTL reaper
loop" for Redis deployments, hence the split above (api: off, worker: on).
If reading the code shows the API ignores `reaper_enabled` when the queue
is redis, simplify and drop the override — follow the code, not this plan.

### Step 6 — README

Under "## Run it", add:

```markdown
### Or with Docker

​```bash
docker compose up --build
​```

Frontend on http://localhost:3000, API on http://localhost:8000
(Swagger at /api/v1/docs), MinIO console on http://localhost:9001.
Demo login: `rafaela@example.edu` / `palestrix-dev-only!`. This stack is
for evaluation — see docs/install-usecase-a-baremetal.md for production.
```

### Step 7 — Verify end to end (do not skip)

```bash
docker compose up --build -d
docker compose ps                    # all services healthy/running
curl -s http://localhost:8000/healthz
curl -s http://localhost:8000/api/v1/openapi.json | head -c 200
# Login round-trip through the real stack:
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"rafaela@example.edu","password":"palestrix-dev-only!"}'
# expect an access_token
docker compose logs worker | tail    # worker consuming, no crash loop
```

Then open `http://localhost:3000`, log in with the demo password, and
confirm the dashboard renders live data (Palestras balance, streak).
Finally `docker compose down -v` and `up` again to prove clean re-creation.

## Edge cases a weaker model would miss

1. **The production boot guard will kill the stack if you set
   `PALESTRIX_ENVIRONMENT=production`.** `hardening.py` refuses to start on
   any readiness finding — and this demo stack has several by design (http
   origin, http CORS). Leave the environment at its `development` default;
   the findings then log as warnings. Do not "fix" this by weakening
   `hardening.py`.
2. **`postgresql://` URLs break — it must be `postgresql+psycopg://`.**
   `requirements.txt` installs **psycopg 3** (`psycopg[binary]`), but
   SQLAlchemy's bare `postgresql://` scheme defaults to the psycopg2
   driver, which is not installed → `ModuleNotFoundError: psycopg2` at
   startup.
3. **`NEXT_PUBLIC_PALESTRIX_API` is baked at `npm run build`.** Setting it
   as a runtime env on the web container does nothing; the browser bundle
   already contains whatever value existed at build time. It must be a
   Docker build ARG. Also: the value is used by the *browser*, so it must
   be `http://localhost:8000` (host-reachable), NOT `http://api:8000`
   (compose-internal DNS the browser can't resolve).
4. **The worker exits on purpose without `PALESTRIX_QUEUE_BACKEND=redis`**
   (`worker.py` docstring: "refuses to start … to catch a half-configured
   deployment early"). If the worker crash-loops, the env block diverged
   between api and worker — keep them identical except the reaper flag.
5. **Seed must run against Postgres after Postgres is *ready*, not just
   started.** Use the `pg_isready` healthcheck + `condition:
   service_healthy`; `depends_on` without a condition only orders container
   start, and the seed would race the DB and crash the api container on
   first boot (classically "works on retry").
6. **Passkeys won't enroll over plain http from another host, and that's
   fine.** WebAuthn works on `localhost` as a secure context; the demo
   password login always works. Don't chase https certs for the demo stack.
7. **MinIO buckets are auto-created** by `MinioStorage.__init__`
   (`storage.py:100`) — no `mc mb` init container needed. But the API must
   not start before MinIO's health endpoint answers, or the constructor's
   `bucket_exists` call throws on boot.
8. **`PALESTRIX_SECRET_KEY` must be ≥ 32 characters** (hardening checks it,
   and short keys are a real risk) — the compose file ships a labeled
   demo value; the README should tell people to change it if the stack
   outlives a demo.
9. **Seed idempotency is already guaranteed** (`seed.py` docstring:
   "Idempotent: safe to re-run") — running it in the api command on every
   boot is deliberate and safe; don't wrap it in first-run marker files.
10. **No Docker socket mounting.** The lab-instance Docker provider
    (`PALESTRIX_DOCKER_ENABLED`) defaults to off; leave it off. Mounting
    `/var/run/docker.sock` into the API container to make lab launches work
    is a container-escape-grade decision that belongs in the runbooks, not
    a demo compose file. Lab launch buttons will 4xx politely; that is
    acceptable for the demo.

## Acceptance criteria

- [ ] Fresh clone + `docker compose up --build` (no other steps) reaches:
      `GET http://localhost:8000/healthz` OK, frontend at
      `http://localhost:3000` renders, demo password login succeeds in the
      browser, dashboard shows seeded balance/streak numbers.
- [ ] `docker compose ps` shows db, redis, minio, api, worker, web all
      up; worker logs show it consuming (no restart loop).
- [ ] The stack uses Postgres (`docker compose exec db psql -U palestrix
      -c '\dt'` lists the palestrix tables), Redis queue, and MinIO
      (`users`/sandbox buckets exist in the MinIO console).
- [ ] `docker compose down -v && docker compose up` works again from
      empty volumes (seed re-runs cleanly).
- [ ] `docker compose restart api` does not duplicate seed data
      (idempotency holds against a populated DB).
- [ ] No application source files modified — only the four new files plus
      the README section (`git diff --stat` confirms).
- [ ] `cd backend && python -m pytest tests -q` still fully green (nothing
      about the host dev flow changed).

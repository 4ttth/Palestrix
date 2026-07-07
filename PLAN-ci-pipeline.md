# PLAN: CI pipeline — GitHub Actions for backend tests + frontend build

**Leverage rank: 2 of 5.** The repository has **no `.github/` directory at
all** — no workflow has ever run. Eight phases of work (71 backend tests, a
type-checked Next.js build) are only verified when someone remembers to run
them locally. Exploration proved the cost concretely: a fresh environment
fails 4 plugin tests unless a non-obvious setup step is performed, and
nothing catches that today. Every future phase, plan, and PR benefits from
this landing early.

## Goal

A single GitHub Actions workflow that, on every push and pull request, runs
the full backend test suite (all 71 tests, including the entry-point plugin
tests) and the frontend production build (which includes TypeScript
checking). Green = both pass.

## Files to touch

1. `.github/workflows/ci.yml` — new file (the only required change).
2. `README.md` — optional single-line status badge at the top (do this only
   if the badge line does not disturb the first heading; skip if unsure).

## Ground truth (verified by running everything on 2026-07-07)

- Backend: Python 3.11 works. Install `backend/requirements-dev.txt`
  (which `-r` includes `requirements.txt`), **then**
  `pip install -e plugins/palestrix-provider-demo` (repo-root relative).
  Then `cd backend && python -m pytest tests -q` → `71 passed`.
  Without the editable plugin install: `4 failed, 67 passed` — the failures
  are in `tests/test_plugins.py` (entry-point discovery of `provider-demo`).
- Frontend: `npm ci` then `npm run build` → succeeds. `next build` runs
  TypeScript type-checking itself, so no separate `tsc --noEmit` job is
  needed. There is **no** `lint` or `test` script in `package.json` — do not
  invent one or call `npm test`.
- The backend tests use SQLite and an inline queue by default — no services
  (Postgres/Redis/MinIO) are needed in CI.

## Step-by-step implementation order

### Step 1 — Create `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [master]
  pull_request:

jobs:
  backend:
    name: Backend tests (pytest)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: backend/requirements*.txt
      - name: Install dependencies
        run: |
          pip install -r backend/requirements-dev.txt
          pip install -e plugins/palestrix-provider-demo
      - name: Run test suite
        working-directory: backend
        run: python -m pytest tests -q

  frontend:
    name: Frontend build (next build)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
      - name: Install dependencies
        run: npm ci
      - name: Build
        run: npm run build
```

Notes on choices (keep them):
- `on.push.branches: [master]` — the default branch is `master`, not `main`.
  `pull_request` with no filter covers all PRs.
- The plugin install step runs from the repo root (default working
  directory), so the path is `plugins/palestrix-provider-demo` — NOT
  `../plugins/...` (that form is only correct from inside `backend/`).
- `working-directory: backend` on the pytest step is mandatory (see edge
  cases).

### Step 2 — Verify locally before pushing

Simulate both jobs in a clean state:

```bash
python3 -m venv /tmp/ci-venv && . /tmp/ci-venv/bin/activate
pip install -r backend/requirements-dev.txt
pip install -e plugins/palestrix-provider-demo
cd backend && python -m pytest tests -q && cd ..   # expect 71 passed
deactivate
npm ci && npm run build                             # expect success
```

### Step 3 — Push and confirm

Push the workflow, then check the run status via the GitHub Actions UI or
API. Both jobs must be green on the first run. If the backend job fails with
exactly 4 `test_plugins.py` failures, the plugin install step is missing or
its path is wrong — fix the path, do not touch the tests.

### Step 4 (optional) — README badge

Add directly under the `# PalestrIX` heading:

```markdown
![CI](https://github.com/4ttth/Palestrix/actions/workflows/ci.yml/badge.svg)
```

## Edge cases a weaker model would miss

1. **The plugin editable-install is load-bearing.** `test_plugins.py`
   asserts `{"provider-demo", "crashy", "needy", "oldapi"} <= discovered
   ids`. The last three are path-discovered test fixtures (already in the
   repo); `provider-demo` only appears when
   `plugins/palestrix-provider-demo` is pip-installed so its
   `palestrix.plugins` entry point registers. Skipping this step produces a
   confusing 4-test failure that looks like a plugin-framework bug.
2. **Working directory matters twice, differently.** pytest must run from
   `backend/` (`pytest tests` — the path is relative), while the plugin
   install path `plugins/palestrix-provider-demo` is relative to the repo
   root. Mixing these up gives "file or directory not found" from pytest or
   "neither a file nor a directory" from pip.
3. **Do not add service containers.** The suite intentionally runs on
   SQLite + inline queue + local-folder storage (the app logs
   "not production-ready" warnings for these at startup — those warnings
   are expected in tests, not errors).
4. **Do not call `npm test` or `npm run lint`** — neither script exists;
   the job would fail with "Missing script". `next build` already
   type-checks.
5. **Default branch is `master`.** A copy-pasted workflow with
   `branches: [main]` would silently never run on pushes.
6. **Python version floor.** The code uses SQLAlchemy 2 typed mappings and
   `X | None` unions; 3.11 is verified. Don't pin 3.9/3.10.
7. **`requirements.txt` has an environment marker**
   (`psycopg[binary]>=3.2; platform_python_implementation == "CPython"`) —
   normal CPython runners satisfy it; nothing to do, just don't "clean it up".

## Acceptance criteria

- [ ] `.github/workflows/ci.yml` exists with two jobs: `backend` and
      `frontend`.
- [ ] The workflow triggers on `push` to `master` and on `pull_request`.
- [ ] The backend job installs `backend/requirements-dev.txt` AND
      `plugins/palestrix-provider-demo` (editable), then runs
      `python -m pytest tests -q` with `working-directory: backend`.
- [ ] The frontend job runs `npm ci` then `npm run build` at the repo root.
- [ ] Both jobs pass on the actual pushed commit (verify the run, don't
      assume).
- [ ] No changes to any test, plugin, or application source file.

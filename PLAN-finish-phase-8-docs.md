# PLAN: Finish Phase 8 — documentation sync + verified green state

**Leverage rank: 1 of 5 (do this first).** It is the only unchecked item on the
project's own Phase 8 todo list (README.md, last bullet under "Phase 8 …
**Todos:**"), it is small, and every other plan builds on a repo whose docs
tell the truth. When this lands, Phase 8 is done.

## Goal

Bring every document that describes the platform up to date with the Phase 8
reality (Canvas LMS integration shipped, 71 backend tests, install guides
written), fix the stale/broken spots found during exploration, and record a
verified green state (71 tests pass, `next build` succeeds).

## Files to touch

1. `README.md`
2. `backend/README.md`
3. `docs/public-api.md`
4. `docs/architecture.md`
5. `docs/integrations-canvas-lms.md` (verification pass only; likely already current)

Do **not** touch any `.py` or `.ts`/`.tsx` file in this plan. This is a
documentation-only change plus verification runs.

## Ground truth to verify against (established by exploration on 2026-07-07)

- Full backend suite: **71 tests pass** — but ONLY after the demo plugin
  package is installed into the venv (`pip install -e plugins/palestrix-provider-demo`
  from the repo root). Without it, exactly 4 tests in
  `backend/tests/test_plugins.py` fail because `provider-demo` is discovered
  via Python entry points, not via path discovery. This is a required setup
  step that `backend/README.md` currently omits.
- `npm run build` (Next.js 15) succeeds with all 13 routes.
- `backend/.env.example` **does not exist**, but `backend/README.md` says
  "Configuration comes from the environment or `.env` (see `.env.example`)".

## Step-by-step implementation order

### Step 1 — Verify the green state first

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e ../plugins/palestrix-provider-demo   # REQUIRED, see above
python -m pytest tests -q        # expect: 71 passed
cd ..
npm ci && npm run build          # expect: build succeeds, 13 routes
```

If either fails, STOP and report the failure instead of updating docs to
claim green.

### Step 2 — `README.md`

- Line ~45: the status paragraph ends with
  `Next: Phase 8 (Canvas LMS integration + step-by-step install documentation).`
  Replace with a sentence in the same voice summarizing Phase 8 as shipped:
  the `ExternalPlatform` contract (`backend/palestrix/integrations/`), the
  Canvas LMS adapter (LTI 1.3 launch, NRPS roster sync, AGS grade passback,
  deep linking), the grade-passback queue with retry, the `/integrations`
  API surface, the Canvas panel in the course view, and the two step-by-step
  install guides (`docs/install-usecase-a-baremetal.md`,
  `docs/install-usecase-b-cloud-aws.md`). Also update the sentence
  "**Status: Phase 7 complete.**" near the top of that paragraph to
  "**Status: Phase 8 complete.**".
- The "Phase 8 … **Todos:**" section (line ~207): convert it to the same
  "**Done**" prose format the Phase 6/7 sections use (look at those sections
  and mirror their structure). Strike through / remove the todo list, state
  "Full test suite: 71 tests pass." at the end, matching the phrasing of the
  earlier phases ("Full test suite: 63 tests pass." etc.).
- Fix the broken markdown in the current todo list if any of it is kept:
  `test_[integrations.py](http://integrations.py)` is a mangled autolink —
  it must read `` `test_integrations.py` ``.

### Step 3 — `backend/README.md`

- Title line reads `# PalestrIX Core API (Phase 2 + 2b + 3 + 4 + 5 + 6 + 7)`
  → append `+ 8`.
- First paragraph: append one clause covering the integrations layer
  (Phase 8): "…and the external integrations layer (Phase 8,
  `palestrix/integrations/`): the `ExternalPlatform` contract, the Canvas
  LMS adapter (LTI 1.3, NRPS, AGS), and the grade-passback queue."
- Quickstart code block: add the missing plugin install step between
  `pip install -r requirements-dev.txt` and `python -m palestrix.seed`:
  ```
  pip install -e ../plugins/palestrix-provider-demo   # entry-point plugin used by the test suite
  ```
- "## Tests" section: change "63 tests cover …" to "71 tests cover …" and add
  the Canvas integration to the coverage list (LTI launch validation, roster
  sync identity mapping, grade passback retry/parking — see
  `backend/tests/test_integrations.py` for what the 8 tests actually cover;
  read that file's test names before writing the sentence). Also add one
  sentence: "The plugin tests require the demo plugin installed as an
  editable package (see Quickstart); without it 4 tests in `test_plugins.py`
  fail on entry-point discovery."
- Fix the dangling `.env.example` reference: either (a) create
  `backend/.env.example` listing the commonly-tuned variables with their
  defaults from `backend/palestrix/config.py` (env prefix is `PALESTRIX_`,
  so `database_url` → `PALESTRIX_DATABASE_URL`, etc. — copy the defaults
  exactly from `config.py`, do not invent values), or (b) reword the
  sentence to point at `backend/palestrix/config.py` as the authoritative
  list. Option (a) is preferred; keep every value commented out so the file
  is inert by default.

### Step 4 — `docs/public-api.md`

- "## Resource groups" code block (line ~21): add one row, keeping the
  column alignment of the block:
  ```
  /api/v1/integrations  external platforms (Canvas LMS), course links, roster sync, grade passback
  ```
- Add a new section `## Integrations surface (Phase 8)` after the sandbox
  section, in the same terse route-table style the sandbox section uses.
  Document these routes (verified against
  `backend/palestrix/api/integrations.py`; router prefix is
  `/integrations`):
  - `GET  /api/v1/integrations/platforms` — configured platform adapters.
  - `POST /api/v1/integrations/links` — link a PalestrIX course to an
    external course (teacher of that course only).
  - `GET  /api/v1/integrations/links` — links visible to the caller.
  - `DELETE /api/v1/integrations/links/{link_id}` — unlink.
  - `POST /api/v1/integrations/links/{link_id}/sync` — NRPS roster sync;
    returns matched/created identity counts.
  - `GET  /api/v1/integrations/links/{link_id}/grades` — passback queue rows
    + receipts for the link.
  - `POST /api/v1/integrations/grades/{passback_id}/retry` — re-queue a
    `failed` passback row (teacher action).
  - Note in prose that the LTI wire endpoints
    (`/integrations/canvas/jwks`, `/canvas/login`, `/canvas/launch`,
    `/canvas/deep-link`) are browser/platform-facing, excluded from the
    OpenAPI schema (`include_in_schema=False`), and documented in
    `docs/integrations-canvas-lms.md`.
  Before writing, open `backend/palestrix/api/integrations.py` and confirm
  each route's auth dependency so the doc states who may call it (they use
  `get_principal` + an internal teacher-of-course check
  `_course_teacher_or_403`).

### Step 5 — `docs/architecture.md`

- Around line 183 there is a bullet "An `ExternalPlatform` adapter layer for
  LMS integrations, Canvas first (integrations-canvas-lms.md)." Read the
  surrounding section: if it is phrased as future/planned work, rephrase to
  implemented ("Implemented in Phase 8 …" — mirror how the Phase 6/7
  sections announce themselves, e.g. line ~128 "Implemented in Phase 7
  (`backend/palestrix/tenancy/`) …"). If it is already present-tense, leave it.
- Build-order table (line ~196): no structural change needed — the table
  lists deliverables, not status. Do not add a status column.

### Step 6 — `docs/integrations-canvas-lms.md`

Read it end-to-end and check only two things: (a) every route it names
exists in `backend/palestrix/api/integrations.py`, and (b) every setting it
names exists in `backend/palestrix/config.py` (the canvas settings block is
`canvas_issuer`, `canvas_client_id`, `canvas_deployment_id`,
`canvas_auth_url`, `canvas_jwks_url`, plus `grade_passback_max_attempts` —
verify the full list by reading `config.py` lines ~133–150). Fix mismatches
only; do not restyle.

### Step 7 — Re-verify and commit

Run the Step 1 commands again if any doubt. Commit with a message like
`Phase 8: close out — docs synced to shipped state, 71 tests + build verified`.

## Edge cases a weaker model would miss

1. **The 4-test plugin trap.** A fresh clone + `pip install -r
   requirements-dev.txt` + `pytest` yields 67 passed / 4 failed. This is not
   a code bug — `tests/test_plugins.py` asserts that `provider-demo` is
   discovered through the `palestrix.plugins` entry point, which only exists
   once `plugins/palestrix-provider-demo` is pip-installed. Do not "fix" the
   tests or the discovery code; fix the README and install the package.
2. **Do not run pytest from the repo root.** The suite must run with
   `backend/` as the working directory (`cd backend && python -m pytest tests -q`);
   from the root, `tests/` doesn't resolve.
3. **A system-wide PyJWT can break `pip install` outside a venv** ("Cannot
   uninstall PyJWT 2.7.0, RECORD file not found" on Debian-managed
   Pythons). Always use a venv.
4. **The mangled link `test_[integrations.py](http://integrations.py)`** in
   README's todo list is an editor autolink artifact — don't copy it forward
   into the rewritten section.
5. **`.env.example` is referenced but absent.** If you create it, the env
   prefix is `PALESTRIX_` (see `model_config` in `config.py`) — a bare
   `DATABASE_URL=` line would be silently ignored by pydantic-settings.
6. **Keep the README's voice.** Every phase section is written as dense
   past-tense prose with inline code refs and ends with the test count.
   Match it; do not add headings, tables, or emoji.

## Acceptance criteria

- [ ] `cd backend && python -m pytest tests -q` → `71 passed` (after the
      documented quickstart, followed exactly as written, in a fresh venv).
- [ ] `npm ci && npm run build` → succeeds.
- [ ] `grep -n "Next: Phase 8" README.md` → no matches.
- [ ] `grep -n "Status: Phase 8 complete" README.md` → 1 match.
- [ ] README Phase 8 section contains "Full test suite: 71 tests pass." and
      no unchecked todo bullets.
- [ ] `grep -n "63 tests" backend/README.md` → no matches; "71 tests" present.
- [ ] `backend/README.md` quickstart contains
      `pip install -e ../plugins/palestrix-provider-demo`.
- [ ] `grep -n "integrations" docs/public-api.md` → resource-group row and a
      dedicated section both present; every documented route exists verbatim
      in `backend/palestrix/api/integrations.py`.
- [ ] Either `backend/.env.example` exists with `PALESTRIX_`-prefixed keys,
      or the reference to it in `backend/README.md` is gone.
- [ ] No `.py`/`.ts`/`.tsx` files changed (`git diff --stat` shows only
      `.md` and optionally `backend/.env.example`).

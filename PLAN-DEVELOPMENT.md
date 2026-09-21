# PalestrIX — Development plan

**For the model doing the work.** Everything below is a verified gap in this
repository as of `claude/dev-security-audit-3sg1i2` — a promise the code does
not keep, a surface with no way to reach it, or missing engineering
infrastructure. Security findings are a separate document:
[PLAN-SECURITY.md](PLAN-SECURITY.md).

Read [PLAN.md](PLAN.md) first. It is the project ledger: §5 holds the
paper-versus-code reconciliation (G-01 … G-11), §6 the study workstreams, and
§9 the progress log. **This plan does not replace it** — it covers the
engineering work PLAN.md's workstreams assume is already solid. Where an item
here maps to a ledger entry, it says so.

---

## How to work this plan

1. **One item per commit**, in the order given inside each section. Items
   across sections are independent.
2. **The build gates everything:**
   ```bash
   pytest backend/tests -q                 # currently 146 passed
   (cd sandbox-coordinator && pytest tests -q)   # currently 60 passed
   npx tsc --noEmit && npm run build
   ```
   Run `npx tsc --noEmit` and `npm run build` *serially* — run in parallel,
   the build rewrites `.next/types` underneath tsc and you get phantom
   TS6053 errors that are not real.
3. **Match the surrounding code.** This codebase writes comments that explain
   *why*, docstrings that state the contract, and tests that name the bug they
   prevent. A patch in a different voice is a patch that will be rewritten.
4. **Never let a doc drift.** `README.md` states the test count; `PLAN.md` §2
   states it twice more. If your change moves it, move all three.
5. **Append to PLAN.md §9** when an item lands.

### Priority key

| | Meaning |
| --- | --- |
| **P1** | Something is advertised and does not work, or the project cannot be verified. |
| **P2** | A real function has no way to reach it, or the contract is wrong. |
| **P3** | Quality of life for whoever maintains this next. |

---

## P1 — Broken promises and missing verification

### DEV-01 · There is no CI · new `.github/workflows/`

**What is wrong.** No `.github` directory at all. Nothing runs the 146
backend tests, the 60 coordinator tests, `tsc`, or the build on a push. Every
guarantee in this repository currently depends on a human remembering to run
four commands.

This is load-bearing for the study, not just hygiene: the paper's Table 3
closes every increment on "the whole accumulated test suite passes"
(PLAN.md **G-06**). That criterion cannot be evidenced without a run log.

**Fix.** Add `.github/workflows/ci.yml` with three jobs:

- `backend` — Python 3.11, `pip install -r backend/requirements-dev.txt`,
  then **`pip install -e plugins/palestrix-provider-demo`** (skip it and four
  plugin tests fail through no fault of the code — this is G-06, and CI
  encoding the step is what closes it), then `pytest backend/tests -q`.
- `coordinator` — `pip install -r sandbox-coordinator/requirements.txt`, then
  `pytest tests -q` in that directory.
- `frontend` — Node 22, `npm ci`, `npx tsc --noEmit`, `npm run build`.

Cache pip and npm. Then add the badge to `README.md` and resolve G-06 in
PLAN.md §5.

---

### DEV-02 · 39 of 47 academy modules have no lesson body

**What is wrong.** `academy_catalog.py` publishes four paths — SOC Analyst
(14 modules), Web Exploitation (12), Network Defense (10), Digital Forensics
(11) — and `README.md` advertises them as "content in version control, not
demo fixtures". Actual lesson files in `backend/palestrix/academy_content/`:

| Path | Modules in catalog | Lesson files |
| --- | --- | --- |
| `soc-analyst` | 14 | **8** |
| `web-exploitation` | 12 | **0** |
| `network-defense` | 10 | **0** |
| `digital-forensics` | 11 | **0** |

So three of the four advertised paths render as empty module lists. `/academy`
is a headline surface and the study's learners are meant to use it.

**Fix.** Write the missing 39 lessons as Markdown in
`backend/palestrix/academy_content/<path-slug>/NN-<slug>.md`, following the
eight existing SOC files exactly — same depth, same voice, same structure.
`academy_content_loader.py` picks them up by position; read it before writing
so the filenames bind correctly.

This is genuine content work, not scaffolding. Do it a path at a time, one
commit per path, and do not generate filler — a module with a stub body is
worse than one that is honestly absent, because the gate in `academy_gate.py`
will happily award Palestras for reading nothing.

**Verify.** Extend `backend/tests/test_academy_content.py` to assert every
catalog module resolves to a non-empty body, so the gap cannot reopen.

---

### DEV-03 · The committed OpenAPI spec does not exist

**What is wrong.** `docs/public-api.md` states: "The OpenAPI spec is committed
to the repo per release and diffed in CI so accidental breaking changes fail
the build." There is no spec file anywhere in the repository and no CI to diff
it with.

That sentence is the project's entire stated defence against breaking its own
API contract — the contract plugins and external tools consume.

**Fix.** Add a script that writes `docs/openapi.json` from
`palestrix.main.app.openapi()`, commit the current output, and add a CI step
(DEV-01) that regenerates and fails on a diff. Keep the generation
deterministic — sort keys — or the diff is noise.

**Depends on** DEV-01.

---

## P2 — Functions with no way to reach them

### DEV-04 · Webhooks and OAuth clients have no UI · `app/(app)/settings/view.tsx`

**What is wrong.** The settings page manages the profile, password, passkeys,
and API keys. It does not touch:

- `/api/v1/webhooks` — subscribe, list, view deliveries, unsubscribe. A whole
  documented subsystem with an event catalog, HMAC signatures, a delivery log,
  and (since 2026-09-21) an egress policy, reachable only by curl.
- `/api/v1/auth/clients` — create, list, revoke. Revocation was *added* on
  2026-09-21 precisely so a leaked secret could be retired; with no UI, nobody
  will.

**Fix.** Two more cards in the existing settings layout, following the
`ApiKeysCard` pattern exactly: `useApi` for the list, optimistic refresh after
mutation, secret shown exactly once on creation with the same warning copy.
For webhooks, also show the delivery log (`GET /webhooks/{id}/deliveries`) with
its status, and surface the 422 reason when a URL is refused by the egress
policy — that message is written to be read by a person.

Add the types to `lib/api/types.ts` (`WebhookOut`, `WebhookCreatedOut`,
`WebhookDeliveryOut`, `OAuthClientOut`) matching the Pydantic schemas.

---

### DEV-05 · Public profiles are advertised and unreachable

**What is wrong.** `README.md` describes `/community` as "Writeups, profiles,
community score", and `GET /api/v1/users/{handle}` serves a public profile
with a recency-decayed community score. No page calls it. `app/(app)/community/[id]/`
is the writeup detail route; there is no profile route at all, and author
handles in the writeup list are not links.

The community score is one of the four algorithms `README.md` names as
distinguishing this platform from a conventional web application. It is
currently invisible.

**Fix.** Add `app/(app)/community/u/[handle]/` rendering the profile: handle,
name, role, community score, and their published writeups. Link every author
handle in the writeup list and detail views to it.

---

### DEV-06 · Assignment submission takes its body as a query parameter · `backend/palestrix/api/courses.py`

**What is wrong.**

```python
def submit(course_id, assignment_id, ..., text: str | None = None)
```

`text` is a bare scalar on a POST, so FastAPI binds it as a **query
parameter**. A student's submission therefore travels in the URL — logged by
every proxy, kept in browser history — and is capped by URL length. Every other
write endpoint in this codebase takes a Pydantic body.

`Submission.storage_key` also exists in the model and nothing ever writes it,
so file submissions are modelled and not implemented.

**Fix.** Introduce `SubmissionIn` with a `text` field and take it as a body.
Add a separate multipart endpoint for file submissions that writes
`storage_key` through `get_storage()` — use `safe_filename` from
`palestrix/storage.py` for the client's filename, as the attachment endpoint
now does. Then wire it into the course surface.

**Breaking change.** Bump nothing — `/api/v1` is young and this endpoint has
no UI caller today (check `components/course/` before you assume that) — but
say so in `docs/public-api.md`.

---

### DEV-07 · List endpoints are unpaginated

**What is wrong.** `GET /users`, `GET /instances`, `GET /courses`,
`GET /sandbox/reports`, and `GET /labs/templates` all return every row.
`GET /community/writeups` is the only one with a `limit`, and it has no
cursor. On the study's own reference deployment — a class section's worth of
students against a term's worth of instance history, which is never deleted —
the admin console degrades steadily and then stops being usable.

**Fix.** Add `limit`/`cursor` to each, defaulting to something sane (50),
capped (200), ordered by a stable key. Return the next cursor. Update
`lib/api/hooks.ts` and the consuming views to page. Document the convention
once in `docs/public-api.md` rather than per endpoint.

---

## P3 — Maintainability

### DEV-08 · No linter or formatter is configured

No `ruff.toml`, no `pyproject.toml`, no ESLint config. Style is currently held
together by whoever wrote the file last. Add `ruff` (lint + format) for Python
and `eslint-config-next` for the frontend, configured to match the existing
style rather than reformatting the repository — then wire both into CI
(DEV-01). Fix what they flag in a **separate** commit from the config, so the
review diff is readable.

### DEV-09 · Deprecation warnings on every test run

Twelve warnings, three distinct causes:

- `HTTP_422_UNPROCESSABLE_ENTITY` → `HTTP_422_UNPROCESSABLE_CONTENT` (Starlette).
  Repository-wide rename; mechanical.
- `starlette.testclient` wanting `httpx2`.
- `anyio.abc.BlockingPortal` alias.

The last two come from pinned dependency versions. Resolve the first, pin or
filter the rest so the suite runs clean — warnings nobody reads are warnings
that hide the one that matters.

### DEV-10 · The frontend has no tests

Sixteen page routes, a typed API client, an SSE reader, and a hand-rolled
Markdown renderer, with zero test coverage. The renderer especially: it is the
platform's defence against author-supplied HTML and it is verified by nobody.

Start narrow — Vitest plus Testing Library, covering `lib/api/client.ts` error
mapping, `lib/api/stream.ts` frame parsing, `safeNext` in the login page, and
`components/ui/markdown.tsx` — rather than attempting route coverage.

### DEV-11 · `lib/mock.ts` is still imported by the landing page

`lib/api/types.ts` says the mock shapes "are retired", but
`app/(marketing)/page.tsx` still imports `provisioningSample` from it. Either
the marketing page's animated sample is legitimately static demo data — in
which case move it into that page and delete `lib/mock.ts` — or it should read
the live API. Decide, then make the comment true.

### DEV-12 · `README.md` "Branches" table is stale

It lists `claude/replan-archive-docs-4d6ahv` as "Active re-plan work"; that
branch merged in `71fbc63`. Anyone reading the README is pointed at a dead
branch. Update it, and consider whether the table should list branches at all
rather than describing the convention.

### DEV-13 · Schema migrations are ADD COLUMN only

`migrations.py` compares models against the live schema and issues
`ALTER TABLE ... ADD COLUMN`, and says plainly that anything more ships with
Alembic. Several items in [PLAN-SECURITY.md](PLAN-SECURITY.md) (SEC-01, SEC-02,
SEC-07, SEC-08) add columns and one adds a table — all still within what this
handles. The first change that needs a backfill, a rename, or a constraint
will not be. Introduce Alembic *before* that change rather than during it.

---

## Not in this plan

These are the study's own workstreams and belong to [PLAN.md](PLAN.md) §6, not
here. Do not start them from this document:

- **W1.1 — Track A performance harness** (ledger **G-01**). Does not exist.
  Blocks the evaluation milestone.
- **W1.3 — ISO/IEC 25010 instrument** (ledger **G-02**). Does not exist.
- **W5 — VirtualBox demo adapter** (ledger **G-11**). Demo path only; the
  harness must refuse to emit reference-grade output under it.

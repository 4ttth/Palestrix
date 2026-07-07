# PLAN: Global search — make the topbar search box real

**Leverage rank: 4 of 5.** The topbar on every authenticated page renders a
search input promising "Search labs, courses, writeups"
(`components/shell/topbar.tsx:26`) — and it is completely dead: no state, no
handler, no endpoint. It is the most prominent broken promise in the UI.
Everything needed to honor it already exists (typed API client, `useApi`
hook with a built-in race guard and `null`-path skip, role logic per
entity).

## Goal

`GET /api/v1/search?q=<text>` returning grouped, RBAC-filtered matches over
lab templates, courses, and published writeups (exactly what the placeholder
promises), plus a live topbar dropdown with debounce, keyboard navigation,
and routing to the matching surface.

## Files to touch

Backend:
1. `backend/palestrix/api/search.py` — new router.
2. `backend/palestrix/schemas.py` — `SearchHitOut`, `SearchOut`.
3. `backend/palestrix/main.py` — import + `include_router` (see the
   existing block importing from `.api` at line ~18 and the router
   registration list further down; mirror how `community` is wired).
4. `backend/tests/test_search.py` — new tests.
5. `docs/public-api.md` — resource-group row + short section.

Frontend:
6. `lib/api/types.ts` — the two result types.
7. `components/shell/topbar.tsx` — replace the dead `<input>` with a
   `SearchBox` component (same file or a sibling
   `components/shell/search.tsx`; sibling preferred to keep topbar small).

## Step-by-step implementation order

### Step 1 — Schemas (`schemas.py`)

Follow the file's existing pydantic style (look at `LabTemplateOut` for the
pattern):

```python
class SearchHitOut(BaseModel):
    kind: str        # "lab" | "course" | "writeup"
    id: str
    title: str
    subtitle: str    # lab: slug; course: "CODE · section"; writeup: first tag or author handle
    href: str        # frontend route, computed server-side: /labs/{id}, /courses, /community

class SearchOut(BaseModel):
    query: str
    hits: list[SearchHitOut]
```

Computing `href` server-side keeps the frontend dumb and the tests able to
pin routing.

### Step 2 — Router (`api/search.py`)

Mirror the header/imports of `api/labs.py`. Router:
`APIRouter(prefix="/search", tags=["search"])`.

```python
@router.get("", response_model=schemas.SearchOut)
def search(
    q: str = Query(min_length=2, max_length=64),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
```

Implementation details (all load-bearing):

- **Escape LIKE wildcards** before building the pattern:
  ```python
  escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
  pattern = f"%{escaped}%"
  # then: Model.title.ilike(pattern, escape="\\")
  ```
  Without this, searching `_` or `%` matches every row.
- **Per-entity visibility — copy, don't invent:**
  - Labs: all authenticated principals see all templates (that is exactly
    what `api/labs.py:list_templates` does — no filter). Match on
    `LabTemplate.title` OR `LabTemplate.slug`.
  - Courses: replicate the three-branch role logic from
    `api/courses.py:list_courses` (lines 69–84): admin/superadmin → all;
    teacher → `Course.teacher_id == principal.user_id`; student → join
    through `Enrollment` on `Enrollment.user_id == principal.user_id`.
    Apply the ilike on `Course.title` OR `Course.code` *on top of* that
    branch's query. Import `Role` from `..models`.
  - Writeups: `Writeup.published.is_(True))` only — same as
    `api/community.py:list_writeups` (line ~40). Match on `Writeup.title`.
    Do NOT search `body_md` (unbounded text scan) and do NOT include the
    author's own unpublished drafts (keeps parity with the list endpoint).
- **Limit each entity to 5 hits** (`.limit(5)`), order labs/courses/writeups
  by `created_at.desc()`. Concatenate labs → courses → writeups into
  `hits`.
- Subtitles: lab → `slug`; course → `f"{code} · {section}".rstrip(" ·")`
  (section may be empty — don't leave a trailing separator); writeup →
  first tag if `tags` is non-empty else the author's handle (fetch the
  author like `community.py` does for its `*_out` helper, or just use the
  first tag / empty string — keep it cheap).

### Step 3 — Register the router (`main.py`)

Add `search` to the `from .api import (...)` block and one
`app.include_router(search.router, prefix=API_PREFIX)`-style line — copy
whatever exact registration form the other routers use (read `main.py`
first; do not guess the helper name).

### Step 4 — Backend tests (`tests/test_search.py`)

Copy the fixture pattern from an existing test file (find the `client` /
role-header fixtures with `grep -rn "def client\|def student\|def teacher"
backend/tests/`). Seed via the API where possible (publish a writeup,
create a course) exactly like neighboring tests do. Cases:

1. Student searching a lab title substring → hit with `kind == "lab"`,
   `href == f"/labs/{id}"`.
2. Student sees an *enrolled* course by code substring; does NOT see an
   unenrolled course matching the same query.
3. Teacher sees own course, not another teacher's.
4. Unpublished writeup is invisible; after publishing, it appears.
5. `q="%"` (after URL-encoding: `?q=%25`) returns only rows whose title
   literally contains `%` — i.e. normally zero hits, not everything.
   (Note: `%` is one char — min_length=2 means use `%%` → `?q=%25%25`, or
   relax the test to `q=a%` matching nothing.)
6. Unauthenticated request → 401/403 (whatever `get_principal` yields —
   check an existing test for the expected code).
7. `q` shorter than 2 chars → 422.

Run the full suite; expect all green.

### Step 5 — Frontend types (`lib/api/types.ts`)

```ts
export type SearchHit = {
  kind: "lab" | "course" | "writeup";
  id: string;
  title: string;
  subtitle: string;
  href: string;
};
export type SearchOut = { query: string; hits: SearchHit[] };
```

Match the file's existing naming conventions (read a few neighboring types
first).

### Step 6 — `components/shell/search.tsx` (new, `"use client"`)

Replace the `<label>` block in `topbar.tsx` (lines ~19–30) with
`<SearchBox />` and build it as:

- Local state: `q` (input value), `open` (dropdown), `activeIndex`
  (keyboard highlight).
- **Debounce**: keep a `debounced` state updated 250 ms after `q` changes
  (a `useEffect` with `setTimeout` + cleanup — no external library; the
  repo has none for this).
- **Fetch through the existing hook** — this is important, it already
  solves the stale-response race via its generation counter:
  ```ts
  const { data, loading } = useApi<SearchOut>(
    debounced.trim().length >= 2
      ? `/api/v1/search?q=${encodeURIComponent(debounced.trim())}`
      : null,
  );
  ```
  `useApi` accepts `null` to skip fetching (see `lib/api/hooks.ts:6`) —
  use that instead of conditional hook calls (which break the rules of
  hooks).
- Dropdown: absolutely positioned panel under the input, grouped by kind
  with small headers (Labs / Courses / Writeups), each row rendering
  `title` + muted `subtitle`. Style with the existing tokens used in
  `topbar.tsx` (`border-border`, `bg-surface`, `text-muted`,
  `rounded-(--radius-input)`, `text-[13px]`) — the theme is locked; invent
  no new colors.
- Keyboard: ArrowDown/ArrowUp move `activeIndex` (clamped), Enter navigates
  to `hits[activeIndex].href` via `useRouter()` from `next/navigation`
  (NOT `next/router` — this is the App Router), Escape closes and blurs.
  Mouse click on a row navigates too. After navigating: close the dropdown
  and clear `q`.
- Close on outside click (a `useEffect` adding a `pointerdown` listener on
  `document`, ignoring events inside the component's ref).
- Accessibility: input keeps `aria-label="Search"`; add
  `role="listbox"`/`role="option"` + `aria-expanded` on the wrapper,
  `aria-selected` on the active row.
- Empty state: when `debounced.length >= 2 && !loading && hits.length === 0`,
  render one muted row "No matches".

### Step 7 — Docs

`docs/public-api.md`: add `/api/v1/search` to the resource-groups block and
a two-line section (query param, per-kind visibility = same as each kind's
list endpoint, 5 hits per kind).

### Step 8 — Verify

`cd backend && python -m pytest tests -q` all green; `npm run build` green;
then manually: seed (`python -m palestrix.seed`), run API + `npm run dev`,
log in as `rafaela@example.edu` / `palestrix-dev-only!`, type `tri` in the
topbar → the seeded "Log Triage" lab template should appear; Enter
navigates to its lab page.

## Edge cases a weaker model would miss

1. **LIKE wildcard injection.** `q="%"` or `q="__"` without escaping
   matches every row — with role filtering that's a data-scoping smell and
   trivially a griefing vector. Escape `%`, `_`, and `\` and pass
   `escape="\\"` to `ilike`.
2. **`ilike` is safe on both engines here** — on PostgreSQL it's native
   `ILIKE`; on SQLite SQLAlchemy emits `lower(x) LIKE lower(y)`. Do not
   hand-roll `func.lower` and do not use PostgreSQL-only full-text search;
   tests run on SQLite.
3. **Course visibility is three-way, not boolean.** Copy the exact
   admin/teacher/student branching from `list_courses`; a naive
   `teacher_id == user or enrolled` misses that admins see everything and
   teachers must NOT see other teachers' courses.
4. **Writeup drafts.** `Writeup.published` defaults to `False`; forgetting
   the filter leaks unpublished student writeups (titles can contain flag
   spoilers — that's why the list endpoint filters).
5. **Conditional hooks.** Fetch-only-when-long-enough must be expressed as
   `useApi(condition ? path : null)` — the hook was designed for this. An
   `if` around the hook call violates the rules of hooks and breaks the
   build.
6. **`next/navigation` vs `next/router`.** This is an App Router project;
   importing `useRouter` from `next/router` compiles in some setups and
   then throws at runtime.
7. **The topbar renders on every authed page and is a client component
   already** — but it currently has no state at all. Extracting `SearchBox`
   into its own file keeps the balance/streak rendering (which re-renders on
   session changes) from re-rendering on every keystroke.
8. **URL-encode the query** (`encodeURIComponent`) — `#`, `&`, `+` in a
   search string otherwise truncate or corrupt the request.
9. **`section` can be empty string** on Course — the subtitle join must not
   render "CS 3712 · ".

## Acceptance criteria

- [ ] `GET /api/v1/search?q=tri` as the seeded student returns the
      "Log Triage Under Fire"-style seeded lab hit with a `/labs/<id>` href.
- [ ] A student never receives an unenrolled course or an unpublished
      writeup in hits (tests pin both).
- [ ] `?q=a%` (encoded) returns zero hits on seeded data, not everything.
- [ ] `?q=x` (1 char) → 422; unauthenticated → 401/403.
- [ ] Each kind returns at most 5 hits.
- [ ] Backend suite fully green including the new `test_search.py`.
- [ ] `npm run build` green; typing in the topbar shows a dropdown after
      ~250 ms, ArrowDown+Enter navigates, Escape closes, clicking outside
      closes.
- [ ] The search input no longer exists as a dead element: deleting the
      network connection to the API shows the hook's error state, not a
      silent noop.
- [ ] `docs/public-api.md` lists `/api/v1/search`.

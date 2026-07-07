# PLAN: Brute-force protection on password login

**Leverage rank: 3 of 5.** PalestrIX is a *cybersecurity training* platform,
and its own `/api/v1/auth/login` accepts unlimited password guesses: no
rate limit, no lockout, no failed-attempt tracking (verified in
`backend/palestrix/api/auth.py:47-54`). CTF flag submission already has a
cooldown (`api/compete.py`), so the platform's threat model clearly cares —
auth was just never given the same treatment. Students in a hacking class
*will* point hydra at the login endpoint of their own training platform.

## Goal

Throttle failed password-login attempts per (email, client IP) with a
sliding window and a temporary lock, returning the same
`429 {"error": ..., "retry_after": n}` shape the flag cooldown already uses
(the frontend's `ApiError` label logic in `lib/api/client.ts` already
renders `retry_after` for 429s). Successful login clears the counter.
WebAuthn (passkey) ceremonies and the OAuth2 `/auth/token` endpoint get the
same guard on their failure paths.

## Files to touch

1. `backend/palestrix/models.py` — new `LoginThrottle` table.
2. `backend/palestrix/config.py` — three new settings.
3. `backend/palestrix/throttle.py` — new module: the check/record/clear logic.
4. `backend/palestrix/api/auth.py` — wire the guard into `login`,
   `webauthn_login_verify`, and `client_credentials_token`.
5. `backend/tests/test_throttle.py` — new test file.
6. `docs/public-api.md` — one paragraph in the existing "## Rate limits"
   section (line ~225).
7. `docs/install-usecase-a-baremetal.md` and
   `docs/install-usecase-b-cloud-aws.md` — add `--proxy-headers` to the
   uvicorn `ExecStart` lines (see edge case 3).

## Step-by-step implementation order

### Step 1 — Settings (`config.py`)

Add to the `Settings` class, near `flag_cooldown_seconds` (line ~46), with
comments in the file's existing style:

```python
login_max_failures: int = 5        # failed attempts allowed per window
login_window_seconds: int = 300    # sliding window for counting failures
login_lockout_seconds: int = 900   # lock length once the window is exceeded
```

(Env names become `PALESTRIX_LOGIN_MAX_FAILURES`, etc. — the prefix is
automatic.)

### Step 2 — Model (`models.py`)

Add after `WebAuthnCredential` (keep the file's declarative style —
`Mapped[...]`/`mapped_column`, `default=uid` for the pk, `utcnow` default
for datetimes):

```python
class LoginThrottle(Base):
    """Failed-authentication counter per (scope key). DB-backed so it works
    across uvicorn workers; rows are tiny and reused in place."""

    __tablename__ = "login_throttles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    scope_key: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

New *tables* are created automatically at startup by
`Base.metadata.create_all` in `main.py`'s lifespan — no change to
`migrations.py` is needed (that module only handles additive *columns* on
existing tables). Do not write an Alembic migration.

### Step 3 — The guard (`throttle.py`)

New module with three functions, all taking a `Session` (the caller owns
the transaction; commit happens with the caller's existing commit or add an
explicit `db.commit()` in `record_failure` since `login`'s failure path
otherwise never commits — see edge case 5):

```python
def check_throttle(db, scope_key: str, *, now=None) -> None
    # look up row; if locked_until is set and still in the future →
    # raise HTTPException(429, detail={"error": "throttled",
    #   "retry_after": int(seconds_remaining)})
    # if the window has expired (now - as_utc(window_start) >
    #   settings.login_window_seconds), reset failures to 0 in memory only
    #   (persist lazily on next failure).

def record_failure(db, scope_key: str, *, now=None) -> None
    # upsert the row; if window expired, restart it (failures=1,
    # window_start=now); else failures += 1.
    # if failures >= settings.login_max_failures:
    #   locked_until = now + timedelta(seconds=settings.login_lockout_seconds)
    #   failures = 0; window_start = now
    # db.commit()  — the failure path must persist even though the request
    # ends in an exception.

def clear_throttle(db, scope_key: str) -> None
    # delete the row if present; caller's subsequent commit persists it.
```

Datetime handling: import and use `as_utc` from `models.py`
(`models.py:39`) on every datetime read back from the DB — SQLite returns
naive values, PostgreSQL returns aware ones; naive-vs-aware subtraction
raises `TypeError`. Mirror how `api/compete.py:143` computes `elapsed`.

Scope key construction (one helper in the same module):

```python
def login_scope(request: Request, email: str) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"login:{ip}:{email.strip().lower()}"
```

### Step 4 — Wire into `api/auth.py`

- `login` (line 47): add `request: Request` parameter (FastAPI injects it).
  At the top: `key = login_scope(request, body.email)`;
  `check_throttle(db, key)`. In the failure branch (the existing
  `if not user or ...` block): `record_failure(db, key)` *before* raising
  the 401. After a successful password check: `clear_throttle(db, key)`
  (the endpoint currently has no commit on success — token creation doesn't
  write — so have `clear_throttle` commit its own delete).
- `webauthn_login_verify` (line 106): same pattern, keyed
  `f"webauthn:{ip}:{email.strip().lower()}"` — check at the top, record on
  the final `raise HTTPException(401, ...)` path, clear on success (it
  already commits on success at line 124, so the delete rides along if done
  before that commit — otherwise commit explicitly).
- `client_credentials_token` (line ~229): read the function first; key on
  `f"oauth:{ip}:{client_id}"`, check at top, record on invalid-secret path,
  clear on success.
- Do NOT throttle `webauthn_login_options` — it performs no secret
  verification, and both of its failure branches are already
  anti-enumeration 400s. Adding a counter there would let an attacker lock
  someone out with requests that carry no secret at all.
- Do NOT throttle `/auth/register` in this change.

### Step 5 — Tests (`backend/tests/test_throttle.py`)

Open an existing test file (e.g. `tests/test_auth.py` or whichever defines
the `client` fixture — find it via `grep -rn "def client" backend/tests/`)
and copy its fixture/imports pattern exactly. Cases:

1. **Lockout after N failures**: register a user, send
   `settings.login_max_failures` wrong-password logins → each returns 401;
   the next attempt returns **429** with `detail.error == "throttled"` and
   an integer `retry_after > 0`.
2. **Correct password while locked is still 429** (the lock is on the
   scope, not on wrongness).
3. **Success clears the counter**: 2 failures → correct login (200) → 5
   more failures allowed again before 429.
4. **Nonexistent email is throttled identically** (no enumeration): N
   failures for `ghost@example.edu` → 429, same shape.
5. **Independent scopes**: failures for user A do not lock user B.
6. **Window/lock expiry**: call the throttle functions directly with a
   `now=` far in the future (both `check_throttle` and `record_failure`
   accept `now` for exactly this) and assert the lock and window reset. Do
   not `sleep()` in tests.

Then run the whole suite: `cd backend && python -m pytest tests -q` —
expect **71 + (new tests) passed, 0 failed**. Existing tests log in many
times via fixtures, but always with correct passwords, so they must not
trip the throttle; if any existing test starts failing with 429, your
counter is counting successes — fix the guard, not the test.

### Step 6 — Docs

- `docs/public-api.md` "## Rate limits" section: add the login throttle
  (defaults: 5 failures / 5 min window / 15 min lock; 429 with
  `retry_after`; keyed per client IP + identifier).
- Both install guides run the API as
  `uvicorn palestrix.main:app --host 127.0.0.1 ... --workers 4` behind
  nginx. Add `--proxy-headers` (and
  `--forwarded-allow-ips 127.0.0.1`) to those `ExecStart` lines so
  `request.client.host` is the real client IP, not `127.0.0.1`, and note
  why in one sentence.

## Edge cases a weaker model would miss

1. **In-memory counters are wrong here.** The production runbook runs
   uvicorn with `--workers 4` — a per-process dict gives attackers 4× the
   budget and resets on every deploy. The counter must live in the DB (or
   Redis, but the DB keeps the dev/test inline path working with zero new
   infrastructure).
2. **Naive vs aware datetimes.** SQLite (dev/tests) returns naive
   datetimes even for `DateTime(timezone=True)` columns; PostgreSQL returns
   aware ones. Every comparison must go through `models.as_utc` or tests
   pass while production crashes with `TypeError: can't subtract offset-naive
   and offset-aware datetimes`. The codebase already solved this — copy
   `api/compete.py`'s cooldown arithmetic.
3. **Behind nginx everyone is 127.0.0.1.** Without `--proxy-headers` on
   uvicorn, keying on client IP makes the throttle global-per-email (fine)
   but also means one attacker's failures against `victim@x` lock the real
   victim out from a different network — that's inherent to email-keyed
   throttling and is why the key includes the IP. With `--proxy-headers`
   configured (Step 6) the IP is real. In tests, `TestClient` reports host
   `"testclient"` for every request — that's why test case 5 must vary the
   *email*, not the IP.
4. **Don't leak account existence through the throttle.** The 401 body is
   already identical for "no such user" and "wrong password"; the 429 must
   be too — throttle unknown emails exactly like known ones (test case 4
   pins this).
5. **Persisting on the failure path.** The login handler raises an
   HTTPException on failure; nothing after the raise runs, and the request's
   session is rolled back by the framework teardown in some setups. Call
   `db.commit()` inside `record_failure` before returning, or the counter
   silently never increments (tests would catch this — case 1 would see six
   401s).
6. **Don't lock on `webauthn_login_options`.** It takes no secret; counting
   it lets anyone lock any account with unauthenticated GET-shaped traffic
   (denial of service on the victim's login).
7. **`locked_until` reset semantics.** After the lock is set, reset
   `failures` to 0 — otherwise the first failure after the lock expires
   immediately re-locks (an off-by-one that turns 15 minutes into forever).
8. **Frontend already understands the error.** `lib/api/client.ts`
   `apiErrorLabel` handles 429 + `retry_after`. Do not change the frontend;
   just match the `{"error": ..., "retry_after": int}` detail shape used by
   `api/compete.py:147-150`.

## Acceptance criteria

- [ ] 6th consecutive wrong-password login (defaults) → HTTP 429, body
      detail `{"error": "throttled", "retry_after": <int > 0>}`.
- [ ] Correct password during a lock → 429 (not 200).
- [ ] Successful login resets the failure budget (verified by test).
- [ ] Unknown email gets identical 401s and identical 429 behavior as a
      known email with wrong passwords.
- [ ] `login_throttles` table appears in a fresh dev DB with no manual
      migration step (start the API once; check with sqlite3 `.tables`).
- [ ] Full suite green: `cd backend && python -m pytest tests -q` → all
      pass (71 existing + new), no existing test newly 429s.
- [ ] `docs/public-api.md` Rate limits section documents the throttle with
      the three env var names.
- [ ] Both install guides' uvicorn `ExecStart` lines include
      `--proxy-headers --forwarded-allow-ips 127.0.0.1`.
- [ ] No frontend files changed.

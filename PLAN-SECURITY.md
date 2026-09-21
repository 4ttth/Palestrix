# PalestrIX — Security remediation plan

**For the model doing the work.** Every item below is a real, verified gap in
this repository as of `claude/dev-security-audit-3sg1i2`. Nothing here is
speculative: each one names the file, says what is wrong and why it matters,
and states what "done" looks like and how to prove it.

Read [PLAN.md](PLAN.md) §9 (entry dated 2026-09-21) first — it records the
fourteen defects already closed, so you do not re-fix them. The development
backlog is a separate document: [PLAN-DEVELOPMENT.md](PLAN-DEVELOPMENT.md).

---

## How to work this plan

1. **One item per commit.** Items are independent unless a `Depends on` line
   says otherwise. Do not batch.
2. **Write the failing test first.** Every item has a *Verify* block. A fix
   with no test that would have caught the original bug is not done — this
   codebase's security rules live in tests, not in review memory.
3. **Run everything before pushing:**
   ```bash
   pytest backend/tests -q                 # must stay green, count must rise
   (cd sandbox-coordinator && pytest tests -q)
   npx tsc --noEmit && npm run build
   ```
4. **Never weaken a control to make a test pass.** If a test conflicts with a
   fix, the test encoded the old behavior — change the test and say so in the
   commit message.
5. **Update the docs in the same commit.** `docs/public-api.md`,
   `docs/rbac-matrix.md`, and `docs/sandbox-security.md` are the contract. A
   fix that leaves them describing the old behavior is half a fix.
6. **Append to PLAN.md §9** when an item lands, in the existing style.

### Severity key

| | Meaning |
| --- | --- |
| **S1** | Exploitable now by a party the platform already trusts (a student, a teacher, an LMS admin). Fix first. |
| **S2** | Requires another failure first, or the blast radius is bounded. |
| **S3** | Hardening and defence in depth. Real, not urgent. |

---

## S1 — Fix these first

### SEC-01 · Session tokens cannot be revoked · `backend/palestrix/security.py`

**What is wrong.** Session JWTs are stateless and carry no revocation handle.
There is no `jti`, no token version, and no server-side session record. The
consequences are all live today:

- Changing a password (`POST /auth/password`) does not sign out the attacker
  who stole the old one. The one action a compromised user takes to save
  themselves does nothing.
- `POST /auth/webauthn/credentials/{id}` removing a passkey likewise leaves
  every session it minted valid.
- There is no logout that actually logs out — `lib/api/session.tsx` `logout()`
  deletes the local copy, and the token stays valid for its full 12 hours.
- An admin who demotes a user gets the role change (deps.py re-reads the user)
  but cannot end that user's session.

**Fix.** Add a `token_version: int` column to `User` (default 0). Put it in
the session token claims as `tv`. In `api/deps.py`, reject a session token
whose `tv` does not match the user's current `token_version`. Increment
`token_version` on: password change, passkey removal, role change, tenant
change, and a new `POST /auth/logout-all`. Add a plain `POST /auth/logout`
that does the same for the calling user.

`migrations.py` adds the column automatically — confirm it does for an
existing SQLite database before you rely on it.

**Verify.** A test that logs in, changes the password, and asserts the *first*
token now gets 401 while the new one works. A second test for role change.

---

### SEC-02 · No way to disable an account · `backend/palestrix/models.py`, `api/users.py`

**What is wrong.** `User` has no `active`/`disabled` flag and there is no
delete endpoint. A compromised, graduated, or expelled account cannot be shut
off at all. The only lever an admin has is `PATCH /users/{id}/role`, which
does not stop authentication. `Tenant` already has `archived` — users do not.

Note the asymmetry this creates with SEC-01: even with token revocation, the
account can simply log in again.

**Fix.** Add `User.active: bool = True`. Refuse authentication for an inactive
user in **all four** credential paths in `api/deps.py` and `api/auth.py`:
password login, passkey login, API key (check the *owner*), and the
client-credentials token (check the owner). Add
`PATCH /users/{user_id}/active` under `users:manage`, with the same
`PROTECTED_ROLES` rule as `change_role` (an admin must not be able to disable
a superadmin). Deactivating must also bump `token_version` (SEC-01) so live
sessions die immediately.

**Guard against lockout:** refuse to deactivate the last active superadmin,
and refuse to deactivate yourself. Both are cheap and both are the failure
mode that gets reported as "we lost the platform".

**Verify.** A test that deactivates a student and asserts 401 on login, on a
still-held session token, and on an API key that student had created.

**Depends on** SEC-01 for the session-kill half.

---

### SEC-03 · Daily earn caps can be exceeded by concurrent requests · `backend/palestrix/gamification.py`

**What is wrong.** `award()` calls `_earned_today()` and then inserts, with
nothing between them. This is the *same* read-then-write race that let one
flag capture pay twice (fixed 2026-09-21) — that fix covered
`compete.submit_flag` only. Every other earn path is still open: module
completion, writeup publishing, and the first-blood bonus. Concurrent requests
all read the same "earned so far" and all post, so the per-source daily cap —
the platform's stated anti-farming control, in `docs/rbac-matrix.md` — does
not hold under load.

**Fix.** Wrap the cap read and the ledger insert in the existing helper:

```python
from .db import serialize_on

with serialize_on(db, "gamification.award", user_id, reason):
    ...  # _earned_today, then db.add(LedgerEntry(...))
```

`serialize_on` (added 2026-09-21, `backend/palestrix/db.py`) is a PostgreSQL
advisory lock and an in-process mutex on SQLite. Do the same for
`touch_streak`, which has the identical shape around `weeks_paid`.

**Verify.** Mirror `test_one_capture_pays_once_under_concurrent_submits` in
`backend/tests/test_compete.py`: fire concurrent module completions against a
cap and assert the total posted never exceeds it.

---

### SEC-04 · LTI launch replay protection is per-process · `backend/palestrix/integrations/__init__.py`

**What is wrong.** `claim_nonce` stores used nonces in a module-level dict.
The code comment is honest that this is per-process, but the consequence is
not mitigated anywhere: run more than one uvicorn worker — which
`hardening.py` effectively pushes sites toward, and which any real deployment
does — and a captured launch POST replays successfully against any worker
that has not seen that nonce. The state JWT stays valid for its full 10-minute
TTL, so the window is real.

**Fix.** Move the nonce store behind the database so every worker shares it.
Add a small `LtiNonce` table (`nonce` primary key, `expires_at`), claim with
an INSERT whose `IntegrityError` means "already used", and sweep expired rows
on the reaper tick (`orchestration/reaper.py` already runs every 60s and is
already the platform heartbeat). Redis is *not* required — the database is
already a hard dependency and this is a tiny, short-lived table.

**Verify.** A test that claims a nonce, clears the in-process cache, and
asserts the second claim still fails. Update the "sticky sessions" note in
`docs/integrations-canvas-lms.md`, which this fix makes unnecessary.

---

## S2 — Bounded, but real

### SEC-05 · Sandbox at-rest seal reuses one keystream · `backend/palestrix/sandbox/vault.py`

**What is wrong.** `seal()` derives a keystream from the app secret and a
fixed domain string, with **no per-object nonce**. So:

- Identical samples seal to identical ciphertext — the store leaks which
  submissions are the same file, across students and tenants.
- Any two ciphertexts XOR to the XOR of their plaintexts. A single known
  sample (EICAR, a public malware sample, a command the attacker submitted
  themselves) recovers that much of every other object.

The module docstring is honest that this exists to stop host antivirus eating
samples rather than to provide confidentiality, and
`docs/sandbox-security.md` promises "encrypted at rest" — those two statements
do not agree, and the doc is the one the study cites.

**Fix.** Version the format. Write a header `PLXS2` + a 16-byte random nonce,
derive the keystream from `secret || domain || nonce || counter`, and have
`unseal()` dispatch on the header — bytes without it are the old format and
still decrypt, so nothing already stored is lost. Better still, use
`cryptography`'s `ChaCha20Poly1305` (already a dependency via `webauthn`), and
derive the key under its own label the way `plugins/registry.py` now does
rather than reusing the raw secret.

**Verify.** A test that seals the same bytes twice and asserts the ciphertexts
differ; a test that an old-format blob still unseals; a round-trip test.
Then correct the claim in `docs/sandbox-security.md` to say exactly what the
seal does and does not provide.

---

### SEC-06 · Lab templates and courses leak across tenants · `backend/palestrix/api/labs.py`, `api/courses.py`

**What is wrong.** Two holes the 2026-09-21 tenancy pass did not reach:

- `GET /labs/templates` returns **every** template on the deployment to any
  authenticated caller — titles, slugs, and `vm_template` names from every
  class section.
- `POST /courses/{id}/enroll` (student self-enrolment) checks only that the
  course exists. A student can enrol in another section's course and then read
  its assignments. Course ids are random hex so this is not casually
  enumerable, but "hard to guess" is not an access control.

**Fix.** Scope `list_templates` the way `compete.list_events` now is: a
template is visible to its owner, to staff, and to members of the tenant whose
courses use it. Add a tenant check to `enroll` — a student joins a course in
their own tenant, or a tenant-less one. Follow the existing convention of
404-not-403 for "another section's thing".

**Verify.** Tests mirroring `test_events_are_scoped_to_the_caller_tenant` in
`backend/tests/test_compete.py`.

---

### SEC-07 · No audit trail for privileged actions · new module

**What is wrong.** Nothing records who did what. Role changes, tenant
assignment, plugin enablement (which grants scopes and runs arbitrary Python),
tenant archival, and grade edits all happen with no durable record. After an
incident there is no way to answer "who made this account a superadmin". For a
platform whose subject *is* security education, this is also a poor example.

**Fix.** Add an append-only `AuditEvent` table (actor id, action, target,
before/after summary as JSON, timestamp, principal kind). Write to it from the
privileged endpoints in `api/users.py`, `api/admin.py`, and `api/plugins.py`.
Expose `GET /admin/audit` under `infra:manage`, newest first, paginated.
Follow the `LedgerEntry` precedent: append-only, never edited.

**Verify.** A test that a role change writes exactly one audit row naming both
the actor and the target, and that the endpoint is refused to non-admins.

---

### SEC-08 · API keys never expire and leave no trace of use · `backend/palestrix/models.py`

**What is wrong.** `ApiKey` has `revoked` but no `expires_at` and no
`last_used_at`. A key minted for one assignment stays valid forever, and there
is no signal to tell a live key from a forgotten one — so nobody ever revokes
anything.

**Fix.** Add both columns. Accept an optional `expires_at` in
`ApiKeyCreateIn` (default something sane, e.g. 90 days). Reject expired keys
in `api/deps.py`. Stamp `last_used_at` on use — throttle the write to at most
once a minute per key so a busy key does not turn every request into an
UPDATE. Surface both in the settings UI (see DEV-04).

**Verify.** A test that an expired key is refused; a test that `last_used_at`
moves.

---

### SEC-09 · Flag hashes are unsalted SHA-256 · `backend/palestrix/api/compete.py`

**What is wrong.** `Challenge.flag_hash = sha256_hex(flag)`. CTF flags are
low-entropy, highly formulaic strings (`CLCTF{...}`). Anyone who reads the
database — a backup, a support dump, a SQL-injection in some future endpoint —
recovers them by dictionary attack, and the whole arena's scoring is void.
This is exactly the password-storage mistake the platform *teaches students
not to make*, which matters for an artifact that is itself the teaching
material.

**Fix.** Store a per-challenge random salt and hash with Argon2id — `security.py`
already has `hash_password`/`verify_password` and the dependency is present.
Keep the verification constant-time (it already is). Migrate: leave old
`flag_hash` rows readable by falling back to the SHA-256 path during
verification, and re-hash on the next successful match, or simply require
authors to re-enter flags and document that.

**Verify.** A test that two challenges with the same flag text store different
hashes, and that submission still works across both formats.

---

## S3 — Hardening

### SEC-10 · `emit()` validates event types with `assert` · `backend/palestrix/events.py:53`

The last `assert` used as a runtime check in the backend (the storage one was
fixed 2026-09-21). `python -O` strips it, and an unknown event type would then
be recorded and delivered instead of refused. Raise `ValueError`. One line,
plus a test.

### SEC-11 · Webhook signing secrets are stored in plaintext

`WebhookSubscription.secret` is a plaintext column. It must be recoverable to
compute the HMAC, so hashing is not an option — but it can be encrypted at
rest with the same domain-separated key derivation `plugins/registry.py` now
uses for plugin config. Reuse that code path rather than writing a second one.

### SEC-12 · Canvas JWKS is fetched on every launch

`CanvasPlatform.validate_launch` does a blocking HTTP GET to the platform
keyset per launch, with no cache, no timeout distinct from the general one,
and no negative caching. A slow or hostile keyset endpoint stalls a worker
thread per launch. Cache by `kid` with a short TTL and refresh on a miss.

### SEC-13 · No password reset flow

`app/(auth)/login/page.tsx` renders a "Forgot it?" link pointing at `#`. An
account whose password is lost and whose passkey is gone is unrecoverable
except by an admin editing the database. Either build the flow (signed,
single-use, short-TTL token by e-mail) or remove the link and document that
recovery is an administrator action — but do not ship a dead control.

### SEC-14 · Docker labs publish ports on all interfaces

`orchestration/docker.py` runs containers with `-P`, which binds published
ports to `0.0.0.0` on the host. `docker_host_address` defaults to `127.0.0.1`,
so the platform *reports* loopback while the port is in fact reachable from
anywhere that can route to the host — and the thing on that port is a
deliberately vulnerable lab. Bind explicitly to the configured address.

### SEC-15 · No secret-rotation story for `PALESTRIX_SECRET_KEY`

One secret keys session JWTs, LTI state, plugin config encryption, and the
sandbox seal. Domain separation was added for plugin config on 2026-09-21;
the rest still derive from it directly, and rotating it invalidates every
session and makes every sealed sample and encrypted config unreadable. Write
`docs/secret-rotation.md` describing the supported procedure, and consider a
`PALESTRIX_SECRET_KEY_PREVIOUS` accepted for decryption/verification only.

---

## Do not "fix" these

Documented decisions, not oversights. Changing them needs a reason beyond a
scanner's opinion:

- **Bearer token in `localStorage`** (`lib/api/client.ts`). Deliberate: it
  means no cookie, so no CSRF surface. The XSS exposure is real but the
  codebase has no HTML sink — `components/ui/markdown.tsx` builds React
  elements and never touches `dangerouslySetInnerHTML`. Revisit only together
  with a move to httpOnly cookies *and* CSRF tokens, as one change.
- **`plugins/registry.py` executing Python from `PALESTRIX_PLUGIN_PATHS`.**
  That is what a server plugin *is*. The control is that only a superadmin
  enables one and the path list is operator configuration.
- **The sandbox detonating attacker-supplied code.** The product. The controls
  are the isolated host, the throwaway VM, the air-gapped bridge, and the wall
  clock — see `docs/sandbox-security.md`.

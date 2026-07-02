# RBAC Matrix

Four roles: **Student**, **Teacher**, **Administrator**, **Superadministrator**.
Roles are strictly increasing only where the matrix says so; admins do not
automatically inherit teacher course powers, for example. Enforcement lives in
one place: FastAPI dependencies on every route (`require_role`,
`require_scope`), mirrored in the UI by hiding what a role cannot do. The UI
gate is convenience; the API gate is the security boundary.

## Matrix

Legend: Y = allowed, O = only own/enrolled resources, - = denied.

| Capability | Student | Teacher | Admin | Superadmin |
|---|---|---|---|---|
| **Learning** |
| View academy paths and modules | Y | Y | Y | Y |
| Complete modules, earn Palestras | Y | - | - | - |
| Launch labs from enrolled courses | O | Y | Y | Y |
| Extend own instance TTL (spends Palestras) | O | Y | Y | Y |
| Stop/destroy own instance | O | O | Y | Y |
| **Courses** |
| Enroll in courses | O | - | - | - |
| Create/edit courses and assignments | - | O | - | Y |
| Upload assignment files (basic) | - | Y | Y | Y |
| Publish live environments (advanced: Dockerfile, VM, TTL, tenancy) | - | Y | Y | Y |
| Grade submissions, view rosters | - | O | - | Y |
| **Community** |
| Publish writeups, comment, vote | Y | Y | Y | Y |
| Moderate community content | - | O (own course forums) | Y | Y |
| **Compete** |
| Join CTF events, submit flags | Y | - | - | - |
| Author challenges, schedule events | - | Y | Y | Y |
| Reset flags / adjust scores during an event | - | - | Y | Y |
| **Sandbox** |
| Submit samples, view own reports | Y | Y | Y | Y |
| View all sandbox reports | - | - | Y | Y |
| Change sandbox isolation config | - | - | - | Y |
| **Infrastructure** |
| View infrastructure console | - | - | Y | Y |
| Upload ISOs, build VM templates | - | - | Y | Y |
| Manage tenants and quotas | - | - | Y | Y |
| Force-reap instances | - | - | Y | Y |
| **Platform** |
| Manage users and roles | - | - | O (students, teachers) | Y |
| Manage API keys and webhooks | - | O (own integrations) | Y | Y |
| Install/enable plugins | - | - | - | Y |
| Platform settings, secrets, backups | - | - | - | Y |

## Gamification cross-cutting rules

- Only the gamification service mints or burns Palestras; every other
  service posts *requests* to it with a reason code. This keeps the ledger
  auditable and the balance rules in one file.
- Earn sources: module completion, flag capture (scaled by solve count),
  first blood bonus, writeup publication, weekly streak checkpoint.
- Spend sinks: hints, TTL extensions, cosmetic profile items (future).
- Anti-abuse: per-source daily caps, duplicate-solve detection, no earning
  from your own authored challenge, community-score decay so ranks reward
  recency, ledger immutability (corrections are new compensating entries).
- Teachers and admins have no earn path: leaderboards stay student-only.

## Implementation notes (Phase 2)

- JWT session carries `role` and `tenant`; WebAuthn (passkey) is the primary
  credential (py_webauthn server side, SimpleWebAuthn browser side).
- API keys and OAuth2 client-credentials tokens carry `scopes` that map to
  the same capabilities (see public-api.md); a key can never exceed the role
  of the account that created it.
- Every table with tenant-owned rows carries `tenant_id`; queries filter on
  it in a shared repository layer, not per-endpoint.

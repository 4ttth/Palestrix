# External Integrations: Canvas LMS (Reference Adapter)

PalestrIX integrates outward through an adapter layer, live since Phase 8
(`backend/palestrix/integrations/`). Every external platform implements one
interface, so adding Moodle or Google Classroom later follows the exact same
path as Canvas, the first target. Nothing in core references Canvas by name
outside its adapter module and its wire routes.

## The `ExternalPlatform` interface

```python
class ExternalPlatform(Protocol):
    id: str          # "canvas-lms"
    name: str
    issuer: str

    def login_redirect_url(...) -> str: ...          # OIDC initiation bounce
    def validate_launch(id_token, *, nonce) -> LaunchClaims: ...
    def fetch_roster(link) -> list[RosterEntry]: ...
    def push_grade(passback) -> str: ...             # returns the receipt
    def deep_link_response_jwt(...) -> str: ...
    def jwks(self) -> dict: ...                      # the tool keyset
```

Adapters are pure platform clients: they never touch PalestrIX tables (the
registry rows are the API's to mutate — the same split as the Phase 7
`TenantCloud` contract). The registry mirrors the provider/detonator/cloud
registries: nothing answers by default; `PALESTRIX_CANVAS_ISSUER` +
`PALESTRIX_CANVAS_CLIENT_ID` activate the Canvas adapter at startup.

## Canvas adapter

### Protocols used

| Concern | Protocol |
|---|---|
| Launch + identity | LTI 1.3 (OIDC third-party initiation, RS256 id_token against the platform keyset) |
| Grade passback | LTI Assignment and Grade Services (AGS) score publish |
| Roster | LTI Names and Role Provisioning Services (NRPS) v2 |
| Deep linking | LTI Deep Linking 2.0 (signed response JWT) |
| Service auth | OAuth2 client-credentials with a JWT client assertion signed by the tool key |

### Wire endpoints (`/api/v1/integrations/...`)

Public by protocol — the browser arrives from Canvas carrying signed
tokens, and those signatures are the authentication:

| Endpoint | Role |
|---|---|
| `GET  /canvas/jwks` | The tool keyset Canvas pins |
| `GET/POST /canvas/login` | OIDC initiation → 302 to Canvas's auth endpoint with a signed `state` carrying the nonce |
| `POST /canvas/launch` | Validates the id_token; resource launches hand the browser to the app with a session, deep-linking launches render the lab picker |
| `POST /canvas/deep-link` | Picker submission → signed `LtiDeepLinkingResponse` auto-posted back to Canvas |

Management endpoints are ordinary authenticated API (teacher-owned, same
rule as `/courses`): `POST/GET/DELETE /links`, `POST /links/{id}/sync`,
`GET /links/{id}/grades`, `POST /grades/{id}/retry`, `GET /platforms`.

### Setup (Canvas admin side)

1. Create an LTI Developer Key in Canvas (Manual entry):
   - Redirect URI / Target link URI:
     `https://palestrix.example.edu/api/v1/integrations/canvas/launch`
   - OIDC initiation URL:
     `https://palestrix.example.edu/api/v1/integrations/canvas/login`
   - Public JWK URL:
     `https://palestrix.example.edu/api/v1/integrations/canvas/jwks`
2. Enable AGS (scores), NRPS (names/roles), and the Assignment/Link
   selection placements.
3. Add the custom field `canvas_course_id=$Canvas.course.id` — it is how a
   launch finds the teacher's course link before the LTI context id has
   been learned.
4. In PalestrIX, set `PALESTRIX_CANVAS_ISSUER`, `_CLIENT_ID`, optionally
   `_DEPLOYMENT_ID`, and the tool signing key `_TOOL_PRIVATE_KEY` (the boot
   guard refuses an empty key in production: Canvas pins the published
   JWKS, and an ephemeral key rotates on every restart). Instructure-cloud
   sites override `_AUTH_URL`, `_JWKS_URL`, `_TOKEN_URL` to the SSO host.

The step-by-step walkthrough with the exact Canvas screens lives in
[install-usecase-a-baremetal.md §13](install-usecase-a-baremetal.md#13-canvas-lms-optional).

## The three flows

**Roster / enrollment sync.** A teacher links their PalestrIX course to a
Canvas course (by Canvas course id, from the course manager's Canvas panel)
and runs a sync — on demand from the panel, or scheduled by hitting
`POST /links/{id}/sync` from cron with an API key. The adapter pulls NRPS
membership: new students get pre-provisioned accounts (no password; they
claim the account through their first launch, then enroll a passkey),
drops are unenrolled — but only students this platform mapped in the first
place; locally added students are never touched. PalestrIX stays the source
of truth for handles; Canvas for enrollment. `roster.synced` fires on the
event bus with the counts.

**Lab deep-linking.** In the Canvas assignment editor the teacher picks the
PalestrIX placement, gets the lab picker (their published templates), and
selects one; the signed response JWT hands Canvas a resource link with the
template in its custom parameters and a `lineItem` so Canvas creates the
grade column. Students clicking the assignment go through the LTI 1.3
launch: PalestrIX validates the id_token, maps the Canvas identity, and
lands them in the app with a session already established.

**Grade passback.** When a teacher grades a submission in PalestrIX, the
`grade.posted` event queues a passback row for every linked platform that
can receive it: the student is identity-mapped and the assignment's grade
column is bound (the first launch of the content link binds the AGS line
item — one launch by anyone in the class binds it for everyone). Delivery
is at-least-once with exponential backoff (`2^attempts` minutes, up to
`PALESTRIX_GRADE_PASSBACK_MAX_ATTEMPTS`), retried on the reaper heartbeat;
exhausted rows park as `failed` in the teacher's course panel with a
one-click retry, never silently. Receipts are kept; `grade.delivered`
fires on success.

## Identity mapping rules

- Mapping key: LTI `sub` claim + issuer, stored as an `ExternalIdentity`
  row on the PalestrIX account.
- First launch with an unmapped Canvas identity: if the asserted e-mail
  matches an existing account (roster sync pre-provisions them), the
  launch claims it; otherwise the launch lands on an "ask your teacher to
  sync the roster" page. No silent account creation from a launch.
- Launch replay is refused: the OIDC nonce is single-use (per-process; a
  multi-replica edge needs sticky sessions on the launch path).
- Unlinking a course keeps identities and receipts; grades already passed
  back are never retracted automatically.

## Failure and privacy posture

- Canvas outages degrade gracefully: labs keep working, grades queue and
  retry on the heartbeat, failures surface in the course panel.
- The adapter stores the minimum: external ids, line-item URLs, receipts.
  No Canvas tokens in application tables — service tokens are minted per
  call from a JWT client assertion and discarded.
- Roster members without an e-mail cannot be keyed to an account and are
  reported as `skipped` in the sync result rather than guessed at.

## Adding the next platform

Implement `ExternalPlatform`, register it in
`activate_configured_platforms()`, and ship contract tests against a mocked
platform (`backend/tests/test_integrations.py` is the worked example: JWKS,
launch validation, roster sync, grade passback with retry, deep linking —
all against `httpx.MockTransport`). The management surface (links, sync,
grade queue) is platform-agnostic and comes for free.

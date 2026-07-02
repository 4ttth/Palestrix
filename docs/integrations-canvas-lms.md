# External Integrations: Canvas LMS (Reference Adapter)

PalestrIX integrates outward through an adapter layer. Every external
platform implements one interface, so adding Moodle or Google Classroom
later follows the exact same path as Canvas, the first target.

## The `ExternalPlatform` interface

```python
class ExternalPlatform(Protocol):
    id: str                                   # "canvas-lms"

    def auth(self, config: PlatformConfig) -> PlatformSession: ...
    def fetch_roster(self, course_ref: str) -> list[ExternalUser]: ...
    def push_grade(self, link: GradeLink, score: Score) -> GradeReceipt: ...
    def resolve_content_link(self, launch: ContentLaunch) -> ContentTarget: ...
```

Four capabilities, deliberately minimal: authenticate, read a roster, write
a grade, deep-link content. Anything an adapter cannot support it declares
unsupported, and the UI hides the feature for that platform.

## Canvas adapter

### Protocols used

| Concern | Protocol |
|---|---|
| Launch + identity | LTI 1.3 (OIDC launch flow, platform keyset) |
| Grade passback | LTI Assignment and Grade Services (AGS) |
| Roster | LTI Names and Role Provisioning Services (NRPS), Canvas REST as fallback |
| Deep linking | LTI Deep Linking 2.0 |
| Extra data (sections, terms) | Canvas REST API with a scoped developer key |

### Setup (Canvas admin side)

1. Create an LTI Developer Key in Canvas: redirect URI
   `https://palestrix.example.edu/api/v1/integrations/canvas/launch`,
   JWKS URL `https://palestrix.example.edu/api/v1/integrations/canvas/jwks`.
2. Enable AGS, NRPS, and Deep Linking placements (assignment selection,
   course navigation).
3. Optionally create a REST developer key scoped to read sections/terms.
4. In PalestrIX (superadmin settings), paste the client id, deployment id,
   and Canvas issuer URL; secrets go to the secret store.

### The three flows

**Roster / enrollment sync.** A teacher links a PalestrIX course to a Canvas
course. Nightly (and on demand) the adapter pulls NRPS membership: new
students get pre-provisioned accounts (they claim them with a passkey on
first launch), drops are unenrolled. PalestrIX stays the source of truth for
handles; Canvas stays the source of truth for enrollment.

**Lab deep-linking.** In the Canvas assignment editor, the teacher picks
"PalestrIX lab" (Deep Linking placement), selects a published lab template,
and Canvas stores the content link. Students clicking the assignment go
through the LTI 1.3 launch: PalestrIX validates the id_token, maps the
Canvas user to the PalestrIX account, and drops them directly into the lab
view with an instance request already queued.

**Grade passback.** When a teacher grades a submission in PalestrIX (or an
auto-graded flag assignment completes), the `grade.posted` event triggers
the adapter, which posts the score to the AGS line item Canvas created with
the content link. Receipts are stored; failures retry with backoff and
surface in the teacher's course view, never silently.

## Identity mapping rules

- Mapping key: LTI `sub` claim + issuer, stored on the PalestrIX account.
- First launch with an unmapped Canvas identity: if the email matches a
  pre-provisioned roster account, claim it (passkey enrollment); otherwise
  the launch lands on a "ask your teacher to sync the roster" page. No
  silent account creation from a launch.
- Unlinking requires the teacher to re-run a sync; grades already passed
  back are never retracted automatically.

## Failure and privacy posture

- Canvas outages degrade gracefully: labs keep working, grades queue.
- The adapter stores the minimum: external ids, line-item ids, receipts.
  No Canvas tokens in application tables; they live in the secret store.
- All adapter traffic is logged with request ids for the practicum's audit
  requirements.

## Adding the next platform

Implement `ExternalPlatform`, register it in the adapter registry, add a
settings panel section, and ship contract tests against the interface. The
Canvas adapter is the worked example; nothing in core references Canvas by
name outside its adapter package.

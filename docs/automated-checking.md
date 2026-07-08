# Automated Checking (Grading)

Rubric-based autograding for live lab environments. A teacher attaches a
grading **scheme** to a lab template; every student instance of that
template is scored against the rubric — automatically at the first of
hand-in, stop, destroy, or TTL expiry — and the result posts into the
course gradebook and rides the existing Canvas grade-passback path.

Two rubric sources share one checker:

- **`diff`** — the teacher publishes an *unfinished* system as the lab, and
  uploads the *finished* system as a reference. The checker diffs the two,
  groups every difference into a named objective (SSH, MOTD, users, …), and
  the teacher weights each objective. Students harden the box to match; each
  objective they get right pays its weight.
- **`winfile`** — for templates published without a reference system
  (a Proxmox VM template, or a Dockerfile the teacher would rather not
  diff), the server mints randomized *win files*. The teacher plants them in
  the image; a student proves an objective by finding and executing one.

Implemented in `backend/palestrix/grading/`, following the same
registry/contract split as Phases 4/6/7: the checker never touches a
student's box directly — it goes through the instance provider's optional
`read_files` probe, so Docker, Proxmox, and future providers each decide how
their systems are inspected.

## Roles

Grading schemes are teacher-owned, exactly like the lab templates they
attach to (`courses:write` + template ownership; superadmin override). See
[rbac-matrix.md](rbac-matrix.md). Students never see the grading surface;
their only window is the student-safe rubric on their own lab
(`GET /instances/{id}/grading` — objective titles and weights, never file
paths, marker locations, or expected hashes).

## Teacher workflow — diff mode

1. **Publish the unfinished system** as a normal container lab template
   (`POST /labs/templates` with the Dockerfile/compose archive). This is
   what students launch and configure. Diff mode requires a container
   template with a build archive; VM templates use winfile mode.
2. **Create the scheme** with the finished system's archive:

   ```
   POST /api/v1/grading/schemes   (multipart)
     lab_template_id=<template id>
     kind=diff
     finished=@finished-system.tar.gz
   ```

   The checker diffs the finished archive against the template's own
   (unfinished) archive. Archive layout mirrors the runtime filesystem —
   files sit at the absolute paths they occupy on the running system (the
   Dockerfile and compose files are ignored as build context). Every added,
   modified, or removed file is grouped into an objective by a topic
   classifier: `/etc/ssh/*` → **SSH configuration**, `motd`/`/etc/issue` →
   **MOTD**, `/etc/passwd|shadow` → **User accounts**, sudoers, cron,
   firewall, web server, network, PAM, services, and a per-file fallback for
   anything unrecognized. Identical systems are rejected (nothing to grade).

3. **Weight the objectives** — the response lists each objective with a
   `weight_percent` of 0. Set them:

   ```
   PATCH /api/v1/grading/schemes/{id}/weights
     {"weights": {"<item id>": 50, "<item id>": 30, "<item id>": 20}}
   ```

4. **Publish** — weights must tally to **exactly 100%** (the whole grade is
   accounted for, nothing double-counted); a short or over tally is refused
   and names the total. Publishing locks the rubric and turns grading on:

   ```
   POST /api/v1/grading/schemes/{id}/publish
   ```

An objective passes only when **every** file expectation under it matches:
a `present` file must hash-match the finished system, and a `removed` file
must actually be gone. Partial edits within an objective earn nothing for
that objective — but each objective is independent, so a student who nails
SSH and nothing else earns exactly SSH's weight.

## Teacher workflow — win files

1. **Publish the template** (VM or container — no reference archive needed).
2. **Create the scheme**, asking for N randomized scripts (1–10):

   ```
   POST /api/v1/grading/schemes  (multipart)
     lab_template_id=<template id>
     kind=winfile
     winfiles=3
   ```

   Each script is an objective. Download them
   (`GET /grading/schemes/{id}/winfiles/{item_id}`), and plant each one
   somewhere in the image before students launch. Executing a script once
   writes a random token into a random marker directory (both regenerated on
   every generation — a re-`POST …/regenerate` invalidates every previously
   downloaded script). The student must *find and run* each file; the checker
   verifies the marker token, and neither the marker path nor the token
   appears in the student's grading view, so a win is recorded only by
   locating the artifact on the system and running it.

3. **Weight and publish** as above (tally to 100%).

Because the token and marker path are random per scheme and never exposed to
students, "find the win file and run it" is the whole objective — copying a
classmate's marker doesn't help (the path is unguessable and the token is
unique per scheme). One honest limit of an offline checker: a student who
locates a script can also read its source and see the token it writes, so
win files reward *finding and running* the artifact rather than proving
execution cryptographically. A teacher who wants a stronger guarantee writes
scripts with real side effects (start a service, drop a file the next
objective depends on) so a hand-copied marker isn't enough.

## When grading runs

The running box is the evidence, so grading always happens **while the
instance is still running**, at the first of:

| Trigger    | Who        | Endpoint / event                                  |
| ---------- | ---------- | ------------------------------------------------- |
| `student`  | the owner  | `POST /instances/{id}/grade` (explicit hand-in)   |
| `stop`     | owner/admin| `POST /instances/{id}/stop`                       |
| `destroy`  | owner/admin| `DELETE /instances/{id}`                          |
| `reaper`   | the system | TTL expiry — time up is a hand-in                 |

The explicit hand-in is re-runnable while the instance is running; the
**latest** check is the grade of record, so a student can iterate
(check → fix → re-check) until they stop or run out of time. The lifecycle
triggers (stop/destroy/reaper) grade only once, and only if the student
never handed in — they never overwrite a better explicit result, and they
never block teardown: a checker failure at stop/destroy/reaper is logged to
the instance and swallowed, while an explicit hand-in surfaces the failure
as a `409` so the student knows to retry.

## How a grade reaches the gradebook

`run_checks` records a `GradeCheck` (the student-safe breakdown plus the
summed `total_percent`). `write_back` then posts that percentage into the
student's `Submission` for every `lab` assignment that targets this template
in a course they're enrolled in — creating the submission if the student
hadn't otherwise submitted — and emits `grade.posted`, which the Phase 8
integration layer turns into a Canvas AGS passback exactly as a manual grade
does. It also emits `grading.result.ready` on the webhook/event bus. A
teacher can still override any automated grade by hand in the gradebook
(`POST …/submissions/{id}/grade`); the manual post is authoritative and
re-queues its own passback.

The teacher's **gradebook**
(`GET /courses/{course}/assignments/{assignment}/submissions`) returns every
submission with its grade of record and, for auto-graded rows, the
objective-by-objective breakdown behind it.

## Provider file inspection

The checker reads a student's system through an optional provider method:

```python
read_files(db, instance, paths) -> {path: sha256_hex | None}
```

- **Docker** (`orchestration/docker.py`): one `docker exec … sha256sum` per
  path inside the live container; a missing file reads as `None`.
- **Proxmox** (`orchestration/proxmox.py`): the QEMU guest agent's
  `file-read` (the same agent that reports the VM's address), hashed
  locally; an unreadable/missing file reads as `None`.
- **Demo** (`providers.py`): the development/test provider has no real
  filesystem, so every path honestly reads as `None`. A graded demo lab
  therefore scores by *absence* — "remove the insecure file" objectives pass
  and "configure X" objectives fail — it never fabricates a pass.

A provider that doesn't implement `read_files` (older plugin providers)
makes its templates ungradeable: an explicit hand-in returns `409` and the
lifecycle triggers skip grading with a logged note. `None` is a first-class
answer (the file isn't there), never an error — errors are reserved for "the
box is gone" (container/VM not found), which raises `GradingUnavailable`.

## Data model

`backend/palestrix/models.py`:

- **`GradingScheme`** — one per lab template; `kind` (`diff`/`winfile`),
  `status` (`draft`/`published`), the finished-archive key (diff) or random
  `marker_dir` (winfile), and the diff `analysis` summary.
- **`RubricItem`** — one objective: `key`, `title`, `weight_percent`, and
  the server-only `checks` (diff: a list of `{path, sha256, present}`
  file expectations; winfile: `{marker, token_sha256}`). Win scripts are
  stored in the `lab-archives` bucket under `grading/{scheme}/`.
- **`GradeCheck`** — one grading run of one instance: the student-safe
  `items` breakdown, `total_percent`, the `trigger`, and the `submission_id`
  it wrote to.

Startup migrations (`migrations.py`) add the new tables and the
`LabTemplateOut.owner_id` column automatically; the model tables are created
by `Base.metadata.create_all` on first boot.

## Endpoint summary

```
POST   /api/v1/grading/schemes                       create (diff|winfile)
GET    /api/v1/grading/schemes[?lab_template_id=]     list your schemes
GET    /api/v1/grading/schemes/{id}                   one scheme + rubric
PATCH  /api/v1/grading/schemes/{id}/weights           set weights (draft only)
POST   /api/v1/grading/schemes/{id}/publish           lock; requires tally=100
POST   /api/v1/grading/schemes/{id}/regenerate        re-randomize win files
GET    /api/v1/grading/schemes/{id}/winfiles/{item}   download a win script
DELETE /api/v1/grading/schemes/{id}                   discard a draft

POST   /api/v1/instances/{id}/grade                   student hand-in (re-runnable)
GET    /api/v1/instances/{id}/grading                 student-safe rubric + result

GET    /api/v1/courses/{c}/assignments/{a}/submissions  teacher gradebook
```

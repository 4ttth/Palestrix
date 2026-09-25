# Roadmap: teacher authoring, courses, and the student dashboard

Design captured 2026-09-25 from a review of the live platform; turned into an
**execution plan** the same day by reading the code it has to change. Nothing
here is built yet.

**If you are the model building this:** read §0 first, then work the
milestones in §4 in order. Each milestone is one reviewable PR-sized unit with
its own files, tests, and "done when". Do not start a milestone until the
previous one's tests pass. Update [PLAN.md](../PLAN.md)'s progress log when a
milestone lands, and tick its box in §4.

Three threads that share a data model, in build order:

1. **Courses & assignments redesign** (highest day-to-day value) — M1–M3
2. **Student dashboard** (small, depends on 1) — M4
3. **Teacher VM-diff lab authoring** (largest, most novel) — M5–M9

---

## 0. Ground rules for whoever builds this

These are facts about the codebase that constrain every milestone. Each was
verified against the code on 2026-09-25; re-verify before trusting.

| Constraint | Where | What it means for this work |
| --- | --- | --- |
| **Schema changes are additive-only.** `migrations.upgrade()` issues `ADD COLUMN` for missing columns; `create_all` creates new tables. No drops, renames, or rewrites. | `backend/palestrix/migrations.py` | New tables are free. New columns must be nullable or carry a scalar default. **Never drop `Assignment.storage_key`, `Assignment.kind`, `Submission.grade`, or `Submission.text`** — keep them and read them as legacy. Anything needing a data rewrite is a lazy read-time shim, not a migration. |
| **Object storage has no streaming read.** `Storage.get()` returns `bytes`. | `backend/palestrix/storage.py` | A 200 MB download through `get()` holds 200 MB per request per worker. M1 adds `Storage.open()` (a readable stream) to both backends before any download route exists. |
| **Buckets are a fixed tuple.** | `storage.BUCKETS` | Course files currently land in `lab-archives` (`upload_assignment_file`). Add a `course-files` bucket; `MinioStorage.__init__` creates missing buckets at startup, `LocalStorage` mkdirs them. |
| **One submission per (assignment, user)**, and `submit` 409s on a second. | `models.Submission` unique constraint; `api/courses.py::submit` | Per-question answering needs a draft → turned-in lifecycle on the *same* row, not more rows. |
| **Lab autograde writes `Submission.grade` directly** for every `kind == "lab"` assignment bound to the template. | `grading/__init__.py::write_back` | Must change to write the lab question's answer and recompute the total (M2). Canvas passback reads `Submission.grade` (0–100) — keep that column as the computed total so passback keeps working unchanged. |
| **A published rubric must total exactly 100.** | `api/grading.py::publish_scheme`, `set_weights` | The lab-plus-quiz split in §3 needs a scheme that totals *less* than 100. Resolved in §2 D3 by a `target_percent` column, not by relaxing the rule. |
| **The backend reaches Proxmox only through its HTTP API.** It has no shell on the PVE node. | `orchestration/proxmox.py` | `virt-diff` (which the first draft of this spec chose) runs on the hypervisor host against a disk — the API cannot run it. §2 D1 replaces it with an in-guest manifest over the QEMU guest agent, the same channel `read_files` already uses. |
| **Proxmox `diff` schemes are container-only today**; VM templates use `winfile`. | `api/grading.py::create_scheme` | VM-diff authoring is a new scheme source, not an extension of the tar-archive diff. It still produces the same `GradingScheme` + `RubricItem` rows. |
| **Tests mock Proxmox with `httpx.MockTransport`.** | `backend/tests/test_orchestration.py::_proxmox_mock` | Every new provider call (snapshot, rollback, agent exec, clone-from-snapshot, template convert) gets a mock route and a test. No test ever needs a real cluster. |
| **The frontend has no test runner or linter**, only `next build` (which type-checks). | `package.json` | Frontend "done when" = `npm run build` passes and the flow was clicked through against a seeded backend (`python -m palestrix.seed`). |
| **Markdown renders through React elements only**; no raw HTML reaches the DOM. | `components/ui/markdown.tsx` | Store rich content as Markdown (`body_md`), never HTML. The editor serialises to Markdown. This keeps the existing XSS guarantee for free. |
| Backend baseline | `pytest backend/tests -q` | Run it before M1 and record the count. Every milestone ends with the whole suite green (PLAN.md's increment rule). Remember `pip install -e plugins/palestrix-provider-demo` first. |

---

## 1. What exists today (the gaps this closes)

`api/courses.py` has create / list / roster / enrol / attach / gradebook /
submit / grade, plus edit / close / archive / delete with a lifecycle
(`ASSIGNMENT_STATUSES = ("open", "closed", "archived")`). An assignment carries
one file (`storage_key`) or a `lab_template_id`. The review surfaced:

- **A published file assignment is a dead end.** One attachment, no content
  around it, no way to say how it is graded.
- **Students cannot open the uploaded file.** `upload_assignment_file` stores
  it; no student-facing download route exists.
- **"quiz" is undefined.** The `kind` enum has it; nothing reads or renders it.
- **Grading is a single manual 0–100** per submission, except auto-graded labs.
- **Labs are not launchable from a course.** A `lab` assignment names a template
  but the course view has no launch affordance.
- **The student dashboard launches labs** (`LaunchPanel` in
  `app/(app)/dashboard/view.tsx`) instead of showing what is due.
- **Lab rubrics come only from uploaded archives or win files.** A teacher
  cannot build a VM lab by doing it.

---

## 2. Decisions (settled — build to these)

The first draft left three open questions and one approach that cannot work
against this architecture. These are the answers. Change one only by editing
this section first.

**D1 — File diff is an in-guest manifest over the guest agent, not `virt-diff`.**
The API has no host shell (§0). At each capture the backend runs one command in
the authoring VM through the QEMU guest agent (`agent/exec` +
`agent/exec-status`): a fixed script, shipped in the authoring template at
`/usr/local/sbin/palestrix-manifest`, that walks the filesystem with
`find / -xdev -type f` (excluding the noise list below), and prints
`sha256  size  path` per file. The two manifests are diffed server-side into
added / changed / deleted. Text content for display is fetched with the
existing `agent/file-read` path, capped at 64 KB per file.
Noise excluded by the script *and* re-filtered server-side:
`/proc /sys /dev /run /tmp /var/tmp /var/cache /var/log /var/lib/apt
/var/lib/dpkg /var/lib/systemd /var/backups /root/.cache /home/*/.cache
/home/*/.bash_history /root/.bash_history /etc/ld.so.cache /boot`, anything
under the audit log directory, and the machine-id / SSH host key files.

**D2 — Commands come from `auditd`, read back the same way.**
The authoring template (and every student template for a lab with command
items) ships `auditd` with an `execve` rule keyed `palestrix`:
`-a always,exit -F arch=b64 -S execve -F auid>=1000 -F auid!=-1 -k palestrix`.
`auid>=1000` limits it to logged-in humans, not daemons. The backend reads the
log with `agent/exec` running `ausearch -k palestrix -i --format text` (or
`--format csv` if available on Debian 12's audit 3.0.9; confirm at build) and
parses `argv` per event. Bash history is not used — it is unflushed until
logout, editable, and loses pipelines.
The `PROMPT_COMMAND` alternative in the first draft is dropped: it misses
non-interactive execution and anything run through `sh -c`.

**D3 — Lab + quiz share one assignment; percentages are "points of the
assignment".** Quiz questions reuse the §3 `AssignmentQuestion` model — no
lab-only quiz concept. The teacher sees one flat table (lab rubric items and
questions together) that must total 100. Stored as:
- `GradingScheme.target_percent` (new, default `100`). An authored scheme's
  items total `target_percent`; `publish_scheme`'s rule becomes
  `total == scheme.target_percent`. Existing schemes are all 100 — unchanged.
- The lab question on the assignment has `weight_percent == target_percent`.
- The lab question's award is `GradeCheck.total_percent` directly (it is
  already "passed weights summed", i.e. out of `target_percent`). No scaling,
  no rounding.
- Academy bindings (`academy_gate.py:86-94` compares the best
  `GradeCheck.total_percent` to `pass_percent`) must normalise to
  `total_percent * 100 // target_percent`, so an academy-bound lab with
  `target_percent < 100` is scored as a fraction of its own total.

**D4 — Command matching is argv-aware, not exact-line.**
A command rubric item stores `{"argv": ["ping", "192.168.1.1"], "match": "subset"}`.
An observed command passes when its program basename equals `argv[0]`'s basename
and every remaining token in the item's `argv` appears in the observed argv, in
order, with other tokens allowed between them. So `ping -c1 192.168.1.1`
satisfies `ping 192.168.1.1`. The teacher can edit the token list in the
rubric table (drop a token to loosen, add a flag to tighten), and can switch
an item to `"match": "exact"`. Pipelines appear as separate execve events,
so `cat x | grep y` yields two candidate items; that is correct.

**D5 — Authoring VM base is Debian 12, CLI-first.** A new golden template
`debian12-author`, built from the `debian12-min` recipe in
[lab-vm-templates.md](lab-vm-templates.md) plus `auditd`, the manifest script,
and the audit rule. GUI (noVNC) authoring works for free because `access_mode`
already supports `gui`, but a desktop authoring image is out of scope.

**D6 — Idle means "no authoring heartbeat and no new audit events".**
The authoring page posts a heartbeat every 5 minutes while open; the server
also treats a growing audit log as activity. 12 h without either → snapshot
`idle-<ts>`, then `status/stop`. Resume = start the VM (its disk is intact;
the snapshot is the safety net if the stop corrupts anything, and is pruned
after a successful resume). Never destroy an authoring VM on a timer.

**D7 — The student's box must not give the student root** for any lab with
command items, or the audit log is forgeable. The template recipe sets up the
cloud-init user `student` **without** sudo (Debian cloud images grant the
default user passwordless sudo — override it with
`--cicustom`/a `users:` block, `sudo: false`). File-only rubrics are unaffected.
Document this in lab-vm-templates.md in M6 and refuse to publish a scheme with
command items against a template not flagged `audited` (see M6).

**D8 — WYSIWYG = TipTap with Markdown as the stored form**, loaded only on the
teacher's edit route (`next/dynamic`, `ssr: false`) so students never download
it. Packages: `@tiptap/react`, `@tiptap/starter-kit`, `tiptap-markdown`. The
"Markdown" toggle swaps to a plain `<textarea>` over the same string. If the
route's JS grows by more than ~150 KB gzip, fall back to textarea + toolbar
buttons that insert Markdown + live preview via `components/ui/markdown.tsx`.
Measure with `next build` output.

---

## 3. Target design

### 3.1 Courses: the assignment as a page, Canvas-style

**Student:** Courses → course → **Open assignments** (archived hidden — keep
that) → an **assignment page**: teacher content, every attachment
(downloadable), an inline **Launch** for a bound lab with its connection info,
and the questions — one screen. They answer questions in any order (saved as a
draft), then **Turn in**. Autograded parts (lab, choice) score on turn-in;
manual parts wait for the teacher.

**Teacher:** author content (WYSIWYG ↔ Markdown), attach files (many, ≤200 MB
each), add questions (text / file / lab / choice), each graded or ungraded with
a weight; graded weights total 100. Publish; edit freely afterwards.

### 3.2 Data model

New tables (created by `create_all`; nothing to migrate):

```python
class AssignmentAttachment(Base):            # many per assignment
    __tablename__ = "assignment_attachments"
    id, assignment_id (FK, index), storage_key (String 512),
    filename (String 256), size (Integer), content_type (String 128),
    position (Integer, default 0), created_at

class AssignmentQuestion(Base):
    __tablename__ = "assignment_questions"
    id, assignment_id (FK, index), position (Integer),
    kind (String 16)            # text|file|lab|choice
    prompt_md (Text, default "")
    weight_percent (Integer, default 0)
    graded (Boolean, default True)
    lab_template_id (FK lab_templates, nullable)   # kind == lab
    choices (JSON, default list)   # kind == choice: [{"id","label"}]
    answer_key (JSON, default dict) # kind == choice: {"correct": ["id",...]}
                                    # never serialised to students

class SubmissionAnswer(Base):
    __tablename__ = "submission_answers"
    __table_args__ = (UniqueConstraint("submission_id", "question_id"),)
    id, submission_id (FK, index), question_id (FK, index),
    text (Text, nullable), storage_key (String 512, nullable),
    filename (String 256, nullable), choice_ids (JSON, nullable),
    instance_id (FK instances, nullable), grade_check_id (FK, nullable),
    awarded_percent (Integer, nullable),   # None = not yet graded
    feedback (Text, nullable), updated_at
```

New columns (additive, all nullable or defaulted):

- `Assignment.body_md: Text, default ""`
- `Submission.status: String(16), default "submitted"` — `draft|submitted`.
  Default `"submitted"` so every existing row reads as turned in.
- `Submission.turned_in_at: DateTime, nullable` (the old `submitted_at` stays
  as "first saved").
- `GradingScheme.target_percent: Integer, default 100` (D3).
- `GradingScheme.source: String(16), default "upload"` — `upload|authored`.
- `LabTemplate.audited: Boolean, default False` (D7).

**Legacy shims (read-time, no data rewrite):**
- An assignment with `storage_key` set and no attachment rows presents that key
  as one attachment (`filename = basename(storage_key)`).
- An assignment with no question rows presents one *virtual* question derived
  from `kind`: `lab` → a lab question at 100 bound to `lab_template_id`;
  `file`/`writeup` → a file question at 100; `quiz` → a text question at 100.
  The first time a teacher saves questions, real rows replace the virtual one.
- `Submission.grade` remains the authoritative 0–100 total (gradebook,
  Canvas passback). It is **recomputed** from answers whenever an answer is
  graded; for a legacy submission with no answers, it is left as is.

**Grade computation** (one function, `courses_grading.recompute(submission)`):
`grade = sum(awarded_percent for graded questions)` when every graded question
has an award; otherwise `grade = None` (partially graded) and the gradebook
shows the partial sum as "provisional". Ungraded questions never count.
Weight validation — share one validator with the rubric rule:
`validate_weights(total, target=100)` in a small module both
`api/grading.py` and the new question endpoint import.

### 3.3 Endpoints

All under `/api/v1/courses/{course_id}/assignments/{assignment_id}`. Student
access requires enrolment; teacher access requires `_require_course_teacher`.

| Method & path | Who | Does |
| --- | --- | --- |
| `GET …` | enrolled student, teacher | Page payload: assignment, `body_md`, attachments (id, filename, size, download path), questions (**`answer_key` stripped for students**), the caller's submission + answers, and for each lab question the caller's live instance (if any) for that template. |
| `POST …/attachments` | teacher | Multipart, many files per request; each ≤ `PALESTRIX_COURSE_FILE_MAX_MB` (default 200) else 413. Stored at `course-files/{course_id}/{assignment_id}/{attachment_id}/{filename}`. |
| `DELETE …/attachments/{att_id}` | teacher | Removes row (object may stay; storage has no delete today — add `Storage.delete` in M1). |
| `GET …/attachments/{att_id}` | enrolled student, teacher | `StreamingResponse` from `Storage.open()`, `Content-Disposition: attachment; filename*=UTF-8''…`, correct `Content-Type`/`Content-Length`. Also serves the legacy virtual attachment. Archived assignments 404 for students. |
| `PUT …/questions` | teacher | Replace the whole ordered question set. 422 `weights_must_total_100` if graded weights ≠ 100 (for a lab question with an authored scheme, its weight must equal `target_percent`). Refused (409) if any submission has answers for a question being removed, unless `force=true`. |
| `PUT …/submission/answers/{question_id}` | student | Upsert one answer while `status == "draft"` and assignment `open`. Creates the draft submission on first call. `file` questions take multipart (same size cap) into `course-files/…/submissions/{user_id}/…`. |
| `POST …/submission/turn-in` | student | Draft → submitted. Scores `choice` answers against `answer_key`; for each `lab` question runs `grading.autograde_if_due(…, force=True)` on the student's running instance of that template if one exists, else leaves it for the lifecycle triggers. Recomputes grade. 409 if closed. |
| `POST …/submissions/{sid}/answers/{qid}/grade` | teacher | `{awarded_percent, feedback}`; 0 ≤ award ≤ question weight. Recomputes; emits `grade.posted` and queues passback exactly as `grade()` does today (factor that tail out and reuse it). |
| `GET …/submissions/{sid}/answers/{qid}/file` | teacher, owning student | Streamed download of a file answer. |

Keep the old `POST …/attachment` and `POST …/submissions` working — the old
one appends an attachment row; the old submit becomes "create + turn in with
`text` as the answer to the first text question (or virtual question)". Existing
tests in `test_management.py` / `test_grading.py` must still pass unmodified;
that is the compatibility proof.

Add `GET /api/v1/courses/deadlines` in M4 (declare it **above** any
`/{course_id}` GET route).

### 3.4 Frontend

- New route `app/(app)/courses/[id]/assignments/[aid]/page.tsx` + `view.tsx`
  (mirror `app/(app)/labs/[id]/page.tsx`'s async-params pattern).
- Student view: `Markdown` body, attachment list, per-question answer widgets,
  a lab card that launches (`POST /api/v1/instances`) and then shows
  `components/lab/ConnectHelp.tsx`, `Countdown`, and `GradingCard` inline.
- Teacher view: same page with an **Edit** mode — `components/course/content-editor.tsx`
  (D8), `attachments-editor.tsx`, `questions-editor.tsx` (weights summing
  live to 100, red until they do), and links to the existing gradebook.
- `app/(app)/courses/view.tsx`: assignment rows link to the page; the
  student list shows open assignments only (it already hides archived).
- `components/course/upload-panel.tsx` / `assignment-manager.tsx`: the single
  "attach a file" path moves into the page editor; keep the create-assignment
  form but have it redirect to the new page after creation.
- Types in `lib/api/types.ts` for every new payload.

### 3.5 Student dashboard

Remove the lab-launch panel from the student dashboard; show dues and
deadlines instead. Labs launch from the roadmap (done) and the assignment page
(M3). `LaunchPanel` stays for teacher/admin roles.

> Reconciliation of two review bullets: one asked for a labs *tab* on the
> dashboard, a later one asked to *remove* labs from the dashboard for dues.
> The later, more specific instruction wins.

`GET /api/v1/courses/deadlines` → for the student's enrolments, assignments
with `status != "archived"`, ordered by `due_at` (nulls last), each with
course code/title, `due_at`, and the caller's state:
`not_started | draft | submitted | graded` and grade if graded. Default window:
overdue-and-unsubmitted plus the next 30 days; `?all=true` for everything.

### 3.6 Teacher VM-diff lab authoring

**The flow the teacher sees**

1. From a course (or Labs → "Author a VM lab") → an **authoring session**: an
   interactive VM (SSH via the existing connect flow, or noVNC for `gui`), **no
   fixed time limit**, **stopped after 12 h idle with a snapshot first** (D6)
   and resumable exactly where it was.
2. Two guided captures:
   a. **Capture unsolved** — "this is what the student first sees." Takes
      Proxmox snapshot `unsolved`, records manifest M₀ and the audit-log
      high-water mark (last event serial).
   b. Teacher solves the lab in the same VM.
   c. **Capture solved** — takes snapshot `solved`, records manifest M₁ and
      every audit event after the high-water mark.
   Either capture can be retaken (rollback to `unsolved` and redo is a button).
3. The system diffs M₀→M₁ and lists everything the solve introduced — files
   added/changed/deleted and *every command the teacher ran*. Teacher checks
   the items that count and puts a percentage on each; file items expand to
   show content (text ≤64 KB, else "binary, N bytes, sha256 …").

   ```
   | ✔ | Rubric                                    |   % |
   | [] | hello.txt  (click to show content)        | [ ] |
   | [] | cat hello.txt                             | [ ] |
   | [] | ping 192.168.1.1                          | [ ] |
   ```

4. **Save** → the system builds the student template and the rubric (below).
5. The teacher may attach it to an assignment and add quiz questions for the
   remaining percentage; the whole assignment totals 100 (D3).

**What Save does (server-side, a queued job):**
1. Full-clone the authoring VM **from snapshot `unsolved`** to a new VMID in
   the authored-lab range (reserve one in lab-vm-templates.md's VMID table,
   e.g. `8100–8999`), boot it, run `palestrix-seal` over the guest agent
   (ships in the authoring template: truncates `/var/log/audit/*`, removes
   shell histories, `cloud-init clean`, resets machine-id), shut down, and
   convert to a template (`POST …/template`). The teacher's own commands must
   never reach a student clone's audit log, or every command item would pass
   on first boot.
2. Create a `LabTemplate` (`kind="vm"`, `vm_template=<new name>`,
   `audited=True`, sizes copied from the authoring session).
3. Create a `GradingScheme` (`kind="diff"`, `source="authored"`,
   `target_percent=<sum of chosen weights>`, `status="draft"`) and one
   `RubricItem` per checked row:
   - file item → `checks = {"files": [{"path","sha256","present"}]}` — exactly
     today's diff check, so `_item_passed` grades it unchanged.
   - command item → `checks = {"command": {"argv": [...], "match": "subset"}}`
     — the new check kind (M7).
4. Keep snapshot `solved` on the authoring VM as the answer key; keep the
   authoring VM itself (stopped) so the teacher can reopen and revise.

**New grader work (M7).** `run_checks` gains a second probe: when any item has
`"command"` checks, read the student VM's audit events once
(`provider.read_commands(db, instance)` → list of argv lists) and pass them to
`_item_passed` alongside the file hashes. Providers without `read_commands`
raise `GradingUnavailable` for command items only — file items still grade.

### 3.7 Authoring data model

```python
class AuthoringSession(Base):
    __tablename__ = "authoring_sessions"
    id, owner_id (FK users, index), tenant_id (FK),
    title (String 256), base_template (String 128)   # "debian12-author"
    instance_id (FK instances, nullable)   # the live VM, reuses Instance
    state (String 16)   # provisioning|active|idle_stopped|saving|saved|failed
    unsolved_manifest (JSON, nullable), solved_manifest (JSON, nullable)
    audit_mark (String 64, nullable), commands (JSON, default list)
    candidates (JSON, default list)   # computed diff rows, stable ids
    lab_template_id (FK, nullable), scheme_id (FK, nullable)  # after save
    last_active_at, created_at
```

The live VM is an ordinary `Instance` so the connect modal, logs stream, and
tenant network all work, but with `expires_at = None` and a new
`Instance.purpose: String(16), default "lab"` (`lab|authoring`). The TTL
reaper already skips `expires_at is None`; the new idle pass handles
`purpose == "authoring"`. Tenant quota: count authoring instances against the
teacher's tenant like any other (no special case).

---

## 4. Milestones

Each: files → work → tests → done when. Tick the box when merged.

### [ ] M1 — Storage and course-file plumbing

- `storage.py`: add `course-files` to `BUCKETS`; add `open(bucket, key) ->
  BinaryIO` and `stat(bucket, key) -> StoredObject` and `delete(bucket, key)`
  to the `Storage` protocol and both backends (MinIO: `get_object` response
  as the stream; release the connection on close).
- `config.py`: `course_file_max_mb: int = 200`.
- A small `api/_files.py` helper: `stream_download(bucket, key, filename,
  content_type)` returning a `StreamingResponse` with RFC 5987 filename; and
  `checked_upload(file, max_bytes)` that enforces the cap even when
  `UploadFile.size` is `None` (count while copying, abort at the limit).
- Deployment docs (usecase-a/usecase-b): any reverse proxy in front of the API
  needs `client_max_body_size 210m` (nginx) or equivalent; say so.
- **Tests** (`test_courses_files.py`): LocalStorage `open/stat/delete`
  round-trip; oversize upload → 413 without writing the object.
- **Done when:** suite green; no route uses `Storage.get()` for course files.

### [ ] M2 — Courses backend: content, attachments, questions, answers

- `models.py`: §3.2 tables and columns.
- `schemas.py`: `AssignmentPageOut`, `AttachmentOut`, `QuestionIn/Out`
  (student variant without `answer_key`), `AnswerIn/Out`, `AnswerGradeIn`,
  `SubmissionDetailOut`.
- New `courses_grading.py`: `effective_questions(db, assignment)` (virtual
  question shim), `effective_attachments(…)`, `score_choice`, `recompute`,
  `post_grade(db, course, assignment, submission, source)` (the event +
  passback tail factored out of `api/courses.py::grade`).
- `grading/weights.py` (or inside `grading/__init__.py`): shared
  `validate_weights`; switch `publish_scheme` to `== scheme.target_percent`.
- `api/courses.py`: §3.3 endpoints; `AssignmentIn/UpdateIn` accept `body_md`;
  legacy routes delegate to the new ones.
- `grading/__init__.py::write_back`: for each matching assignment, find its
  lab question(s) for `template.id` (via `effective_questions`, so legacy
  `kind="lab"` assignments still match), upsert that `SubmissionAnswer`
  (`awarded_percent = check.total_percent`, `instance_id`,
  `grade_check_id`), set `status="submitted"` if it was a draft *only when the
  assignment has no other graded questions* (a lab-only assignment is turned in
  by finishing the lab — today's behaviour), then `recompute` and
  `post_grade`. Match assignments by question binding, not just
  `Assignment.lab_template_id`.
- `academy_gate.py`: normalise by `target_percent` (D3).
- **Tests** (`test_assignment_pages.py`): student sees page without
  `answer_key`; unenrolled student 403; archived → 404 for student; multi-file
  upload + student download bytes match; question weights ≠ 100 → 422;
  draft answers upsert, turn-in scores choice, closed → 409; teacher grades a
  text answer → `Submission.grade` recomputed and `grade.posted` emitted;
  partially graded → `grade is None`; lab question autograde flows through
  `write_back` into the answer; **legacy**: an assignment made the old way
  (single `storage_key`, `kind="lab"`) presents one attachment / one virtual
  question and the existing `test_grading.py::test_partial_credit_end_to_end`
  still passes untouched.
- **Done when:** whole suite green with zero edits to existing tests.

### [ ] M3 — Courses frontend: the assignment page

- §3.4 route and components; TipTap per D8 (record the measured bundle delta
  in the PR description).
- Launch from the page reuses the dashboard's launch call; on success, render
  `ConnectHelp` inline rather than navigating away; "open full lab view"
  links to `/labs/{instance_id}`.
- Weight editor: live total, graded/ungraded toggle, disallow publish ≠ 100.
- File inputs show the 200 MB cap and reject client-side before upload.
- **Done when:** `npm run build` passes; walkthrough against the seed data:
  teacher creates an assignment with body, two attachments, a text + choice +
  lab question (40/20/40), student opens it, downloads both files, answers,
  launches the lab from the page, turns in; teacher grades the text answer and
  sees the total.

### [ ] M4 — Student dashboard deadlines

- `api/courses.py`: `GET /courses/deadlines` (§3.5), `schemas.DeadlineOut`.
- `app/(app)/dashboard/view.tsx`: for `role === "student"` replace
  `<LaunchPanel />` with `<DeadlinesPanel />` (new
  `components/course/deadlines-panel.tsx`: title → assignment page link,
  course code, relative due date with overdue in the danger colour, state
  badge). Non-students keep `LaunchPanel`. An active instance still shows its
  card for everyone.
- **Tests:** ordering (nulls last), archived excluded, other courses'
  assignments excluded, state derivation for each of the four states,
  teacher → 403 (or empty; pick 403 and test it).
- **Done when:** suite green, build green, a student dashboard shows no launch
  panel.

### [ ] M5 — Proxmox provider: the calls authoring needs

All in `orchestration/proxmox.py`, each with a `MockTransport` route and a test
in `test_orchestration.py`:

- `snapshot(vmid, name, description="")` → `POST …/qemu/{vmid}/snapshot`
  (`vmstate=0`), wait task.
- `rollback(vmid, name)` → `POST …/snapshot/{name}/rollback`.
- `delete_snapshot(vmid, name)`.
- `agent_exec(vmid, argv, timeout)` → `POST …/agent/exec` (`command` as
  repeated params) then poll `GET …/agent/exec-status?pid=` until `exited`;
  return `(exitcode, out-data, err-data)`. Cap output at 8 MB; raise on
  truncation (`out-truncated`).
- `clone_from_snapshot(src_vmid, snapname, newid, name)` → `…/clone` with
  `full=1&snapname=`.
- `convert_to_template(vmid)` → `POST …/template`.
- `start(vmid)` (the existing `status/start` path, factored out).
- `read_commands(db, instance)` → `agent_exec` `ausearch` + parser (D2).
  Put the parser in a pure function `parse_ausearch(text) -> list[dict]`
  (`serial`, `time`, `auid`, `argv`) and unit-test it against a captured
  fixture (`backend/tests/fixtures/ausearch-sample.txt` — capture a real one
  from a Debian 12 VM with auditd 3.0.9 when building `debian12-author`).
- Token permissions: `agent/exec` needs `VM.GuestAgent.Unrestricted` on PVE 9
  (`VM.Monitor` on PVE 8), and snapshots need `VM.Snapshot`. Add both to the
  role in the install docs and make `check()` report them missing.
- **Done when:** every call has a mocked test; `parse_ausearch` tested on the
  fixture including a pipeline and an argument with spaces.

### [ ] M6 — Authoring template and session lifecycle

- `docs/lab-vm-templates.md`: `debian12-author` recipe (from `debian12-min`
  + `auditd`, the audit rule file `/etc/audit/rules.d/palestrix.rules`,
  `/usr/local/sbin/palestrix-manifest`, `/usr/local/sbin/palestrix-seal`,
  student user **without sudo** per D7), the VMID ranges for authoring
  sessions and authored templates, and the rule that authored templates are
  `audited`. Keep the two scripts in the repo under
  `labs/authoring/` so the recipe `virt-customize --upload`s them and the
  backend's server-side noise filter can import the same exclusion list
  (one list, two consumers).
- `models.py`: `AuthoringSession`, `Instance.purpose`,
  `LabTemplate.audited`.
- New `api/authoring.py` (router `/authoring`, `courses:write`):
  `POST /sessions` (provision from `debian12-author` via the existing queue,
  `purpose="authoring"`, `expires_at=None`), `GET /sessions`,
  `GET /sessions/{id}`, `POST /sessions/{id}/heartbeat`,
  `POST /sessions/{id}/resume`, `DELETE /sessions/{id}` (destroys VM and
  snapshots; refuses while `saving`).
- `orchestration/reaper.py`: `idle_authoring(db, now)` — per D6, snapshot then
  stop; state `idle_stopped`; called from `ReaperThread.run` and the worker
  loop next to `reap_expired`. Make sure `reap_expired` never touches
  `purpose == "authoring"` even if someone sets an `expires_at`.
- `api/instances.py`: `stop`/`destroy`/`extend` on an authoring instance go
  through the authoring API (409 with a pointer) so a stray click in the lab
  view cannot destroy a teacher's work.
- **Tests** (`test_authoring.py`, mocked Proxmox): create → active;
  heartbeat updates `last_active_at`; 12 h idle → snapshot then stop, state
  `idle_stopped`; resume → active; TTL reaper ignores it; student → 403;
  another teacher → 403 (superadmin allowed).
- **Done when:** suite green; recipe reviewed against the real cluster by the
  owner (flag it in the PR — the model cannot build the golden image).

### [ ] M7 — Capture, diff, candidates, and the command check

- `api/authoring.py`: `POST /sessions/{id}/capture/unsolved`,
  `POST /sessions/{id}/capture/solved`, `POST /sessions/{id}/reset-to-unsolved`,
  `GET /sessions/{id}/candidates`, `GET /sessions/{id}/candidates/{cid}/content`.
- New `grading/authoring.py` (pure functions, heavily unit-tested):
  `parse_manifest(text)`, `diff_manifests(m0, m1) -> [added|changed|deleted]`,
  `filter_noise(rows)` (shared exclusion list), `command_candidates(events)`
  (dedupe identical argv, drop the shell itself and Palestrix's own scripts,
  keep order of first use), `candidate_id(row)` (stable hash so the UI's
  selections survive a re-fetch), and `candidates_to_rubric(selected,
  weights) -> (list[RubricItem spec], target_percent)`. Reuse
  `classify_path` for file item keys/titles.
- `grading/__init__.py`: `_item_paths` ignores command items; `run_checks`
  fetches commands once when needed via `provider.read_commands`;
  `_item_passed(item, observed, commands)` handles `"command"` per D4.
  Extract the matcher as `command_matches(expected, observed_argv)`.
- **Tests:** manifest diff (added/changed/deleted, noise dropped); command
  dedupe; `command_matches` table (subset with extra flag passes, wrong host
  fails, exact mode, basename `/usr/bin/ping` vs `ping`); a mixed file +
  command scheme graded end-to-end on a mocked instance with partial credit;
  a provider without `read_commands` grades file items and marks command items
  unavailable rather than failing the whole check (decide: the check fails
  closed for those items — record `passed: false, error: "unavailable"` —
  and test it).
- **Done when:** suite green.

### [ ] M8 — Save: template + scheme from the authoring session

- `POST /sessions/{id}/save` body: `{title, slug, selected: [{candidate_id,
  weight_percent, argv?, match?}], cpu, ram_gb, ttl_minutes_default,
  ttl_minutes_max}`. Validates `0 < sum ≤ 100`. Runs as a queued job
  (`orchestration/jobs.py` pattern) doing §3.6 "What Save does"; state
  `saving` → `saved` | `failed` with the error logged to the session's
  instance log.
- Re-save after revising: creates a **new** template version (slug
  `name:1.1`, …) rather than mutating one students may be running; the new
  scheme starts in `draft`.
- `api/grading.py::create_scheme` unchanged; `publish_scheme` refuses a scheme
  with command items whose template is not `audited` (D7).
- Assignment binding: a lab question may reference the new template; its
  weight must equal the scheme's `target_percent` (validated in `PUT
  …/questions`).
- **Tests:** save builds the right clone/seal/template call sequence against
  the mock; rubric rows match the selection; `target_percent` = selected sum;
  publish with a non-audited template + command item → 422; lab question
  weight mismatch → 422; re-save bumps the version.
- **Done when:** suite green.

### [ ] M9 — Authoring frontend

- `app/(app)/labs/author/page.tsx` (list + "new session") and
  `app/(app)/labs/author/[id]/page.tsx` (the session): stepper
  **Prepare unsolved → Capture → Solve → Capture → Build rubric → Save**,
  connection info via `ConnectHelp`, provisioning log via `ProvisioningLog`,
  heartbeat every 5 min while the tab is visible (`visibilitychange`), resume
  button when `idle_stopped`.
- Rubric builder table exactly as sketched in §3.6: checkbox, label (file path
  or command line), expandable content for files (fetched lazily), editable
  argv tokens + match mode for commands, % input, live total with the
  remaining percentage labelled "left for quiz questions".
- After save: link to the new template and a "use in an assignment" button
  that opens the M3 assignment editor with a lab question pre-filled at the
  saved `target_percent`.
- Entry points: a button on the courses page teacher panel and the labs
  catalog.
- **Done when:** `npm run build` passes; walkthrough against a mocked or real
  cluster documented in the PR (screenshots via the `run` skill if a cluster is
  unavailable, using the demo provider for the non-Proxmox parts).

### [ ] M10 — Docs and ledger

- `docs/managing-courses-and-users.md`: assignment pages, questions,
  attachments, deadlines.
- `docs/automated-checking.md`: authored schemes, `target_percent`, command
  checks, the no-root rule.
- `docs/rbac-matrix.md`: the new routes.
- `docs/public-api.md`: new endpoints.
- PLAN.md progress log + test count; README status table if it lists features.
- Mark each milestone box above; replace this file's status line with "Built".

---

## 5. Risks and what to do about them

| Risk | Mitigation |
| --- | --- |
| Guest-agent exec disabled or token lacks permission on the real cluster. | `check()` reports it (M5); capture endpoints return a 503 naming the missing privilege instead of a generic failure. |
| `find /` on a larger VM is slow or huge. | `-xdev`, exclusion list, and a 120 s exec timeout; the manifest is `sha256 size path` only (~100 bytes/file; a minimal Debian is ~30k files ≈ 3 MB, under the 8 MB cap). Warn and refuse capture above the cap rather than truncating silently. |
| Audit log rotated or huge during a long solve. | Record the serial high-water mark at capture-unsolved; `ausearch --start` from it. Set `max_log_file` / `num_logs` generously in the authoring template. |
| Student with root forges or wipes the audit log. | D7: no sudo for the student user; publish refuses command items on non-audited templates. Document as a known limit for labs that *require* root (use file checks there). |
| Teacher noise leaks into the rubric (editor swap files, `apt update`). | Noise list + teacher unchecks rows; nothing is selected by default. |
| Idle stop loses unsaved in-memory state (running processes). | Stated in the UI: "after 12 h idle the VM is shut down; files are kept, running programs are not." Snapshot is `vmstate=0` by choice — RAM snapshots are large and slow on the single-workstation deployment. |
| Grade semantics change breaks Canvas passback. | `Submission.grade` stays the 0–100 total; passback code untouched; M2 tests assert a passback row is queued after an answer-level grade. |
| TipTap bloats the bundle. | D8 fallback, measured in M3. |

---

## 6. Out of scope for this block

- Desktop/GUI authoring images (D5).
- Question banks, randomised quizzes, timed quizzes, attempts > 1.
- Late-submission policy and per-student extensions (deadlines are display-only).
- Container (Docker) authoring sessions — the archive-diff path already covers
  containers.
- Peer review, rubrics for manual questions beyond a single score + feedback.

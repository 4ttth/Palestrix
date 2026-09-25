# Roadmap: teacher authoring, courses, and the student dashboard

Design notes for the next block of work, captured 2026-09-25 from a review of
the live platform. Nothing here is built yet — this is the spec to build
against, written so the shape is agreed before code. Three threads that share a
data model and should ship in this order:

1. **Courses & assignments redesign** (highest day-to-day value)
2. **Student dashboard** (small, depends on 1)
3. **Teacher VM-diff lab authoring** (largest, most novel)

---

## 1. Courses & assignments redesign

### Where it is now

`api/courses.py` has create / list / attach / gradebook / submit / grade, and
(added recently) edit / close / archive / delete plus a status the lifecycle
enforces. An assignment can carry one file (`storage_key`) or a
`lab_template_id`. Gaps the review surfaced:

- **Once a file assignment is published, there is nothing more to do with it.**
  You can attach one PDF; you cannot edit the content around it, add more
  files, or say how it is graded.
- **Students cannot open the uploaded files.** `upload_assignment_file` stores
  to object storage but no student-facing download route exists.
- **"quiz export" is undefined.** The `kind` enum has `quiz` but nothing reads
  or renders it.
- **Assignments are not really graded.** Submissions get a manual 0–100; there
  is no per-question structure, no autograding for file/lab work tied to a
  rubric, no quiz scoring.
- **Ephemeral labs are not launchable from a course.** A `lab` assignment
  references a template but the student has no launch affordance in the course
  view; today launching lives only on the dashboard and (now) the roadmap.

### Target — the assignment as a page, Canvas-style

**Student workflow**

1. Courses tab → pick a course → see **Open assignments** (archived ones are
   already filtered out of the student view; keep that).
2. Click one → an **assignment page**: the teacher's rich content, every
   attachment (downloadable), an inline **Launch** for any bound lab with its
   connection info, and the questions to answer — all on one screen.
3. Submit: file upload(s), text answers, and/or a passing lab check, depending
   on what the assignment declares.

**Teacher workflow**

1. Create/attach a VM (see §3) *or* author a file/quiz assignment.
2. Edit content in a **WYSIWYG editor with a Markdown toggle**.
3. Add **questions** — textbox, file submission(s), or a lab check — each
   **graded or ungraded**, each carrying a weight.
4. Attach files (**multiple, up to 200 MB each**).
5. Publish; edit freely afterwards (the edit/close/archive/delete already
   exists — extend it to the new fields).

### Data-model additions (sketch)

- `Assignment` gains `body_md` (rich content) and drops the single-file
  assumption.
- New `AssignmentAttachment` (assignment_id, storage_key, filename, size,
  content_type) — many per assignment, 200 MB cap each, streamed like ISOs.
- New `AssignmentQuestion` (assignment_id, position, kind ∈
  {text, file, lab, choice}, prompt_md, weight_percent, graded: bool,
  lab_template_id?, autograde_scheme_id?).
- `Submission` becomes per-question: `SubmissionAnswer` (submission_id,
  question_id, text?, storage_key?, instance_id?, awarded_percent?).
- Weights across graded questions **must sum to 100** (the same invariant the
  lab rubric already enforces; share the validator).

### Endpoints (sketch)

- `GET /courses/{id}/assignments/{aid}` → the full page payload for a student
  (content, attachments with signed download URLs, questions, any bound lab).
- `GET /courses/{id}/assignments/{aid}/attachments/{key}` → streamed download,
  enrolment-checked (closes the "students cannot access files" gap).
- `POST …/attachments` (teacher, multipart, ≤200 MB) — many.
- `PUT …/questions` (teacher) — the question set with weights; rejects a graded
  set that does not total 100.
- `POST …/submit` becomes per-question answers; autograded questions (lab pass,
  choice) score immediately, manual ones land in the gradebook.

### Frontend

- New `courses/[id]/assignments/[aid]` route — the assignment page.
- WYSIWYG: a small, dependency-light editor with an md source toggle (evaluate
  against the artifact-size budget before pulling a heavy one).
- Reuse `ConnectHelp` for the in-page lab launch + connection info.

---

## 2. Student dashboard

Bullet from the review: **remove the lab-launch panel from the student
dashboard; show dues and deadlines from the student's courses instead.** Labs
launch from the roadmap (done) and from the course assignment page (§1), so the
dashboard no longer needs its own launcher.

- New `GET /me/deadlines` (or `/courses/deadlines`) → upcoming assignments
  across the student's enrolments, sorted by `due_at`, archived excluded.
- Dashboard: replace `LaunchPanel` for the student role with a deadlines list
  (title, course, due date, submitted/graded state). Teachers/admins keep
  their launch affordance, or move it under the infrastructure/course views.

> Reconciliation of two review bullets: one asked for a labs *tab* on the
> dashboard, a later one asked to *remove* labs from the dashboard for dues.
> The later, more specific instruction wins — labs are reached from the roadmap
> and the course page, and the dashboard is deadlines.

---

## 3. Teacher VM-diff lab authoring

The largest piece. A teacher builds a lab by *doing it*, and the system turns
what they did into a rubric.

### The flow the teacher sees

1. Redirect to a **lab-authoring session**: an interactive VM (browser console
   or SSH), **no fixed time limit**, that **pauses after 12 h idle but
   snapshots first so it can resume** exactly where it was.
2. Configure two states, guided:
   a. **The unsolved machine** — what the student first sees.
   b. **The solved machine** — what a completed machine looks like.
3. Save.
4. The system **diffs the two states** and presents everything the solve
   introduced — files created/changed, *and every command the teacher ran*
   (`cat /home/student/flag.txt`, `ping 192.168.1.1`, a new `hello.txt` with
   its contents). The teacher **checks the items** that should count and puts a
   **percentage** on each. A file item can be expanded to show its content.

   ```
   | ✔ | Rubric                                    |   % |
   | [] | hello.txt  (click to show content)        | [ ] |
   | [] | cat hello.txt                             | [ ] |
   | [] | ping 192.168.1.1                          | [ ] |
   ```

5. The lab becomes available for automated grading. The teacher may **attach a
   quiz** for the remaining percentage. The sum **must reach 100** at the end
   of the activity (it may be < 100 from the lab alone if a quiz makes up the
   rest); the teacher can tune the % per rubric item and per question.

### How the diff is captured — file diff + audited command log

Chosen approach (over file-diff-only), because the spec needs commands that
leave no file trace (`ping`), and bash history is unreliable (not flushed until
logout, editable, missing pipes):

- **File diff:** compare the unsolved and solved disk states offline with
  libguestfs `virt-diff` (the same toolchain the template build already uses).
  Yields added / changed / deleted files, and for text files the content the
  rubric item can display.
- **Command log:** bake command auditing into the authoring template so *every*
  command is recorded reliably, not scraped from history. Two options to pick
  between at build time:
  - `auditd` with an `execve` rule → a durable, tamper-evident log of every
    executed program and its arguments; or
  - a lighter `PROMPT_COMMAND` / `PROMPT_COMMAND`-plus-`script` capture writing
    each command line to an append-only file.
  `auditd` is the more faithful and is the recommendation; it captures `ping`
  and pipelines that a history file can miss.
- The authoring session runs on its **own template** (not the student
  `debian12-min`), with auditing on and the console exposed to the teacher.

### Lifecycle

- Snapshot-on-idle + resume: a reaper variant that, at 12 h idle, `qm snapshot`
  then `qm suspend`/`stop`, and resumes from the snapshot when the teacher
  returns — distinct from the student TTL reaper, which destroys.
- On save, the solved state is snapshotted as the lab's answer key; the
  unsolved state becomes (or updates) the `LabTemplate` the student clones.
- The chosen rubric items become a `GradingScheme` + `RubricItem`s — the exact
  structures the automated checker already grades (file items map to the
  existing `checks.files[]`; command items need a new check kind that greps the
  audit log for the command, which is new grader work).

### New grader work

The current grader (`grading/__init__.py`, `proxmox.read_files`) does file-hash
checks over the guest agent. Command-based rubric items need a new check kind
that reads the student VM's audit log via the agent and matches a command
pattern. Design it alongside the file check so both share `_item_passed`.

---

## Open questions to settle before building §3

- **Authoring VM base**: Debian like the labs, or does authoring need a richer
  desktop (GUI console) for some lab types?
- **Command match strictness**: exact line, or a normalized/argument-aware
  match (so `ping -c1 192.168.1.1` can satisfy a `ping 192.168.1.1` item)?
- **Where the quiz lives**: reuse the §1 `AssignmentQuestion` model so a lab and
  its quiz are one assignment, rather than a lab-only quiz concept.

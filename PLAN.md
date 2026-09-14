# PalestrIX — Re-Plan and Progress Ledger

**This file is the working contract for anyone — human or model — picking up
this repository.** Read it before touching code. Update it when you finish
work. It is the only place where "what is true right now" is recorded.

- **Branch:** `claude/replan-archive-docs-4d6ahv`
- **Archive snapshot:** branch `archive` @ `e008971` — the complete
  pre-replan state. Never force-push it. Diff against it to recover anything.
- **Last verified:** 2026-09-14

---

## 1. Authority: what wins when sources disagree

The research paper — *GROUP_1_-_Topic_1_Midterm.docx* ("PalestrIX: A Scalable,
Multitenant, Deployment-Agnostic Platform for a Cyber Training Range for
Institutional Learning", Dizon, Flores, Garcia & Olpindo, Holy Angel
University) — **is the contract.** Where the codebase and the paper disagree,
the code changes to match the paper.

Two bounded exceptions, because blind application would damage the paper's own
claims. Both are logged in §5 and await an author decision:

1. Where the paper **contradicts itself**, code cannot satisfy both readings.
2. Where a repo feature is **unclaimed by the paper but load-bearing for a
   stated objective**, deleting it would break the objective it serves.

Everything else: the paper is right, the code is wrong, fix the code.

### Milestone target

**Final build + full evaluation.** The goal is the completed platform with
Track A telemetry and Track B acceptability data actually collected — not a
documentation-only midterm pass. Work is ordered so evaluation can begin as
early as possible, because Track B cannot start until the instrument is
validated and Track A cannot start until the harness exists.

---

## 2. Ground truth (verified 2026-09-14, re-verify before trusting)

| Fact | Value | How to re-verify |
| --- | --- | --- |
| Backend test suite | **97 passed, 0 failed** | `pytest backend/tests -q` |
| Backend size | 75 Python files, ~15,550 lines | `find backend -name '*.py' \| wc -l` |
| Frontend routes | 16 pages | `find app -name 'page.tsx'` |
| Role model | 4 roles: student, teacher, admin, **superadmin** | `backend/palestrix/models.py:45` |
| Perf/telemetry harness | **does not exist** | `grep -rl "replicate\|sysstat" .` → no hits |
| ISO 25010 instrument | **does not exist** | `grep -rl "25010\|Cronbach" .` → no hits |
| Provider kinds | Proxmox → `vm`, Docker → `container`, demo → both | `grep -n 'kinds = ' backend/palestrix/**/*.py` |
| VirtualBox adapter | **does not exist** | `ls backend/palestrix/orchestration/` |

> **Setup trap.** From a clean checkout the suite reports **4 failures** in
> `test_plugins.py`. They are not defects. `provider-demo` is found through
> *entry-point* discovery, so the reference plugin must be installed first:
>
> ```bash
> pip install -r backend/requirements-dev.txt
> pip install -e plugins/palestrix-provider-demo   # ← the undocumented step
> pytest backend/tests -q                          # → 97 passed
> ```
>
> This matters beyond convenience: the paper's Table 3 closes every increment
> on "the whole accumulated test suite passes". That criterion is currently
> not reproducible from a clean clone. See **G-06**.

---

## 3. Increment map — paper Table 3 ↔ repository

The paper defines **8 increments**. The repo was built in **9 labelled phases**
(it carries a "Phase 2b"). Paper Increment 8 merges repo Phases 7 and 8.
Because the paper is the contract, the repo renumbers to 1–8. See **G-03**.

| Paper increment | Subsystem (paper Table 3) | Repo phase | Closing tests | State |
| --- | --- | --- | --- | --- |
| 1 | Frontend surfaces, locked design system, deployment docs | Phase 1 | Production build of every route | Built |
| 2 | Core service: passkey auth, RBAC, versioned API, M2M auth, webhook/event bus, object storage | Phase 2 | `test_auth.py`, `test_rbac.py` | Built |
| 3 | Plugin framework: manifest discovery, capability scoping, encrypted config, crash isolation, UI slots | Phase 2b | `test_plugins.py` + 2 reference plugins | Built |
| 4 | Gamification: append-only ledger, daily caps, solve-scaled awards, first blood, writeups, streaks, decayed community score, leaderboards | Phase 3 | `test_gamification.py`, `test_compete.py` | Built |
| 5 | Orchestration: provider abstraction, Docker + Proxmox VE adapters, log stream, TTL reaper | Phase 4 | `test_orchestration.py`, `test_provider_check.py` | Built |
| 6 | Feature surfaces wired to the versioned API, real ceremonies, session-guarded routing, server-authoritative countdowns | Phase 5 | `test_surfaces.py`, `test_management.py` | Built |
| 7 | Malware sandbox: static pre-analysis, ATT&CK verdict, behavior timeline, sealed storage, gated export | Phase 6 | `test_sandbox.py` | Built |
| 8 | Multitenancy + hardening + Canvas LTI 1.3 | Phases 7 **and** 8 | `test_tenancy.py`, `test_integrations.py` | Built |

**All eight increments are functionally built.** The re-plan is therefore not a
rebuild. The remaining work is (a) the evaluation apparatus the paper promises
but the repo never had, and (b) conformance of code and paper to each other.

---

## 4. Objective coverage — paper §Objectives vs. reality

| # | Objective (abridged) | Implementation | Evaluable? |
| --- | --- | --- | --- |
| 1 | Ephemeral VMs/containers with automatic TTL reclamation | `orchestration/reaper.py`, `providers.py` | Needs **W1.1** |
| 2 | Gamification: Palestras, streaks, community score, leaderboards | `gamification.py` | Yes |
| 3 | RBAC for students, teachers, administrators | `rbac.py` | Yes — but see **G-07** |
| 4 | CTF arena: flags, first blood, writeups | `api/`, `/compete`, `/community` | Yes |
| 5 | Malware sandbox: static pre-analysis + detonation, ATT&CK verdict | `sandbox/` | Yes — but see **G-08** |
| 6 | Multitenancy: isolated network, quotas, naming | `tenancy/` | Needs **W1.1** |
| 7 | Canvas LTI 1.3: roster sync + grade passback | `integrations/` | Yes — but see **G-04** |
| 8 | ISO/IEC 25010:2023 evaluation across 9 characteristics | — | Needs **W1.1 + W1.3** |

Objective 8 is the one with no implementation at all. It is the reason the
evaluation workstream is ordered first.

---

## 5. Reconciliation ledger

Status: `OPEN` = not started · `WIP` = in progress · `DONE` = closed ·
`DECIDE` = blocked on an author decision, do not act unilaterally.

### G-01 · Track A performance harness missing · **OPEN** · owner: repo

The paper's Appendix C specifies a protocol the repo has no code for.
Required by Objective 8 and the entire Performance Efficiency characteristic.

The protocol demands, verbatim from the paper:

- An **idle baseline**: no student instance running, 30-minute continuous
  window, processor utilisation (%) and memory (GB) via `sysstat` +
  `docker stats`.
- Four workload scenarios: single-tenant sequential, single-tenant concurrent,
  multitenant concurrent, and quota ceiling.
- **Five independent replicates** per scenario, **order randomised** to control
  for a warmed image cache or warmed provider connection.
- Host **returned to idle and re-verified against the baseline** between
  replicates.
- Docker and Proxmox VE adapters exercised in **separate runs** so container
  and VM costs stay distinguishable.
- **Provisioning latency** = API accepts the request → log stream reports ready.
- **Reclamation latency** = recorded expiry timestamp → reaper emits expired
  and releases quota.
- Every record keyed by **scenario, replicate, tenant, provider adapter,
  instance id**, plus server-side timestamps, "so that any figure reported in
  the study can be traced back to the run that produced it."

Both latencies must derive from **server-side** timestamps only — the paper
explicitly rules out client network conditions contaminating the measurement.

### G-02 · ISO/IEC 25010 questionnaire missing · **OPEN** · owner: repo

Part 1 demographics; Part 2 on a five-point Likert scale across **eight**
sub-scales — functional suitability, compatibility, interaction capability,
reliability, security, maintainability, flexibility, safety. Performance
efficiency is deliberately **excluded** from Part 2 because Track A measures it
by telemetry; together the two instruments cover all nine characteristics
"so that no characteristic is evaluated twice and none is left unevaluated."

Adapted from Dela Rosa & Abad (2025), preserving their structure while
retargeting items to PalestrIX features: TTL reaper, malware sandbox,
multitenant isolation, ephemeral provisioning, Canvas integration.

Needs I-CVI and S-CVI by the averaging method (Yusoff, 2019), then Cronbach's
alpha per sub-scale with 0.70 as the floor (Taber, 2018). Interpretation
bands are fixed by the paper: 4.51–5.00 Highly Acceptable · 3.51–4.50
Acceptable · 2.51–3.50 Moderately Acceptable · 1.51–2.50 Low Acceptability ·
1.00–1.50 Not Acceptable.

### G-03 · Phase numbering diverges from the paper · **OPEN** · owner: repo

Repo says Phases 1, 2, **2b**, 3, 4, 5, 6, 7, 8. Paper says Increments 1–8.
Paper wins: renumber every reference in README, `docs/`, and code comments to
the Increment column in §3. Highest-traffic offenders: `README.md`,
`docs/architecture.md`, and the "mirrors the Phase 4/6/7 registry" comments in
`tenancy/` and `sandbox/`.

### G-04 · Autograding exists in code, absent from the paper · **DECIDE**

The repo has a rubric autograding subsystem — `backend/palestrix/grading/`
(443 lines), `api/grading.py` (8 endpoints), `test_grading.py` (464 lines),
`docs/automated-checking.md` (215 lines) — plus hooks reaching into `main.py`,
`schemas.py`, `providers.py`, `api/instances.py`, all three orchestration
modules, and `integrations/{canvas,passback}.py`. The paper never mentions it.

**Do not simply delete it.** Tracing the dependency shows why:
`queue_grade_passbacks` runs *inside the grading request, right after the
`grade.posted` event* (`integrations/passback.py:1-8`). Autograding is what
*produces* the grades that **Objective 7** carries into Canvas. The paper also
puts "view the gradebook" in the faculty hands-on sequence (Track B). Removing
the subsystem to satisfy "the paper does not claim it" would break an
objective the paper does claim.

**Recommendation:** amend the paper, not the code — one sentence in Scope and a
clause in Objective 7 naming how grades are produced. This is the cheapest
change that makes paper and code consistent without losing a working,
tested, 900-line subsystem.

**Alternative if the authors insist on removal:** it is a multi-day,
high-risk excision that lands squarely on the Canvas passback path, and
Objective 7 would need a replacement grade source. Do not start it without an
explicit instruction.

### G-05 · Runtime defaults contradict the Track A configuration · **OPEN** · owner: repo

The paper commits to a specific evaluation configuration: "The queue will be
set to its Redis backend so that provisioning is carried out by a separate
worker process rather than inside the request that asked for it, which is the
configuration an institution would actually run in a classroom."

Shipped defaults disagree on five counts — `hardening.py` correctly warns
about each, so this is a packaging gap, not a defect:

| Setting | Default | Track A requires |
| --- | --- | --- |
| `PALESTRIX_QUEUE_BACKEND` | `inline` | Redis + worker |
| `PALESTRIX_STORAGE_BACKEND` | local folder | MinIO |
| `PALESTRIX_REAPER_ENABLED` | off | on |
| `PALESTRIX_DATABASE_URL` | SQLite | PostgreSQL |
| `PALESTRIX_ORIGIN` | http | https |

A measurement taken under the defaults measures something the paper does not
describe. Ship a single committed **evaluation profile** so every run is
reproducible and provably the configuration the paper claims.

### G-06 · Test-suite closure criterion not reproducible · **OPEN** · owner: repo

Per §2. The paper's Table 3 note — "An increment is closed only when the whole
accumulated test suite passes" — cannot currently be demonstrated from a clean
clone without an undocumented `pip install -e`. Fix by making the reference
plugin install automatic (dev requirements or a `conftest.py` guard that fails
with an actionable message) and documenting it in `backend/README.md`.

### G-07 · Paper contradicts itself on role count · **DECIDE**

- Introduction: "...enable administrators to manage resources, and **super
  administrators** to manage the platform at a system-wide level" — 4 roles.
- Objective 3 and Scope: "students, teachers, and administrators" — 3 roles.
- Code: 4 roles (`models.py:45`), superadmin carries distinct capabilities
  including `courses:write`, `compete:adjust`, `instances:read-all`.

The contract is ambiguous, so code cannot resolve it. **Recommendation:** amend
Objective 3 and Scope to name the super administrator, matching the
Introduction and the implementation.

### G-08 · Objective 5 overpromises against the delimitation · **DECIDE**

Objective 5 promises "a monitored detonation". The delimitation says the
built-in detonator "produces a clearly labeled simulated dynamic trace unless a
separate live detonation host is attached". The Ethics section then binds the
study to the default detonator and EICAR-only samples.

The code is honest — `sandbox/` labels the synthetic trace and swaps in a real
coordinator via `PALESTRIX_SANDBOX_COORDINATOR_URL`. It is Objective 5's
*wording* that overreaches. **Recommendation:** reword Objective 5 to match the
delimitation the study actually operates under. A reader comparing Objective 5
to the Ethics section will otherwise find the study promising what it forbids
itself from doing.

### G-09 · Appendix B computation is blank · **OPEN** · owner: authors

`n = ______ / (1 + ______ × (0.05)²) = ______`. Blocks Track B: the student
sample size cannot be fixed without the enrolment figure from the Office of the
University Registrar. Faculty (10) and professionals (5) are set by criteria
and need no computation.

### G-10 · Reference list defects · **OPEN** · owner: authors

Verified against the body text (§Introduction through §Research Procedure):

- **Zhong et al. (2022) is cited twice in the body but is absent from the
  reference list.** It carries the Kolb/experiential argument and the warning
  that gamified rewards must attach to real achievement — load-bearing, not
  decorative. Most serious defect here.
- **Six entries appear in the reference list but are never cited:** Fortinet
  (2025), Fortinet (n.d.), Department of Information and Communications
  Technology (2023), Rappler (2024), Strom et al. (2020), and International
  Information System Security Certification Consortium (2025).
- **Duplicate ISC2 entry:** the body cites "ISC2, 2024"; a second entry for the
  same organisation sits under its expanded name with a 2025 date.
- **Citations missing years:** "(Ramezanian & Niemi; National Institute of
  Standards and Technology)"; "(Bertone et. al.; Lazarov; Deng et. al.)"; and
  the narrative "In Nakata and Otsuka... and in Mills et al." in §Research
  Design.
- **Style:** "et. al." appears throughout; APA is "et al."
- MITRE ATT&CK is discussed in three places with no author-date citation,
  though Strom et al. (2020) sits unused in the list — pairing these fixes both.

### G-11 · VirtualBox demo path is a sanctioned scope addition · **OPEN** · owner: authors + repo

The authors have directed a **VirtualBox demo path for low-specification
machines**, with Proxmox VE remaining the final and reference deployment.

VirtualBox appears **nowhere** in the paper. This is not a gap being closed —
it is a deliberate extension of scope, and under §1 it propagates *into* the
document. Four sections need amending:

| Paper section | Current text | Needs |
| --- | --- | --- |
| Table 1, Software Requirements | "Virtualization \| Proxmox VE (KVM and LXC), Docker" | Add VirtualBox, marked demo-only |
| Scope and Delimitations | "documented for two ways of deployment: on a single Proxmox VE workstation... and on cloud services" | A third, non-reference demo path |
| Delimitations | names OpenNebula/CloudStack as optional non-focus adapters | Same treatment for VirtualBox |
| Table 2, Hardware Requirements | assumes a ZFS pool and a VLAN-aware bridge | Neither exists on a laptop; see W5.2 |

**Measurement integrity — the hard rule.** The paper fixes the reference
deployment as "a single Proxmox VE workstation owned by the institution" and
states that "no figure will be presented as a property of the platform
independent of the machine it ran on." Therefore:

> **No VirtualBox telemetry may ever be reported as Track A data.** Appendix C
> scenarios remain Docker and Proxmox VE only. The harness must refuse to emit
> a reference-grade results file when running under the VirtualBox adapter.

The demo path exists to *show the platform working* on modest hardware. It is
not a measurement surface, and conflating the two would invalidate the
performance chapter.

**Assumption recorded** (correct it if wrong): the VirtualBox path serves
development and demonstration — including defense presentation — while **both
Track A and Track B run on the Proxmox reference deployment**. If respondent
sessions were instead run on VirtualBox, that is a methodology deviation
requiring disclosure, because the paper places those sessions on the reference
deployment.

---

## 6. Workstreams

Ordered by dependency. W1 gates the milestone: no evaluation data can be
collected until it lands.

### W1 — Evaluation apparatus *(blocks the milestone)*

- [ ] **W1.1** Track A harness implementing Appendix C in full (**G-01**)
  - [ ] Scenario runner: 4 scenarios × 5 replicates, randomised order
  - [ ] Idle baseline capture + between-replicate re-verification
  - [ ] Host/container sampling via `sysstat` and `docker stats`
  - [ ] Provisioning latency from API-accept → SSE ready, server-side only
  - [ ] Reclamation latency from expiry → reaper expired event
  - [ ] Results log keyed by scenario/replicate/tenant/adapter/instance
  - [ ] Separate Docker and Proxmox VE runs
  - [ ] Export shaped for Jamovi (descriptives, and median alongside mean for
        both latencies, as the paper's Data Analysis section requires)
  - [ ] Stamp every record with the provider adapter **and** the host
        specification, and **refuse reference-grade output under the
        VirtualBox adapter** — demo runs are quarantined, never reported as
        Track A (**G-11**)
- [ ] **W1.2** Committed evaluation deployment profile (**G-05**)
- [ ] **W1.3** ISO/IEC 25010 instrument, 8 sub-scales + demographics (**G-02**)
  - [ ] Item bank adapted from Dela Rosa & Abad (2025)
  - [ ] I-CVI / S-CVI scoring sheet (Yusoff, 2019)
  - [ ] Cronbach's alpha sheet per sub-scale, 0.70 floor (Taber, 2018)
  - [ ] Fixed interpretation bands

### W2 — Contract conformance

- [ ] **W2.1** Renumber phases → increments 1–8 everywhere (**G-03**)
- [ ] **W2.2** Make the test suite green from a clean clone (**G-06**)
- [ ] **W2.3** Resolve the autograding conflict — *awaiting decision* (**G-04**)

### W3 — Paper remediation *(author-owned, tracked here)*

- [ ] **W3.1** Add the missing Zhong et al. (2022) reference (**G-10**)
- [ ] **W3.2** Cite or cut the six uncited entries; merge the ISC2 duplicate
- [ ] **W3.3** Repair year-less citations and "et. al." throughout
- [ ] **W3.4** Fill Appendix B from registrar enrolment (**G-09**)
- [ ] **W3.5** Apply decisions from G-04, G-07, G-08

### W4 — Execution *(gated on W1)*

- [ ] **W4.1** Content validation, then pilot, then instrument revision
- [ ] **W4.2** Track A runs on the reference Proxmox VE workstation
- [ ] **W4.3** Track B sessions — three respondent groups, fixed per-role
      hands-on sequence, seeded demonstration tenant
- [ ] **W4.4** Jamovi analysis: descriptives for Track A; weighted means, SD,
      alpha, per-group disaggregation and Kruskal–Wallis for Track B

### W5 — VirtualBox demo path *(low-spec demonstration; never a measurement surface)*

Runs in parallel with W1 — it blocks nothing, and blocks on nothing. Its
purpose is a credible end-to-end demonstration on a laptop. Read **G-11**
before starting; the measurement rule there is not negotiable.

- [ ] **W5.1** VirtualBox provider adapter (`orchestration/virtualbox.py`)
  - [ ] Drive the `VBoxManage` CLI with an **injectable runner**, mirroring
        `DockerProvider` exactly, so tests use a recorded runner and CI never
        needs VirtualBox installed
  - [ ] Satisfy the `InstanceProvider` protocol: `provision()`, `destroy()`,
        optional `stop()` (ACPI power button, falling back to poweroff)
  - [ ] **Resolve the kind collision.** VirtualBox wants `kinds = ("vm",)` —
        the same kind Proxmox claims. Both are *core-owned*, so the registry's
        guard (`existing.owner_plugin != owner_plugin` → `None != None`) **does
        not fire**: the later `register_provider` call silently overwrites the
        earlier one, and which VM adapter you get depends on registration
        order in `orchestration/__init__.py`. Make the two **mutually exclusive
        by configuration**, with an explicit startup guard that refuses to boot
        when both `PALESTRIX_PROXMOX_ENABLED` and `PALESTRIX_VIRTUALBOX_ENABLED`
        are set. A silent, order-dependent winner is the worst outcome here.
  - [ ] Idempotency by instance id. VirtualBox has no Docker-style label
        mechanism, so use a deterministic VM name (`palestrix-<instance_id>`)
        plus guest properties for the mapping — a re-run provision reuses or
        replaces, never duplicates (`docs/ephemeral-lifecycle.md`)
  - [ ] Fill the access fields (host/port/proto) via a per-instance NAT
        port-forward rule, since an internal network gives the host no route in
  - [ ] Emit progress through `add_log` so the SSE stream behaves identically
        to Docker and Proxmox — the demo must show a *real* provisioning log
  - [ ] Config in the established pattern: `virtualbox_enabled: bool = False`,
        `virtualbox_binary: str = "VBoxManage"`

#### W5.2 — Tenant isolation mapping, and its honest limits

The three adapters isolate tenants by genuinely different mechanisms:

| Adapter | Mechanism | Tenant field used |
| --- | --- | --- |
| Proxmox VE | VLAN tag on a VLAN-aware trunk bridge | `tenant.vlan_id` |
| Docker | `net-<tenant_id>` bridge with `--subnet` | `tenant.network_cidr` |
| VirtualBox | internal network, no host NIC path | *neither* |

- [ ] Map each tenant to a VirtualBox **internal network**
      (`--intnet palestrix-<tenant_id>`), which carries no path to the host
      NIC at all
- [ ] Treat `tenant.vlan_id` as **not applicable** under VirtualBox — leave it
      null and surface it as such. A demo must never imply that VLAN-backed
      isolation was demonstrated when it was not. An internal network is
      arguably *stricter* (traffic never reaches a physical NIC), but it does
      not trunk, does not span hosts, and is not what the paper describes.

- [ ] **W5.3** Low-spec demo profile
  - [ ] Reduced tenant quotas and smaller templates sized for a laptop
  - [ ] Must still visibly exercise: TTL reaper reclamation, quota admission
        *refusing and naming the blocking quota*, two-tenant isolation,
        gamification, the CTF arena, and the sandbox
  - [ ] Keep Redis, MinIO, and PostgreSQL real (all three run in containers on
        a laptop) so the demo does not quietly fall back to the development
        defaults flagged in **G-05**

- [ ] **W5.4** `docs/demo-virtualbox.md` runbook — host prerequisites, the
      mutual-exclusion switch, seeding the demonstration tenant, and an ordered
      walkthrough. State at the top that this path produces **no reportable
      performance data**.

- [ ] **W5.5** Adapter tests in `test_orchestration.py`, recorded-runner style:
      provision/stop/destroy, idempotent re-provision, internal-network
      attachment, and the both-adapters-enabled startup refusal

- [ ] **W5.6** Paper amendments for **G-11** (authors) — Table 1, Scope,
      Delimitations, Table 2

### Out of scope (decided)

**Appendix A figure capture.** The 10 interface plates are handled outside the
repository; no scripted screenshot pipeline will be built.

---

## 7. Definition of done

An increment is closed only when **the whole accumulated suite passes**, not
just its own tests — the paper's criterion, and it binds this repo.

A W-item is done when: the code is committed and pushed; the full suite is
green from a clean clone; this file's checkbox is ticked; and the progress log
below carries a dated entry.

---

## 8. Conventions for models working here

1. **Read this file first. Update it last.** An untracked change is a change
   the next model will undo.
2. **Never force-push `archive`.** It is the only copy of the pre-replan state.
3. **Do not act on a `DECIDE` item.** Surface it and stop.
4. **Verify before asserting.** Every claim in §2 carries a command. Run it —
   figures drift.
5. **The paper is the contract** (§1), within its two stated exceptions.
6. Run `pip install -e plugins/palestrix-provider-demo` before trusting any
   test result, until **G-06** closes.

---

## 9. Progress log

Newest first. One entry per session: what changed, what was verified, what is
now blocked.

### 2026-09-14 — VirtualBox demo path added to scope

- Authors directed a **VirtualBox demo path for low-spec machines**, with
  Proxmox VE remaining the final and reference deployment. Opened **G-11** and
  workstream **W5**.
- VirtualBox is absent from the paper, so this propagates into the document:
  Table 1, Scope, Delimitations, and Table 2 all need amending (**W5.6**).
- Established the measurement rule: **no VirtualBox telemetry is reportable as
  Track A data**. Added a matching guardrail to W1.1 — the harness stamps
  adapter and host spec, and refuses reference-grade output under VirtualBox.
- Verified a design hazard before planning around it: VirtualBox needs the
  `vm` kind that Proxmox already claims, and because both are core-owned the
  registry's conflict guard never fires — the later registration silently wins.
  W5.1 therefore requires config-level mutual exclusion and a startup refusal.
- Recorded that tenant isolation has no VLAN analogue under VirtualBox;
  `tenant.vlan_id` is not-applicable there and must not imply otherwise.
- **Assumption to confirm:** Track A *and* Track B both stay on Proxmox; the
  VirtualBox path is for development and demonstration only.
- **Next:** unchanged — W1.1 harness, then W1.3 instrument. W5 runs in parallel.

### 2026-09-14 — Re-plan established

- Cut branch `archive` @ `e008971` and pushed it; full pre-replan state
  preserved.
- Read the contract document end to end, including its two tracked comments.
- Audited repo against it: all 8 paper increments functionally built.
- Verified suite: **97 passed** after installing the reference plugin;
  4 apparent failures traced to entry-point discovery, not defects (**G-06**).
- Confirmed by search that the Track A harness and the ISO 25010 instrument do
  not exist in any form.
- Traced autograding → Canvas passback and found it load-bearing for
  Objective 7 (**G-04**).
- Verified reference-list defects against the body, incl. the missing Zhong
  et al. (2022) (**G-10**).
- Opened ten ledger items; three need an author decision.
- **Blocked on:** G-04, G-07, G-08 decisions; G-09 registrar figure.
- **Next:** W1.1 harness, then W1.3 instrument.

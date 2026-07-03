# Malware Sandbox: Security Model

The sandbox is a **separate, self-contained module** that detonates
student-submitted samples and streams file-system and network behavior to the
UI. It is the most dangerous component in the platform, so its design
assumption is: *the sample will escape the container; the blast radius must
already be contained when it does.*

## Implementation status (Phase 6)

This document is the full security target. What ships in the repository is the
**platform half** — the API contract, the analysis pipeline, and the detonator
abstraction — with the isolated detonation host left to a deployment, exactly
as the placement rules below require.

- **Detonator abstraction** (`backend/palestrix/sandbox/`): a registry that
  mirrors the Phase 4 provider pattern. The built-in **demo detonator** runs
  the real static pre-check and a clearly-labelled *simulated* dynamic trace —
  it never executes a sample, so it is safe on any host and is the dev/test
  default. Setting `PALESTRIX_SANDBOX_COORDINATOR_URL` registers the
  **coordinator detonator**, which submits bytes to `sandbox-01` over the one
  permitted port and returns the structured result; the core process never
  touches the detonation container, the fake-internet bridge, or the raw pcap.
- **Real, shipped today:** static pre-check (magic-byte typing, Shannon
  entropy / packing heuristic, ASCII+UTF-16 string extraction, URL/IP/domain
  IOC extraction, EICAR detection); verdict scoring with threat score, family,
  MITRE ATT&CK ids, and an SOC-handoff summary; the behavior-event timeline and
  its SSE stream; samples and report artifacts **sealed at rest** so a host AV
  cannot quarantine them (the "encrypted-at-rest" control below); report
  privacy (submitter-only until shared with the tenant); raw samples never
  served and artifact **export gated to admins**; the `sandbox.report.ready`
  event.
- **Deployment-provided (the coordinator implements against this contract):**
  the hardened detonation container (gVisor/Kata, seccomp, `cap-drop=ALL`,
  read-only image, wall-clock kill), INetSim/FakeNet + tcpdump instrumentation,
  live process-tree/memory analysis, the interactive debugger, TLS/SSL
  decryption, and the AI threat summary. These are behaviors of the isolated
  host, surfaced through the same report/event shapes the demo detonator fills.

## Placement

- **Baremetal (Use Case A):** a dedicated physical host (`sandbox-01`) on
  its own VLAN. The switch ACL permits exactly one flow: the core API's
  submission/result exchange over a single TCP port to the sandbox
  coordinator. No route to tenant networks, the management network, or the
  campus network.
- **Cloud (Use Case B):** a dedicated node group with taints so nothing else
  schedules there, in its own subnet with a security group that mirrors the
  VLAN ACL above; for stronger separation, a separate account with a single
  cross-account queue.

## Detonation container hardening

Each analysis runs in a fresh container that is destroyed afterward:

| Control | Setting |
|---|---|
| User | non-root, `no-new-privileges` |
| Capabilities | `--cap-drop=ALL` |
| Filesystem | read-only image, tmpfs work dir, no host mounts |
| Syscalls | strict seccomp profile, AppArmor/SELinux enforcing |
| Resources | CPU, memory, pids limits (fork-bomb proof) |
| Time | hard wall-clock kill (default 5 min) |
| Network | attached only to an instrumented internal bridge (below) |
| Runtime | prefer gVisor (`runsc`) or Kata containers over runc for kernel-boundary insulation |

Windows-behavior samples run in a disposable VM on the sandbox host
(KVM, snapshot-revert after each run), same network rules.

## Network instrumentation ("fake internet")

Samples want to phone home; we let them think they can:
- HTTP requests, DNS queries, and C2 connections are tracked live. The network layer performs **automatic TLS and SSL decryption** to uncover hidden threats without breaking the sandbox illusion.
- The detonation bridge routes to **INetSim** (or FakeNet-NG): fake DNS,
  HTTP/S, SMTP responders record every request without letting traffic out.
- A capture container runs `tcpdump` on the bridge; the coordinator parses
  the pcap into the network-event table shown in the UI.
- Absolute egress rule at the host firewall: the sandbox VLAN/subnet has
  **no default route**. Even a full container escape lands on a host that
  cannot reach anything but the coordinator port.

## Process, Memory, & File-System Instrumentation

- **Live Interactivity & Process Tree:** The UI streams a live view of all processes organized in a tree structure. Analysts can click files, open archives, and trigger payloads manually.
- **Automated Interactivity:** For API submissions, the sandbox uses automated routines to detonate threats from initial stage to final payload, providing hints for manual detonation.
- **Memory Analysis:** Real-time process memory dumps decode configuration strings (extracting C2s from known malware families) on the fly.
- **Static Analysis Pre-check:** Before execution, files undergo deep static analysis (previewing PDF headers, HEX, pulling metadata/IOCs from MSG/Email/Office embeds) without executing the code.
- **Built-in Debugger:** Allows for live reverse-engineering of samples within the browser view.
- The overlay diff after detonation is archived to object storage, allowing analysts to pull dropped artifacts later.

## Handling rules (platform policy)

- **SOC-Ready Reports:** Telemetry is compiled into a Visual Process Graph, mapped to MITRE ATT&CK TTPs, and summarized via an **AI Threat Summary** for fast handoff. 
- **Export & Integrations:** Analysts can export triggered detection rules directly to MISP, download JSON summaries, or leverage the platform's API and SDK for automated submission.
- **Data Privacy & Storage:** Samples are stored encrypted-at-rest (`sandbox-reports`), named by SHA-256. Workspaces have strict privacy bounds; reports are private to the submitter's team unless shared.
- Downloads of raw malware back out of the platform are disabled for Students. Admins can export password-protected archives (`infected` convention).
- **Workspace Analytics:** Team leads can track analysis completion, manage shared VM presets, and monitor openVPN settings.

## What the sandbox module never gets

- Platform database credentials (it has its own result queue credential).
- Tenant network routes.
- The object-storage root key (a scoped key for its two buckets only).
- Inbound connections from anywhere but the core API.

## Abuse cases considered

| Abuse | Mitigation |
|---|---|
| Student detonates ransomware hoping to hit the range | No route from sandbox to tenants; fresh container per run |
| Sample fingerprints the sandbox and sleeps | Configurable clock skew, INetSim responses, longer reruns by teachers |
| Student uses sandbox as a malware dropbox for classmates | Downloads disabled for students; SHA-256 dedup flags resubmissions |
| Crypto-mining in detonation time | Hard 5-minute wall clock and CPU quota make it pointless |
| Escape to host | Non-root + seccomp + gVisor/Kata; host itself is on a dead-end network |

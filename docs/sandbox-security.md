# Malware Sandbox: Security Model

The sandbox is a **separate, self-contained module** that detonates
student-submitted samples and streams file-system and network behavior to the
UI. It is the most dangerous component in the platform, so its design
assumption is: *the sample will escape the container; the blast radius must
already be contained when it does.*

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

- The detonation bridge routes to **INetSim** (or FakeNet-NG): fake DNS,
  HTTP/S, SMTP responders record every request without letting traffic out.
- A capture container runs `tcpdump` on the bridge; the coordinator parses
  the pcap into the network-event table shown in the UI.
- Absolute egress rule at the host firewall: the sandbox VLAN/subnet has
  **no default route**. Even a full container escape lands on a host that
  cannot reach anything but the coordinator port.

## File-system instrumentation

- The agent traces syscalls (eBPF on Linux; Sysmon in the Windows VM) and
  emits create/write/delete/registry events with pid and path.
- The overlay diff after detonation is archived to object storage with the
  report, so analysts can pull dropped artifacts later.

## Handling rules (platform policy)

- Samples are stored encrypted-at-rest in a dedicated bucket
  (`sandbox-reports`), named by SHA-256, never by original filename.
- Downloads back out of the platform are disabled for Students; teachers and
  admins can export a password-protected archive (classic `infected`
  convention) with an audit log entry.
- Reports are private to the submitter; Administrators can view all reports
  (see rbac-matrix.md).
- Retention: raw samples 90 days, reports 1 year, then lifecycle-deleted.

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

# PalestrIX sandbox coordinator

The deployment half of the malware sandbox. `backend/palestrix/sandbox/` ships
the platform half — the detonator abstraction, static pre-check, verdict
storage and the behaviour-event stream — and calls out to *this* service for
live detonation. See [docs/sandbox-security.md](../docs/sandbox-security.md).

One request is one throwaway Windows VM:

```
POST /detonate  (multipart: sample, sha256, filename; Bearer auth)
  -> build payload ISO containing the sample + run.bat
  -> clone the Windows template to a fresh VMID
  -> pin net0 to the air-gapped bridge, attach the ISO, start
  -> tcpdump the clone's tap for the detonation window
  -> console screenshot, hard stop, destroy the clone
  -> parse pcap into network events + IOCs, score, answer JSON
```

The clone is destroyed in a `finally` block. A leaked clone is a live malware
host, so teardown never depends on the happy path.

## The wall clock

`SBX_WALL_CLOCK_SECONDS` (default 300, matching the 5-minute kill
[docs/sandbox-security.md](../docs/sandbox-security.md) promises) is a hard
ceiling on how long a clone may stay alive. It is measured from the top of the
run, so a slow ISO build or clone eats into the detonation window rather than
extending the run past the cap — which is what makes it worth anything as the
anti-cryptomining control the threat model leans on. When the ceiling truncates
the window the run says so in a `warn` event instead of silently running short.

Keep it under the platform's `PALESTRIX_SANDBOX_COORDINATOR_TIMEOUT_SECONDS`,
which is itself under the detonation job's RQ timeout. Each layer needs
headroom over the one below, or the outer one kills a run the inner one was
about to finish.

## Why the capture works with no network

The sandbox bridge has no gateway, no SNAT and no DHCP, so nothing a sample
sends is ever answered. That is the point: an unanswered SYN still names the
C2 it wanted, and a DNS question still names the domain. Every network finding
is derived from what the sample *attempted*.

## Requirements on the sandbox host

| Need | Why |
|---|---|
| `qm` (Proxmox) | clone / start / stop / destroy |
| `tcpdump` | capture on `tap<vmid>i0` |
| `genisoimage` | build the payload ISO |
| `scapy` (pip) | parse the pcap |
| `imagemagick` or `netpbm` | optional: PPM console grab to PNG |

## Template prerequisites

The template (default VMID 900) must be a **fully installed** Windows that
boots straight to a desktop with no password prompt, and it needs one hook so
the payload ISO actually runs. Inside the template, once, as the autologon
user:

```bat
schtasks /create /tn "PalestrIXRunner" /rl highest /sc onlogon /f ^
  /tr "cmd /c if exist D:\run.bat (D:\run.bat)"
```

Then shut down and `qm template 900`.

Defender must be off in the template or it will quarantine samples before they
execute, and the run will look falsely inert.

## Install

```sh
mkdir -p /opt/palestrix-sandbox-coordinator
cp -r coordinator env.example /opt/palestrix-sandbox-coordinator/
cd /opt/palestrix-sandbox-coordinator
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp env.example .env && chmod 600 .env   # set SBX_AUTH_TOKEN
install -m644 systemd/palestrix-sandbox-coordinator.service /etc/systemd/system/
systemctl enable --now palestrix-sandbox-coordinator
```

Then point the platform at it (in the platform guest's `backend/.env`):

```ini
PALESTRIX_SANDBOX_COORDINATOR_URL=http://<sandbox-host>:8900
PALESTRIX_SANDBOX_COORDINATOR_TOKEN=<same as SBX_AUTH_TOKEN>
```

Setting those swaps the demo detonator for the coordinator automatically.

## What this does and does not give you

**Implemented:** real execution in a disposable VM; full packet capture; DNS
questions, TCP/UDP connection attempts, cleartext HTTP requests and TLS SNI;
IOC extraction from both the file and the wire; static pre-check (type,
entropy/packing, strings, EICAR); MITRE mapping (T1027, T1071.001/.004, T1571,
T1573, T1046); wall-clock kill; console screenshot; pcap archived as an
artifact.

**Not implemented — needs in-guest instrumentation:** the live process tree,
file-system and registry diffs, memory dumps and config extraction, the
interactive debugger, TLS interception. Those need an agent inside the
template (Sysmon + a log shipper is the usual first step) and would surface
through the same `process` / `file` event categories the UI already renders.

**No fake internet yet.** With no responder on the bridge, samples that need a
live C2 will stall and look inert. `docs/sandbox-security.md` calls for
INetSim/FakeNet on the same bridge; until that exists, treat a quiet verdict as
"unknown", which is exactly what `verdict.py` returns.

## Placement caveat

`docs/sandbox-security.md` wants a dedicated `sandbox-01` host. On a
single-workstation deployment this service runs as root on the same Proxmox
host that runs the platform, so a hypervisor-level escape is not contained by
the design. The guest stays air-gapped, but that is a real deviation — size it
against your threat model before detonating live samples.

# Use Case A: Single Proxmox VE Workstation (Public IP / Domain)

Run PalestrIX on one workstation you own, running **Proxmox VE 9.1.1**,
reachable from the internet through your public IP address or domain. This is
the reference deployment for a campus (or a single instructor) that owns one
capable box and wants the whole range — the platform *and* the ephemeral labs —
to live on it.

"Baremetal" here means exactly one bigger workstation. There is no cluster, no
second hypervisor, no separate management appliance, and no physical
VLAN-capable switch: Proxmox VE is the only infrastructure layer, and tenant
isolation happens inside the host's own VLAN-aware bridge. If you later outgrow
one box, the same PalestrIX configuration scales out to a Proxmox cluster
without any application changes — but nothing below assumes more than one node.

## Target topology

Everything runs on the single Proxmox VE host: the PalestrIX platform services
in one management LXC/VM, and every student's ephemeral lab as a VM or container
on the same box, isolated from each other on per-tenant VLANs.

```
Internet
   |
   |  A/AAAA records: palestrix.example.edu, *.labs.palestrix.example.edu
   v
[ Router / firewall ]  port-forward 80,443 (and a WireGuard UDP port if used)
   |
=================  ONE Proxmox VE 9.1.1 workstation  ==============================
   |
 [ platform LXC or VM ] (management network, e.g. 10.0.10.0/24)
   |   Caddy (TLS termination, routing)
   |     +-- Next.js frontend        :3000
   |     +-- FastAPI core API + worker:8000
   |   PostgreSQL 16  ·  Redis 7  ·  MinIO (S3 API + console)
   |
 [ vmbr0: VLAN-aware Linux bridge ]  802.1Q filtering in software = the isolation edge
   |     +-- tenant VLAN 100  -> ephemeral lab VMs/containers  (class A, 10.24.0.0/24)
   |     +-- tenant VLAN 101  -> ephemeral lab VMs/containers  (class B, 10.24.1.0/24)
   |     +-- sandbox VLAN 666 -> isolated detonation VM        (no route to tenants/mgmt)
   |
 [ storage ]  local-lvm (LVM-thin: VM + lab disks) · local (dir: ISOs, MinIO data, dumps)
==================================================================================
```

The platform LXC/VM sits on the management network; the ephemeral labs sit on
tenant VLANs the platform never joins. PalestrIX (Phase 7, `LocalCloud`)
allocates each tenant a VLAN tag and a /24, and the Proxmox adapter tags every
lab NIC with its tenant's tag — so isolation is enforced by the VLAN-aware
bridge on this one host, with no external switch involved.

## Hardware baseline

One workstation, sized for how many students launch labs at once. Ephemeral
labs are the load; the platform services are light.

| Role | Minimum (one section) | Comfortable (2 sections + a CTF event) |
|---|---|---|
| The workstation | 16-core, 128 GB RAM, 2 TB SSD | 24–32-core, 256 GB RAM, 4 TB NVMe or a hardware-RAID volume |
| Platform LXC/VM | 4 vCPU, 8 GB RAM, 60 GB | 8 vCPU, 16 GB RAM, 100 GB |
| Headroom for labs | the rest | the rest, sized to peak concurrent launches |
| Storage layout | the installer default: LVM-thin `local-lvm` (VM/lab disks) + `local` (ISOs, MinIO, dumps) | same, on NVMe or a RAID10/RAID6 volume — or `rpool` + a ZFS `tank` pool if the box has spare disks |
| Network | 1 GbE uplink; VLAN-aware `vmbr0` | 1–10 GbE uplink; VLAN-aware `vmbr0` |

No VLAN-capable switch is required: the tenant VLAN tags are filtered by the
host bridge, not by external hardware. A single uplink to your LAN/router is
enough.

## Layer 1: Proxmox VE (the whole hypervisor base)

1. Install **Proxmox VE 9.1.1** on the workstation from the official ISO.
   The installer's default LVM layout is the baseline here: it gives you
   `local` (a directory store for ISOs, templates and dumps) and `local-lvm`
   (an LVM-thin pool for VM and lab disks), both carved out of the system
   volume. On a box behind a hardware RAID controller — a single logical
   volume presented to the OS — this is the only sensible layout, because ZFS
   wants raw disks it owns.
2. Confirm the two storages exist and carry the right content types; nothing
   else has to be created:

   ```
   pvesm status
   pvesm set local     --content iso,vztmpl,backup,import
   pvesm set local-lvm --content images,rootdir
   ```

   Lab disks, golden templates and the platform guest all land on
   `local-lvm`; ISOs and the MinIO data directory live under `local`
   (`/var/lib/vz`).

   > **ZFS variant.** If the workstation has spare disks that Proxmox can own
   > directly, a ZFS pool is the better choice — it buys you snapshots and
   > `zfs send` replication. Install with ZFS for the system pool, then add a
   > data pool and point the storage names below at it:
   >
   > ```
   > zpool create tank mirror /dev/nvme1n1 /dev/nvme2n1
   > pvesm add zfspool tank-vm   --pool tank/vm   --content images,rootdir
   > pvesm add dir     tank-iso  --path /tank/iso --content iso
   > ```
   >
   > Everywhere this document says `local-lvm` / `local`, read `tank-vm` /
   > `tank-iso` instead, and set `PALESTRIX_PROXMOX_ISO_STORAGE` to match.

   Single node — there is no `pvecm create`/`pvecm add` step.
3. Make `vmbr0` VLAN-aware so tenant tags isolate labs in software, with no
   external switch (`/etc/network/interfaces`, then `ifreload -a`):

   ```
   auto vmbr0
   iface vmbr0 inet static
       address 10.0.10.11/24
       gateway 10.0.10.1
       bridge-ports eno1
       bridge-stp off
       bridge-fd 0
       bridge-vlan-aware yes
       bridge-vids 2-4094
   ```

   PalestrIX tags each lab's `net0` with its tenant's VLAN automatically
   (Phase 7); the VLAN-aware bridge keeps tenants on different tags from
   reaching each other. (Proxmox SDN with a VLAN zone is an equivalent, more
   declarative alternative — either works on a single host.)
4. Create an API token for the orchestration service — never use `root@pam`:

   ```
   pveum user add palestrix@pve
   pveum aclmod / -user palestrix@pve -role PVEAdmin
   # privsep 0: token inherits the user's permissions. PVEAdmin covers clone
   # + Datastore.AllocateSpace (clone disk) + Datastore.AllocateTemplate (ISO
   # upload); PVEVMAdmin alone fails clones with "403 ... Datastore.AllocateSpace".
   pveum user token add palestrix@pve orchestrator --privsep 0
   ```

   With `--privsep 1` the token's effective rights are the *intersection* of
   the user's and the token's ACLs, so you must grant the same role to both
   sides or clones hit an `AllocateSpace` 403.

   The core API consumes `PROXMOX_HOST`, `PROXMOX_TOKEN_ID`,
   `PROXMOX_TOKEN_SECRET`, and `PROXMOX_NODE` (the single node's name, `pve`
   by default) from its environment.
5. Build golden VM templates (Kali, Ubuntu server, Windows eval) from ISOs
   uploaded through the PalestrIX admin screen (which calls
   `POST /nodes/{node}/storage/{storage}/upload` on the Proxmox API). Convert
   each to a template: `qm template <vmid>`.
6. GUI labs use Proxmox's noVNC: the orchestration service requests a VNC
   ticket (`POST /nodes/{node}/qemu/{vmid}/vncproxy`) and the frontend embeds
   the console; Caddy passes the websocket through under the main domain.

## Layer 2: Tenancy (Proxmox-only, registry-driven)

There is no separate cloud-management layer on this deployment — Proxmox VE is
the only infrastructure. PalestrIX's built-in tenancy backend does everything a
single workstation needs:

Set `PALESTRIX_CLOUD_BACKEND=local` (the default). The `LocalCloud`
(`backend/palestrix/tenancy/`) is the source of truth: creating a tenant in the
admin console allocates a VLAN tag (`PALESTRIX_TENANT_VLAN_MIN..MAX`, default
100–1999) and a /24 from `PALESTRIX_TENANT_CIDR_POOL` (default `10.24.0.0/16`),
the Proxmox adapter tags each instance's `net0` with that tenant VLAN on
`PALESTRIX_PROXMOX_BRIDGE` (`vmbr0`), and the API enforces the per-tenant
instance/vCPU/RAM quotas at launch. Because `vmbr0` is VLAN-aware (Layer 1,
step 3), those tags isolate tenants inside this one host — nothing needs to be
trunked anywhere.

Creating, editing, and archiving tenants is entirely API-driven from
**Admin → Infrastructure → Tenants**: create materializes the VLAN + CIDR,
quota edits sync through, and archive is refused while the tenant still holds
active instances (its VLAN and CIDR then stay reserved forever, so instance
history can never be misread across a reused network).

> The `TenantCloud` contract also ships managed-cloud adapters (OpenNebula,
> CloudStack) for sites that front a hypervisor *fleet* with a self-service IaaS
> manager. They are out of scope for a single-workstation deployment and are
> not used here — leave `PALESTRIX_CLOUD_BACKEND=local`.

## Layer 3: Platform services

Run these in **one** management LXC or VM on the same Proxmox host (a single
Debian 12 / Ubuntu 24.04 guest is simplest; a Docker Compose stack inside it is
equally fine). None of them touch the tenant VLANs.

| Service | Software | Notes |
|---|---|---|
| Frontend | Next.js (node:22) | `npm run build && npm start`, port 3000 |
| Core API | FastAPI + uvicorn | port 8000 |
| Worker | RQ worker | `python -m palestrix.worker`; owns the TTL reaper + grade-passback retries |
| Queue/cache | Redis 7 | AOF persistence on |
| Database | PostgreSQL 16 | on its own filesystem (a ZFS dataset with `recordsize=16k` if you run ZFS); nightly `pg_dump` to MinIO |
| Object storage | MinIO | buckets: `isos`, `lab-archives`, `writeups`, `sandbox-samples`, `sandbox-reports`, `backups` |
| Edge | Caddy (or Traefik) | see Layer 4 |

## Layer 4: Edge, DNS, TLS

1. DNS: point `palestrix.example.edu` at your public IP. Add a wildcard
   `*.labs.palestrix.example.edu` only if you expose per-instance subdomains.
2. Port-forward only 80 and 443 from the router to the platform LXC/VM's
   management address.
3. Caddy example (automatic Let's Encrypt), running in the platform guest:

   ```
   palestrix.example.edu {
       handle /api/* {
           reverse_proxy 127.0.0.1:8000
       }
       handle {
           reverse_proxy 127.0.0.1:3000
       }
   }
   ```

   (Everything is co-located, so the reverse-proxy targets are localhost. If
   you split services across guests later, point them at those addresses.)
4. Instance exposure, two supported modes:
   - **GUI labs:** noVNC websocket proxied under the main domain
     (`/console/{instance}`); no extra ports opened.
   - **Headless labs:** on-campus users reach the tenant network directly
     (`10.24.x.x:port`); remote users come in through WireGuard, or you
     allocate a per-instance high port on the router with a strict forward
     rule. Prefer WireGuard: one UDP port, no dynamic firewall holes.

## Malware sandbox on one box

By default `/sandbox` works with no extra hardware: the built-in demo detonator
runs real static analysis and a clearly-labelled synthetic behavior trace, and
never executes a sample. To detonate for real, dedicate an **isolated VM on the
same Proxmox host** — put it on its own SDN/VLAN (for example VLAN 666) with a
default-deny firewall that permits only the single coordinator TCP port inbound
and no route to any tenant or the management network — and follow
[sandbox-security.md](sandbox-security.md). Point the platform at it with
`PALESTRIX_SANDBOX_COORDINATOR_URL`; the coordinator detonator then takes over.

## TTL reaper on one workstation

The reaper is owned by the worker process (every 60 s):

1. `SELECT ... WHERE expires_at < now() AND state IN ('running','stopped')`
2. For each hit: provider `stop()` then `destroy()`, release quota, emit
   `instance.expired` webhook, append ledger events.
3. A `systemd` timer on the Proxmox host runs a fallback script hourly that
   reconciles Proxmox reality against the registry (kills orphaned VMs the
   queue may have missed, marks vanished VMs expired).

## Backup and recovery

Everything is on one box, so backups must leave it:

- PostgreSQL: nightly `pg_dump` to the MinIO `backups` bucket, 14-day
  retention; weekly restore test into a scratch database.
- MinIO: `mc mirror` to an external disk or a second machine — this is the
  only copy of ISOs, archives, and reports.
- Proxmox templates: `vzdump` weekly for the golden templates only (ephemeral
  instances are never backed up, by design).
- Host state: `/etc/pve`, `/etc/network/interfaces` and the storage
  definitions to the same off-box target as the database dumps.
- On LVM-thin there is no cheap snapshot-and-replicate path, so the `pg_dump`
  and `mc mirror` copies above *are* the disaster recovery — verify them.
  (On the ZFS variant, take hourly snapshots on `tank` and `zfs send` nightly
  to an off-box target instead; that replica then becomes your recovery.)

## Hardening checklist

The first item is enforced by the application itself: set
`PALESTRIX_ENVIRONMENT=production` and the API refuses to boot while any
`production_readiness()` finding stands (dev secret, SQLite, plain-HTTP
origin, wildcard CORS, TLS verification off on Proxmox/sandbox, inline queue,
disabled reaper, local-folder storage). Everything else is site infrastructure
the app cannot see.

- [ ] `PALESTRIX_ENVIRONMENT=production` on the API and worker units; a unit
      that fails to start means a finding to fix, never a check to skip.
- [ ] Proxmox web UI (8006) and SSH reachable only from your management LAN,
      never from a tenant VLAN or the public internet.
- [ ] API token whose effective rights cover clone + `Datastore.AllocateSpace`
      (`PVEAdmin` on the user with `--privsep 0`, or the same role on **both**
      user and token under `--privsep 1`); no
      `root@pam` anywhere in config.
- [ ] `PALESTRIX_PROXMOX_VERIFY_TLS=true` with a real certificate on the host,
      or Proxmox's cluster CA pinned via `PALESTRIX_PROXMOX_CA_BUNDLE`
- [ ] `PALESTRIX_PROXMOX_HOST` uses a name the certificate carries (the node
      hostname, not its management IP)
      (the guard refuses `false` in production). Proxmox ACME or your internal
      CA both work.
- [ ] `vmbr0` is VLAN-aware and the management interface is **not** on any
      tenant VLAN; the platform LXC/VM stays on the management network only.
      Tenant VLANs default-deny east-west and to management (host firewall
      rules or SDN).
- [ ] The sandbox VM (if used) is on its own VLAN with no route to tenants or
      management (see sandbox-security.md).
- [ ] fail2ban or CrowdSec on the platform guest running Caddy.
- [ ] Automatic security updates on the platform guest; Proxmox host updates
      in a scheduled maintenance window.
- [ ] Secrets in sops or Vault, rendered to an env file readable only by the
      service user; `PALESTRIX_SECRET_KEY` unique to this site, 32+ characters.
- [ ] Caddy repeats the security headers the API already sets (nosniff,
      frame-deny, no-referrer, HSTS) — belt and suspenders; the API does not
      rely on the proxy for them.

## Acceptance test (run before calling the deployment done)

1. Register an account, enroll a passkey, sign in from a clean browser.
2. As a teacher, publish a container lab with a 30-minute TTL.
3. As a student, launch it, watch real provisioning logs stream, connect
   over SSH from the campus network.
4. Wait out the TTL: the instance must stop, be destroyed, and release quota
   without human action.
5. Submit a CTF flag; watch the leaderboard and Palestras balance update.
6. If the sandbox VM is deployed, confirm it cannot reach any tenant network
   (nmap from a detonation container).
7. Create a tenant in the admin console; verify its VLAN tag and /24 are
   allocated (registry), that a launch beyond its vCPU cap is refused naming
   the quota, and that archiving is refused while an instance runs. Confirm
   two tenants on different VLANs cannot reach each other across `vmbr0`.
8. Restart the API with `PALESTRIX_ENVIRONMENT=production` and one check
   deliberately broken (for example the dev secret); the unit must refuse to
   start and name the finding.

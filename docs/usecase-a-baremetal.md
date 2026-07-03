# Use Case A: Baremetal Deployment (Public IP / Domain)

Run PalestrIX on hardware you own, reachable from the internet through your
public IP address or domain. This is the reference deployment for a campus
that controls its own servers and storage.

## Target topology

```
Internet
   |
   |  A/AAAA records: palestrix.example.edu, *.labs.palestrix.example.edu
   v
[ Router / firewall ]  port-forward 80,443 (and a WireGuard port if used)
   |
[ Edge host or VM: Traefik or Caddy ]  TLS termination, routing
   |
   +-- app.internal      -> Next.js frontend (node or container)
   +-- api.internal      -> FastAPI core API + workers
   +-- minio.internal    -> MinIO (S3 API + console)
   +-- novnc pass-through-> Proxmox noVNC consoles (websocket)
   |
[ Proxmox VE cluster: pve-01, pve-02, ... ]
   |    ZFS pools: rpool (system), tank (VM disks, ISOs)
   |
[ OpenNebula OR CloudStack management VM ]  multitenant layer
   |
[ Isolated tenant networks: VLAN or VXLAN per class/event ]

[ sandbox-01 ]  separate host or airgapped VLAN for the malware sandbox
```

## Hardware baseline

| Role | Minimum | Comfortable (2 sections + CTF event) |
|---|---|---|
| Hypervisor nodes | 1x 16-core, 128 GB RAM, 2 TB SSD | 2x 24-core, 256 GB RAM, 4 TB NVMe (ZFS mirror) |
| Sandbox host | 4-core, 32 GB RAM | 8-core, 64 GB RAM, no shared storage |
| Storage | local ZFS | ZFS + nightly snapshots shipped off-box |
| Network | 1 GbE flat | 10 GbE between nodes, VLAN-capable switch |

## Layer 1: Proxmox VE (hypervisor base)

1. Install Proxmox VE 8.x on each node from the official ISO. Use ZFS
   (RAID1/RAIDZ) at install time for the system pool.
2. Create the data pool and ISO storage:

   ```
   zpool create tank mirror /dev/nvme1n1 /dev/nvme2n1
   pvesm add zfspool tank-vm   --pool tank/vm   --content images,rootdir
   pvesm add dir     tank-iso  --path /tank/iso --content iso
   ```

3. Cluster the nodes: `pvecm create palestrix` on node 1,
   `pvecm add <node1-ip>` on the others.
4. Create an API token for the orchestration service (never use root@pam):

   ```
   pveum user add palestrix@pve
   pveum aclmod / -user palestrix@pve -role PVEVMAdmin
   pveum user token add palestrix@pve orchestrator --privsep 1
   ```

   The core API consumes `PROXMOX_HOST`, `PROXMOX_TOKEN_ID`,
   `PROXMOX_TOKEN_SECRET` from its environment.
5. Build golden VM templates (Kali, Ubuntu server, Windows eval) from ISOs
   uploaded through the PalestrIX admin screen (which calls
   `POST /nodes/{node}/storage/{storage}/upload` on the Proxmox API). Convert
   each to a template: `qm template <vmid>`.
6. GUI labs use Proxmox's noVNC: the orchestration service requests a VNC
   ticket (`POST /nodes/{node}/qemu/{vmid}/vncproxy`) and the frontend embeds
   the console; the edge proxy passes the websocket through.

## Layer 2: Multitenant cloud layer (choose one)

Both options sit on top of the same Proxmox/KVM base and give you tenants,
quotas, and self-service inside limits. Document your choice in the site
runbook; do not run both.

PalestrIX drives this layer itself (Phase 7, `backend/palestrix/tenancy/`):
creating a tenant in the admin console materializes it end to end, editing
quotas pushes them through, and archiving tears the manager objects down.
Select the backend with `PALESTRIX_CLOUD_BACKEND=local|opennebula|cloudstack`.
The smallest deployment (one Proxmox node, a handful of sections) skips the
manager entirely and runs `local`: the registry allocates the VLAN tag
(`PALESTRIX_TENANT_VLAN_MIN..MAX`, default 100-1999) and a /24 per tenant
from `PALESTRIX_TENANT_CIDR_POOL` (default 10.24.0.0/16), the Proxmox
adapter tags every instance's `net0` with the tenant VLAN on the trunk
bridge, and the API enforces the quotas at launch. The switch ports feeding
`PALESTRIX_PROXMOX_BRIDGE` must trunk the tenant VLAN range.

### Option 1: OpenNebula

- Install the OpenNebula front-end (`opennebula`, `opennebula-sunstone`) on a
  management VM; register the Proxmox/KVM nodes as hosts.
- Model each class section or event as a **Group** plus a **VDC** (virtual
  datacenter): assign hosts, datastores, and virtual networks to the VDC.
- Quotas per group: `oneuser quota` / `onegroup quota` limit VMs, CPU, RAM,
  and storage (maps to PalestrIX tenant quotas).
- Networking: one VXLAN or VLAN-backed virtual network per tenant with
  address ranges matching PalestrIX tenant CIDRs (for example 10.24.7.0/24
  for `hau-bscs-3a`).
- PalestrIX talks to the XML-RPC API with a service account:
  `PALESTRIX_OPENNEBULA_ENDPOINT` (for example
  `http://one.internal:2633/RPC2`), `_USERNAME`, `_PASSWORD`, and
  `_PHYDEV` (the trunk device carrying the 802.1Q tags, default `bond0`).
  Per tenant it creates the group `palestrix-<tenant>`, a VLAN-backed
  virtual network `net-<tenant>` with an address range from the tenant
  CIDR, and the VDC `vdc-<tenant>`, then sets the group quota (VMS, CPU,
  MEMORY). All idempotent by name — re-running converges.

### Option 2: Apache CloudStack

- Install `cloudstack-management` + MySQL on a management VM; add the KVM
  hosts with `cloudstack-agent`.
- Model each class section or event as a **Domain** with an **Account**;
  place them in a shared or dedicated **Zone**.
- Quotas: resource limits per domain/account (instances, CPU, RAM, volumes)
  map to PalestrIX tenant quotas.
- Networking: isolated guest networks with security groups per tenant.
- PalestrIX talks to the CloudStack REST API with an API/secret key pair
  (every request HMAC-SHA1 signed): `PALESTRIX_CLOUDSTACK_ENDPOINT`
  (for example `https://cs.internal:8080/client/api`), `_API_KEY`,
  `_SECRET_KEY`, `_ZONE_ID`, and `_NETWORK_OFFERING_ID`. Per tenant it
  creates the domain `palestrix-<tenant>` with a `palestrix` account, sets
  the domain resource limits (instances, CPU, memory), and creates the
  isolated network `net-<tenant>` gatewayed on the tenant CIDR. Archiving
  issues `deleteDomain` with cleanup. Keep `_VERIFY_TLS` on — the boot
  guard flags it off in production.

## Layer 3: Platform services

Run these as containers (compose file) or as VMs on the cluster:

| Service | Software | Notes |
|---|---|---|
| Frontend | Next.js (node:22 image) | `npm run build && npm start`, port 3000 |
| Core API | FastAPI + uvicorn | port 8000, horizontal-scale ready |
| Workers | Celery or RQ | same image as API, `celery -A palestrix worker` and `celery beat` (reaper schedule) |
| Queue/cache | Redis 7 | AOF persistence on |
| Database | PostgreSQL 16 | on ZFS dataset with `recordsize=16k`; nightly `pg_dump` to MinIO |
| Object storage | MinIO | buckets: `isos`, `lab-archives`, `writeups`, `sandbox-reports` |
| Edge | Traefik or Caddy | see below |

## Layer 4: Edge, DNS, TLS

1. DNS: point `palestrix.example.edu` at your public IP. Add a wildcard
   `*.labs.palestrix.example.edu` if you expose per-instance subdomains.
2. Port-forward only 80 and 443 to the edge host.
3. Caddy example (automatic Let's Encrypt):

   ```
   palestrix.example.edu {
       handle /api/* {
           reverse_proxy api.internal:8000
       }
       handle {
           reverse_proxy app.internal:3000
       }
   }
   *.labs.palestrix.example.edu {
       reverse_proxy edge-router.internal:8081   # per-instance router
   }
   ```

4. Instance exposure, two supported modes:
   - **GUI labs:** noVNC websocket proxied under the main domain
     (`/console/{instance}`); no extra ports opened.
   - **Headless labs:** on-campus users connect to the tenant network
     directly (`10.24.x.x:port`); remote users come in through WireGuard,
     or you allocate a per-instance high port on the edge with a strict
     forward rule. Prefer WireGuard: one UDP port, no dynamic firewall holes.

## TTL reaper on baremetal

The reaper is a beat-scheduled worker (every 60 s):

1. `SELECT ... WHERE expires_at < now() AND state IN ('running','stopped')`
2. For each hit: provider `stop()` then `destroy()`, release quota, emit
   `instance.expired` webhook, append ledger events.
3. A `systemd` timer runs a fallback script hourly that reconciles Proxmox
   reality against the registry (kills orphans the queue may have missed).

## Backup and recovery

- PostgreSQL: nightly `pg_dump` to the MinIO `backups` bucket, 14-day
  retention; weekly restore test into a scratch database.
- MinIO: `mc mirror` to a second box or external disk.
- Proxmox: `vzdump` weekly for golden templates only (ephemeral instances
  are never backed up, by design).
- ZFS: hourly snapshots on `tank`, `zfs send` nightly off-box.

## Hardening checklist

The first item is enforced by the application itself: set
`PALESTRIX_ENVIRONMENT=production` and the API refuses to boot while any
`production_readiness()` finding stands (dev secret, SQLite, plain-HTTP
origin, wildcard CORS, TLS verification off on Proxmox/CloudStack/sandbox,
inline queue, disabled reaper, local-folder storage). Everything else is
site infrastructure the app cannot see.

- [ ] `PALESTRIX_ENVIRONMENT=production` on the API and worker units; a unit
      that fails to start means a finding to fix, never a check to skip.
- [ ] Proxmox web UI (8006) and SSH reachable only from the management VLAN.
- [ ] API tokens with least privilege; no root@pam anywhere in config.
- [ ] `PALESTRIX_PROXMOX_VERIFY_TLS=true` with a real certificate on the
      cluster (the guard refuses `false` in production).
- [ ] Tenant networks deny east-west traffic to other tenants and to the
      management network (default-deny, explicit allows). The tenant VLAN
      range is trunked to the hypervisors only — never to the edge host.
- [ ] Sandbox host on its own VLAN with no route to tenants or management
      (see sandbox-security.md).
- [ ] fail2ban or CrowdSec on the edge host.
- [ ] Automatic security updates on all hosts; Proxmox updates in a monthly
      maintenance window.
- [ ] Secrets in sops or Vault, rendered to an env file readable only by the
      service user; `PALESTRIX_SECRET_KEY` unique per site, 32+ characters.
- [ ] The edge proxy repeats the security headers the API already sets
      (nosniff, frame-deny, no-referrer, HSTS) — belt and suspenders; the
      API does not rely on the proxy for them.

## Acceptance test (run before calling the deployment done)

1. Register an account, enroll a passkey, sign in from a clean browser.
2. As a teacher, publish a container lab with a 30-minute TTL.
3. As a student, launch it, watch real provisioning logs stream, connect
   over SSH from the campus network.
4. Wait out the TTL: the instance must stop, be destroyed, and release quota
   without human action.
5. Submit a CTF flag; watch the leaderboard and Palestras balance update.
6. Confirm the sandbox host cannot reach any tenant network (nmap from a
   detonation container).
7. Create a tenant in the admin console; verify its VLAN and network appear
   in the cloud layer (or the registry on `local`), that a launch beyond its
   vCPU cap is refused naming the quota, and that archiving is refused while
   an instance runs.
8. Restart the API with `PALESTRIX_ENVIRONMENT=production` and one check
   deliberately broken (for example the dev secret); the unit must refuse to
   start and name the finding.

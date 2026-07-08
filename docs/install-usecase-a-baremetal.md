# Installing PalestrIX — Use Case A: Single Proxmox VE Workstation

A step-by-step installation for one workstation you own, running **Proxmox VE
9.1.1**, reachable through your own public IP or domain. Follow it top to bottom
on a fresh box; every step is a command you run or a screen you fill in. The
architecture and the *why* behind each layer live in
[usecase-a-baremetal.md](usecase-a-baremetal.md) — this document is the *how*,
in order.

**What you end up with:** one Proxmox VE host running both the PalestrIX
platform (a management LXC/VM with PostgreSQL, Redis, MinIO, the FastAPI core
API, the worker, and the Next.js frontend, fronted by Caddy with automatic TLS)
and every student's ephemeral lab — with tenants isolated on VLANs inside the
host's VLAN-aware bridge, the TTL reaper destroying expired labs, the production
boot guard armed, and (optionally) a sandbox VM and Canvas LMS wired in.

This is a single-node deployment: no cluster, no second hypervisor, no external
VLAN switch.

## Contents

1. [Prerequisites](#1-prerequisites)
2. [Network plan and DNS](#2-network-plan-and-dns)
3. [Proxmox VE](#3-proxmox-ve)
4. [The platform guest](#4-the-platform-guest)
5. [PostgreSQL](#5-postgresql)
6. [Redis](#6-redis)
7. [MinIO](#7-minio)
8. [The core API and worker](#8-the-core-api-and-worker)
9. [The frontend](#9-the-frontend)
10. [The edge proxy (Caddy)](#10-the-edge-proxy-caddy)
11. [Tenancy](#11-tenancy)
12. [The malware sandbox VM (optional)](#12-the-malware-sandbox-vm-optional)
13. [Canvas LMS (optional)](#13-canvas-lms-optional)
14. [Arm the production boot guard](#14-arm-the-production-boot-guard)
15. [Verify the deployment](#15-verify-the-deployment)
16. [Troubleshooting](#16-troubleshooting)

---

## 1. Prerequisites

| You need | Details |
|---|---|
| One workstation | See the [hardware baseline](usecase-a-baremetal.md#hardware-baseline). Minimum: 16-core / 128 GB / 2 TB SSD — hosts the platform *and* the labs |
| A domain | `palestrix.example.edu` with control over its DNS records |
| A public IP | Static, or dynamic DNS you trust; ports 80/443 forwardable |
| Proxmox VE 9.1.1 ISO | <https://www.proxmox.com/en/downloads> |
| This repository | Cloned into the platform guest in step 4 |

No VLAN-capable switch is needed — tenant VLANs are filtered inside the host's
`vmbr0` bridge (step 3.4). The platform guest below runs Debian 12 / Ubuntu
24.04 on a POSIX shell; run commands as root or with `sudo` as shown.

## 2. Network plan and DNS

1. Decide the address plan and write it down before anything else. All of it
   lives on the one host:

   | Network | Example | Purpose |
   |---|---|---|
   | Management | `10.0.10.0/24` | Proxmox UI/SSH and the platform guest — never on a tenant VLAN |
   | Tenant pool | `10.24.0.0/16` | Carved into a /24 per tenant by PalestrIX (`PALESTRIX_TENANT_CIDR_POOL`) |
   | Tenant VLANs | tags `100–1999` | One tag per tenant, allocated by PalestrIX (`PALESTRIX_TENANT_VLAN_MIN/MAX`), filtered by `vmbr0` |
   | Sandbox | `10.66.6.0/24`, VLAN 666 | The detonation VM; no route to anything else |

2. There is no switch to configure: the VLAN-aware bridge (step 3.4) isolates
   the tenant tags in software on the host. Just give the workstation a single
   uplink to your LAN/router on the management network.

3. Create the DNS records at your provider:

   ```
   palestrix.example.edu.          A     <your public IP>
   *.labs.palestrix.example.edu.  A     <your public IP>   ; optional, per-instance subdomains
   ```

4. On the router/firewall, port-forward **only** 80 and 443 to the platform
   guest's management address, plus one UDP port if you later add WireGuard for
   remote headless-lab access.

## 3. Proxmox VE

1. Install **Proxmox VE 9.1.1** from the ISO on the workstation. Choose ZFS
   (RAID1/RAIDZ, or single-disk on a modest box) for the system pool at install
   time.

2. Create the data pool and register storage (adjust device names). This pool
   holds VM disks, ISOs, and the MinIO object store:

   ```sh
   zpool create tank mirror /dev/nvme1n1 /dev/nvme2n1
   pvesm add zfspool tank-vm  --pool tank/vm  --content images,rootdir
   mkdir -p /tank/iso
   pvesm add dir     tank-iso --path /tank/iso --content iso
   ```

3. Single node — skip clustering entirely. There is no `pvecm` step; the
   default node name is `pve`.

4. Make the bridge VLAN-aware so tenant tags isolate labs on this one host,
   with no external switch (`/etc/network/interfaces`):

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

   Then `ifreload -a`. PalestrIX tags each lab's `net0` with its tenant's VLAN
   automatically (Phase 7), and the VLAN-aware bridge keeps different tags from
   reaching each other. (A Proxmox SDN VLAN zone is an equivalent alternative.)

5. Create the orchestration service account and API token — never use
   `root@pam`:

   ```sh
   pveum user add palestrix@pve
   pveum aclmod / -user palestrix@pve -role PVEVMAdmin
   pveum user token add palestrix@pve orchestrator --privsep 1
   ```

   Record the token id (`palestrix@pve!orchestrator`) and the secret it
   prints **once** — they become `PALESTRIX_PROXMOX_TOKEN_ID` and
   `PALESTRIX_PROXMOX_TOKEN_SECRET` in step 8.

6. Build golden VM templates (Kali, Ubuntu server, Windows eval): upload the
   ISOs — after step 8 you can do this from the PalestrIX admin screen, which
   forwards to `tank-iso` — install one VM per template, then:

   ```sh
   qm template <vmid>
   ```

   The template name (for example `kali-web`) is what teachers reference when
   publishing VM labs.

## 4. The platform guest

Run all the platform services in one LXC container or VM on the Proxmox host
you just installed. A VM is simplest; an LXC is lighter. Either way it lives on
the management network, never on a tenant VLAN.

1. Create the guest from the Proxmox UI (or `qm`/`pct`): 8 vCPU, 16 GB RAM,
   100 GB disk on `tank-vm`, Debian 12 or Ubuntu 24.04, `vmbr0` **untagged**
   (management network).

2. Inside the guest, install base packages:

   ```sh
   apt update && apt install -y git curl python3.12 python3.12-venv \
       postgresql-16 redis-server caddy
   ```

   (Caddy: follow <https://caddyserver.com/docs/install> if your distro has
   no package. Node.js 22: <https://github.com/nodesource/distributions>.)

3. Create the service user and clone the repository:

   ```sh
   useradd --system --create-home --shell /usr/sbin/nologin palestrix
   sudo -u palestrix git clone https://github.com/<your-org>/palestrix.git /home/palestrix/app
   ```

## 5. PostgreSQL

1. Create the role and database:

   ```sh
   sudo -u postgres psql <<'SQL'
   CREATE ROLE palestrix LOGIN PASSWORD 'CHANGE-ME-DB-PASSWORD';
   CREATE DATABASE palestrix OWNER palestrix;
   SQL
   ```

2. Keep PostgreSQL listening on localhost only (the default) — the API runs in
   the same guest.

3. Nightly backups (installs a cron job; MinIO's `mc` comes in step 7):

   ```sh
   cat > /etc/cron.d/palestrix-pgdump <<'CRON'
   15 2 * * * postgres pg_dump palestrix | gzip | /usr/local/bin/mc pipe local/backups/pg/palestrix-$(date +\%F).sql.gz
   CRON
   ```

## 6. Redis

1. Redis 7 from the distro package is fine. Turn on AOF persistence in
   `/etc/redis/redis.conf`:

   ```
   appendonly yes
   ```

2. `systemctl enable --now redis-server`. Leave it bound to localhost.

## 7. MinIO

1. Install the server and client:

   ```sh
   curl -o /usr/local/bin/minio https://dl.min.io/server/minio/release/linux-amd64/minio
   curl -o /usr/local/bin/mc    https://dl.min.io/client/mc/release/linux-amd64/mc
   chmod +x /usr/local/bin/minio /usr/local/bin/mc
   useradd --system minio && mkdir -p /srv/minio && chown minio: /srv/minio
   ```

2. Unit file `/etc/systemd/system/minio.service`:

   ```ini
   [Unit]
   Description=MinIO object storage
   After=network-online.target

   [Service]
   User=minio
   Environment=MINIO_ROOT_USER=palestrix-minio
   Environment=MINIO_ROOT_PASSWORD=CHANGE-ME-MINIO-PASSWORD
   ExecStart=/usr/local/bin/minio server /srv/minio --address 127.0.0.1:9000 --console-address 127.0.0.1:9001
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target
   ```

3. Start it and create the buckets the platform uses:

   ```sh
   systemctl enable --now minio
   mc alias set local http://127.0.0.1:9000 palestrix-minio CHANGE-ME-MINIO-PASSWORD
   mc mb local/isos local/lab-archives local/writeups \
         local/sandbox-samples local/sandbox-reports local/backups
   ```

## 8. The core API and worker

1. Python environment:

   ```sh
   sudo -u palestrix -s
   cd /home/palestrix/app/backend
   python3.12 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

2. Generate the application secret:

   ```sh
   .venv/bin/python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

3. Write `/home/palestrix/app/backend/.env` (mode `0600`, owner
   `palestrix`). This is the complete production set — every key is
   documented in [.env.example](../backend/.env.example):

   ```ini
   PALESTRIX_ENVIRONMENT=production
   PALESTRIX_SECRET_KEY=<output of step 2>

   PALESTRIX_DATABASE_URL=postgresql+psycopg://palestrix:CHANGE-ME-DB-PASSWORD@localhost:5432/palestrix

   # Passkeys bind to the public origin — must match the domain exactly.
   PALESTRIX_RP_ID=palestrix.example.edu
   PALESTRIX_ORIGIN=https://palestrix.example.edu
   PALESTRIX_CORS_ORIGINS=https://palestrix.example.edu

   PALESTRIX_STORAGE_BACKEND=minio
   PALESTRIX_MINIO_ENDPOINT=127.0.0.1:9000
   PALESTRIX_MINIO_ACCESS_KEY=palestrix-minio
   PALESTRIX_MINIO_SECRET_KEY=CHANGE-ME-MINIO-PASSWORD
   PALESTRIX_MINIO_SECURE=false

   PALESTRIX_QUEUE_BACKEND=redis
   PALESTRIX_REDIS_URL=redis://localhost:6379/0
   PALESTRIX_REAPER_ENABLED=true

   # Proxmox adapter (step 3.5): activates the "vm" lab kind. The host is this
   # same workstation, reached on the management network.
   PALESTRIX_PROXMOX_HOST=https://10.0.10.11:8006
   PALESTRIX_PROXMOX_TOKEN_ID=palestrix@pve!orchestrator
   PALESTRIX_PROXMOX_TOKEN_SECRET=<token secret>
   PALESTRIX_PROXMOX_NODE=pve
   PALESTRIX_PROXMOX_BRIDGE=vmbr0
   PALESTRIX_PROXMOX_ISO_STORAGE=tank-iso

   # Tenancy (step 11): "local" is the only backend for a single workstation.
   PALESTRIX_CLOUD_BACKEND=local
   PALESTRIX_TENANT_VLAN_MIN=100
   PALESTRIX_TENANT_VLAN_MAX=1999
   PALESTRIX_TENANT_CIDR_POOL=10.24.0.0/16
   ```

   > **Note** — production TLS to Proxmox needs a real certificate on the host;
   > the boot guard refuses `PALESTRIX_PROXMOX_VERIFY_TLS=false`. Proxmox ACME
   > integration: `pvenode acme account register` + `pvenode acme cert order`,
   > or install your internal CA in the platform guest. (`PALESTRIX_PROXMOX_HOST`
   > must then match the certificate's name.)

4. Initialize the schema. Tables are created (and later phases' columns
   migrated) automatically at every startup, so this is just the first boot.
   Do **not** run the demo seed in production — register your first account
   through the UI and promote it:

   ```sh
   .venv/bin/python - <<'PY'
   from palestrix.db import Base, engine
   import palestrix.models
   from palestrix.migrations import upgrade
   Base.metadata.create_all(bind=engine)
   upgrade(engine)
   print("schema ready")
   PY
   ```

5. Systemd unit `/etc/systemd/system/palestrix-api.service`:

   ```ini
   [Unit]
   Description=PalestrIX core API
   After=network-online.target postgresql.service redis-server.service minio.service

   [Service]
   User=palestrix
   WorkingDirectory=/home/palestrix/app/backend
   ExecStart=/home/palestrix/app/backend/.venv/bin/uvicorn palestrix.main:app --host 127.0.0.1 --port 8000 --workers 4
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target
   ```

   And `/etc/systemd/system/palestrix-worker.service` (consumes provisioning
   jobs and owns the TTL reaper + grade-passback retries):

   ```ini
   [Unit]
   Description=PalestrIX worker
   After=palestrix-api.service

   [Service]
   User=palestrix
   WorkingDirectory=/home/palestrix/app/backend
   ExecStart=/home/palestrix/app/backend/.venv/bin/python -m palestrix.worker
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target
   ```

6. Start both. The boot guard runs first — a unit that refuses to start
   names the configuration finding in its log; fix it, never bypass it:

   ```sh
   systemctl enable --now palestrix-api palestrix-worker
   journalctl -u palestrix-api -n 20   # expect: uvicorn running on 127.0.0.1:8000
   curl -s http://127.0.0.1:8000/healthz   # {"ok":true}
   ```

7. Promote your admin: register through the UI once step 10 is live, then:

   ```sh
   sudo -u postgres psql palestrix -c \
     "UPDATE users SET role='superadmin' WHERE email='you@example.edu';"
   ```

## 9. The frontend

1. Build:

   ```sh
   sudo -u palestrix -s
   cd /home/palestrix/app
   echo "NEXT_PUBLIC_PALESTRIX_API=https://palestrix.example.edu" > .env.production
   npm ci && npm run build
   ```

   > The frontend calls the API on the same public origin; Caddy (step 10)
   > routes `/api/*` to the API and everything else to Next.js, so no
   > separate API subdomain is needed.

2. Unit file `/etc/systemd/system/palestrix-frontend.service`:

   ```ini
   [Unit]
   Description=PalestrIX frontend (Next.js)
   After=network-online.target

   [Service]
   User=palestrix
   WorkingDirectory=/home/palestrix/app
   Environment=PORT=3000
   ExecStart=/usr/bin/npm start
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target
   ```

3. `systemctl enable --now palestrix-frontend`.

## 10. The edge proxy (Caddy)

1. `/etc/caddy/Caddyfile` — Caddy provisions Let's Encrypt certificates
   automatically the first time it serves the domain. Everything is co-located
   in this guest, so the targets are localhost:

   ```
   palestrix.example.edu {
       handle /api/* {
           reverse_proxy 127.0.0.1:8000
       }
       handle /healthz {
           reverse_proxy 127.0.0.1:8000
       }
       handle {
           reverse_proxy 127.0.0.1:3000
       }
   }
   ```

2. `systemctl reload caddy`, then from **outside** the network:

   ```sh
   curl -s https://palestrix.example.edu/healthz          # {"ok":true}
   curl -sI https://palestrix.example.edu | grep -i strict # HSTS from the API
   ```

3. Open `https://palestrix.example.edu`, register your account, enroll a
   passkey, and promote yourself (step 8.7).

## 11. Tenancy

`PALESTRIX_CLOUD_BACKEND=local` (already set in step 8) is the only tenancy
backend for a single workstation, and it needs no extra software: PalestrIX
allocates each tenant a VLAN tag and a /24 from the pools, the Proxmox adapter
tags instance NICs on `vmbr0`, the VLAN-aware bridge isolates them on the host,
and the API enforces the instance/vCPU/RAM quotas at launch. Create tenants in
**Admin → Infrastructure → Tenants**; each create materializes the VLAN + CIDR
on the spot.

There is no separate cloud-management layer to install on this deployment.
(The `TenantCloud` contract ships OpenNebula/CloudStack adapters for sites that
front a hypervisor fleet with a self-service IaaS manager; they are out of
scope here — leave the backend on `local`.)

## 12. The malware sandbox VM (optional)

Without any of this, `/sandbox` still works: the built-in demo detonator runs
real static analysis and a clearly labelled synthetic behavior trace. To
detonate for real, dedicate an **isolated VM on the same Proxmox host** — on
its own VLAN (for example 666, via a Proxmox SDN zone or a tagged `net0`) with a
default-deny firewall: no route to tenants or management, one permitted inbound
TCP port. Follow [sandbox-security.md](sandbox-security.md) for its isolation
requirements, then:

```ini
PALESTRIX_SANDBOX_COORDINATOR_URL=https://10.66.6.10:8443
PALESTRIX_SANDBOX_COORDINATOR_TOKEN=<shared token>
PALESTRIX_SANDBOX_COORDINATOR_VERIFY_TLS=true
```

Restart the API; the sandbox status endpoint now reports the live coordinator
instead of the demo detonator.

## 13. Canvas LMS (optional)

Full protocol details and the adapter contract:
[integrations-canvas-lms.md](integrations-canvas-lms.md). The condensed
sequence:

1. Generate the tool signing key in the platform guest and keep it in the env
   file (the boot guard refuses an empty key in production when Canvas is
   configured):

   ```sh
   cd /home/palestrix/app/backend
   .venv/bin/python -c "from cryptography.hazmat.primitives.asymmetric import rsa; from cryptography.hazmat.primitives import serialization as s; print(rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(s.Encoding.PEM, s.PrivateFormat.PKCS8, s.NoEncryption()).decode())"
   ```

2. In Canvas (**Admin → Developer keys → + LTI Key**, choose *Manual
   entry*):

   | Field | Value |
   |---|---|
   | Redirect URIs / Target link URI | `https://palestrix.example.edu/api/v1/integrations/canvas/launch` |
   | OpenID Connect initiation URL | `https://palestrix.example.edu/api/v1/integrations/canvas/login` |
   | JWK method | Public JWK URL → `https://palestrix.example.edu/api/v1/integrations/canvas/jwks` |
   | LTI Advantage services | Enable AGS (scores), NRPS (names/roles) |
   | Placements | Assignment selection, Link selection |
   | Custom fields | `canvas_course_id=$Canvas.course.id` |

   Save, flip the key to **ON**, note the client id (the number above the
   key). If the deployment is per-account, note the deployment id from the
   app installation as well.

3. Configure PalestrIX and restart the API and worker:

   ```ini
   PALESTRIX_CANVAS_ISSUER=https://canvas.example.edu
   PALESTRIX_CANVAS_CLIENT_ID=<client id>
   PALESTRIX_CANVAS_DEPLOYMENT_ID=<deployment id>      # optional but recommended
   PALESTRIX_CANVAS_TOOL_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----
   ...
   -----END PRIVATE KEY-----"
   ```

   Self-hosted Canvas serves the conventional endpoints under the issuer and
   needs nothing more. Instructure-cloud Canvas moves auth to its SSO host —
   override explicitly:

   ```ini
   PALESTRIX_CANVAS_AUTH_URL=https://sso.canvaslms.com/api/lti/authorize_redirect
   PALESTRIX_CANVAS_JWKS_URL=https://sso.canvaslms.com/api/lti/security/jwks
   PALESTRIX_CANVAS_TOKEN_URL=https://sso.canvaslms.com/login/oauth2/token
   ```

4. Verify: a teacher opens their course in PalestrIX → the **Canvas LMS**
   panel appears → link the course by its Canvas course id → **Sync
   roster** pre-provisions the students. In Canvas, add an assignment →
   *Find* → PalestrIX → pick a lab. A student clicking it lands in
   PalestrIX signed in; grading their submission in PalestrIX posts the
   score back to the Canvas gradebook.

## 14. Arm the production boot guard

Already armed — step 8 set `PALESTRIX_ENVIRONMENT=production`. Prove it
works: break one thing on purpose and watch the API refuse to start.

```sh
sudo -u palestrix sed -i 's/^PALESTRIX_QUEUE_BACKEND=redis/PALESTRIX_QUEUE_BACKEND=inline/' /home/palestrix/app/backend/.env
systemctl restart palestrix-api && sleep 2
journalctl -u palestrix-api -n 5    # expect: refusing to start: production readiness failed
sudo -u palestrix sed -i 's/^PALESTRIX_QUEUE_BACKEND=inline/PALESTRIX_QUEUE_BACKEND=redis/' /home/palestrix/app/backend/.env
systemctl restart palestrix-api
```

Then work through the [hardening checklist](usecase-a-baremetal.md#hardening-checklist)
for the items outside the app's sight (VLAN-aware bridge and firewall rules,
fail2ban, secrets handling, update policy).

## 15. Verify the deployment

Run the full [acceptance test](usecase-a-baremetal.md#acceptance-test-run-before-calling-the-deployment-done).
Abbreviated:

- [ ] Register, enroll a passkey, sign in from a clean browser.
- [ ] Publish a container lab (teacher), launch it (student), watch the log
      stream, connect to the instance.
- [ ] Let the TTL lapse; the instance is destroyed and quota released
      without human action.
- [ ] Submit a CTF flag; leaderboard and Palestras update.
- [ ] Create two tenants; confirm each gets its own VLAN + /24, that
      over-cap launches are refused naming the quota, that archive is refused
      while an instance runs, and that the two tenants cannot reach each other
      across `vmbr0`.
- [ ] The sandbox VM (if present) cannot reach tenant or management networks.
- [ ] Canvas (if wired): roster sync, deep-linked launch, grade passback
      round trip.

## 16. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| API unit exits immediately | Boot guard finding | `journalctl -u palestrix-api` names it; fix the env, don't bypass |
| Passkey enrollment fails | `PALESTRIX_RP_ID`/`_ORIGIN` don't match the browser origin | Both must be the exact public domain, https |
| Instance stuck in `provisioning` | Worker not running, or Proxmox token wrong | `systemctl status palestrix-worker`; test the token with `curl -k -H "Authorization: PVEAPIToken=<id>=<secret>" https://10.0.10.11:8006/api2/json/nodes` |
| Two tenants can reach each other | `vmbr0` not VLAN-aware, or `net0` not tagged | Confirm `bridge-vlan-aware yes` (step 3.4) and that the tenant's `vlan_id` is set in the admin console |
| Launch refused `quota_exceeded` | Tenant at instance/vCPU/RAM cap | Raise the tenant quota in the admin console, or destroy instances |
| Canvas launch: "kid not in the platform keyset" | Issuer/JWKS URL mismatch | Check `PALESTRIX_CANVAS_ISSUER` and the JWKS override for cloud Canvas |
| Canvas launch: "Account not linked yet" page | Student not in a synced roster | Teacher runs **Sync roster** on the linked course, student launches again |
| Grades stay `pending` | Canvas unreachable or AGS scope missing on the key | Row's error column (course panel) has the HTTP failure; retry after fixing |
| `500` on uploads | MinIO down or bucket missing | `systemctl status minio`; re-run the `mc mb` bucket list from step 7 |

# Student access to labs: a self-hosted NetBird overlay

Layer 2 of [lab-networking.md](lab-networking.md). Layer 1 puts every lab VM on
an isolated tenant VLAN that routes nowhere — which is the point, and also why
a student cannot reach `ssh student@10.24.0.165` from their laptop. This
document builds the way in.

The lab page's **"How do I connect?"** modal renders from
`GET /instances/access`, which reads the `PALESTRIX_NETBIRD_*` settings at the
bottom of this page. Configure those and students get the instructions
automatically; leave them empty and the modal says remote access is not set up
rather than printing steps that cannot work.

---

## Why an overlay rather than a port-forward

The obvious alternative — forward a port per lab — fails on its own terms.
Instances are ephemeral and get a fresh DHCP address every launch, there are as
many of them as there are students, and every forward is a hole straight into
a VLAN whose entire purpose is to have no holes. An overlay inverts it: the
student's device joins a private network, one peer advertises the lab subnets,
and nothing is exposed publicly at all.

## What this site already has

Measured, not assumed:

| Fact | Value |
|------|-------|
| Public IP | `122.3.149.244` — and it is also the hosts' egress IP |
| CGNAT? | **No.** The A record and the egress IP are the same address |
| Inbound forwarding | Works — 443/TCP already reaches the reverse proxy |
| HTTPS ingress | Router 443 → LXC 117 `reverse-proxy` (`192.168.3.4`, openresty + Let's Encrypt) |
| Separate path | `*.ssecka.tech` rides a cloudflared tunnel on pve2, bypassing that proxy |
| Lab subnets | `10.24.0.0/16`, carved `/24` per tenant (`demo-account` = VLAN 100, `10.24.0.0/24`) |

> An earlier draft of Layer 2 assumed CGNAT and specified a WireGuard relay on
> EC2 to work around it. That premise is wrong for this site: there is a
> routable public IP and working inbound forwarding, so the relay is
> unnecessary and self-hosting NetBird here is strictly simpler.

## Before you build: one public IP, two NetBird servers

There is already a `netbird-server` VM on the *other* Proxmox
(`pve.hausoc.org`). This document builds a **separate** one for PalestrIX, but
be deliberate about the collision: both want the same well-known ports behind
**one** public IP, and a port can be forwarded to exactly one host.

**Settled: a separate server on a different UDP port.** The old deployment is
left alone, and this one takes `3479/UDP` instead of `3478`.

It is one port rather than a translated pair. `getting-started.sh` maps the
STUN port straight through (`$PORT:$PORT/udp`) and advertises the same number
to peers, so 3479 inside, 3479 outside and 3479 in the forward is simpler than
forwarding `:3479` to `:3478` — and it removes the mismatch where peers are
told to dial a port the forward does not answer on.

The TCP side needs no new forward at all: openresty routes by `server_name`,
so `netbird.hausoc.org` is one more vhost on LXC 117 beside the others.

> Measured on 2026-09-22, before building: nothing on `192.168.3.0/24` was
> listening on 33073 (management), 10000 (signal) or 3478 (STUN) — only the
> router, the reverse proxy, csiagym and `.107`, on 80/443. The old
> `netbird-server` appears to be stopped rather than serving. It is still left
> untouched, because "stopped today" is not "retired".

## The VM — built

Built 2026-09-22 on pve2 (`socproxmoxa`), where the labs are: the control
plane should be near the subnets it serves.

| | |
|---|---|
| VMID / name | `203` / `netbird-labs`, distinct from the existing `netbird-server` |
| OS | Debian 12 (full clone of the `debian12-min` template, VMID 8001) |
| Size | 2 vCPU, 4 GB RAM, 20 GB disk |
| NIC | `vmbr0` (LAN) — reachable from the router, which forwards UDP to it |
| Address | `192.168.3.30/24`, gw `192.168.3.1`, static |
| Login | `sysop`, key `/root/.ssh/palestrix_prov` on pve2 |

The address is static on purpose: a router forward needs a target that does not
move. **Exclude `192.168.3.30` from the router's DHCP pool** if it is not
already outside it — a lease handed to some other device would silently break
the overlay.

It has **no** leg on a tenant VLAN. It is the control plane; the routing peer
is a separate role (below).

Rebuild, if it ever comes to that:

```sh
qm clone 8001 203 --name netbird-labs --full true --storage local-lvm
qm set 203 --cores 2 --memory 4096 --agent enabled=1 --net0 virtio,bridge=vmbr0
qm set 203 --ipconfig0 ip=192.168.3.30/24,gw=192.168.3.1 --nameserver "1.1.1.1 8.8.8.8"
qm set 203 --ciuser sysop --sshkeys /root/.ssh/palestrix_prov.pub
qm resize 203 scsi0 20G && qm start 203
```

## Install — done

Two things the previous draft got wrong, both found by checking upstream
instead of trusting it:

- **The Zitadel quickstart is retired.** `getting-started-with-zitadel.sh` now
  exits 1 with a notice. The current installer is `getting-started.sh`, which
  ships an embedded Dex identity provider, so no separate IdP is needed.
- **There is no TURN relay port range to forward.** In 0.79.0 the relay is
  multiplexed onto the management port and advertised as
  `rels://netbird.hausoc.org:443` — it rides TCP 443 through openresty. Only
  **one** UDP port needs a forward.

Installed with Docker CE from the upstream Debian repo, then:

```sh
cd /opt/netbird
curl -sSL https://github.com/netbirdio/netbird/releases/latest/download/getting-started.sh -o getting-started.sh
chmod +x getting-started.sh
NETBIRD_DOMAIN=netbird.hausoc.org NETBIRD_NON_INTERACTIVE=true NETBIRD_REVERSE_PROXY_TYPE=2 NETBIRD_BIND_LOCALHOST_ONLY=false NETBIRD_HTTP_PROTOCOL=https NETBIRD_PORT=443   sudo -E ./getting-started.sh
```

`REVERSE_PROXY_TYPE=2` is the Nginx option — openresty is nginx, so the
generated template applies. `BIND_LOCALHOST_ONLY=false` matters: the default
binds `127.0.0.1` only, and our proxy is on a *different host*, so it could
never reach the ports. `HTTP_PROTOCOL=https` with `PORT=443` sets the public
URL that gets baked into the dashboard and the advertised peer config; TLS
itself is openresty's job.

Both containers carry `restart: unless-stopped` and docker is enabled, so the
stack comes back by itself after a reboot.

### The STUN port is not an installer knob

`NETBIRD_STUN_PORT` looks like one but is not: the installer assigns its own
default (3478) unconditionally, overwriting anything exported. Getting 3479
took editing the two generated files and recreating:

```sh
cd /opt/netbird
sudo sed -i 's/- 3478$/- 3479/' config.yaml               # advertised to peers
sed -i "s|'3478:3478/udp'|'3479:3479/udp'|" docker-compose.yml  # the binding
sudo docker compose up -d --force-recreate
```

Both had to change together. `config.yaml`'s `stunPorts` is what management
hands out to clients, and the compose mapping is what actually listens — set
only one and peers dial a port nothing answers on. Re-running the installer
will reset both, so redo this after any upgrade.

Resulting state, verified:

| | |
|---|---|
| Version | NetBird 0.79.0 |
| Dashboard | `192.168.3.30:8080` → 200 |
| Server (management + signal + relay + OIDC) | `192.168.3.30:8081` → 200 on `/oauth2/.well-known/openid-configuration` |
| STUN | listening on `0.0.0.0:3479/udp` |
| Relay | `rels://netbird.hausoc.org:443`, multiplexed on the management port |

## Still to do: DNS, one forward, one vhost

The overlay does not answer until these three exist. Nothing on the VM needs
touching for them.

1. **DNS.** `netbird.hausoc.org` → `122.3.149.244`. It did not resolve as of
   this build.
2. **Router forward.** `3479/UDP` → `192.168.3.30:3479`, straight through, no
   translation. This is the only forward required, and the only thing
   openresty cannot carry — it proxies HTTP(S), and STUN is UDP.
3. **openresty vhost** on LXC 117 (`192.168.3.4`) for `netbird.hausoc.org`,
   terminating TLS and proxying to the VM. The installer wrote a template to
   `/opt/netbird/nginx-netbird.conf`, but its upstreams point at `127.0.0.1`
   because it assumes nginx is on the same host. On LXC 117 they must be:

   ```nginx
   upstream netbird_dashboard { server 192.168.3.30:8080; keepalive 10; }
   upstream netbird_server    { server 192.168.3.30:8081; }
   ```

   Take the rest of the vhost from that template as generated. It already has
   the parts that are easy to get wrong: `grpc_pass` for the management and
   signal services, WebSocket upgrade on `/relay`, and day-long read timeouts
   for the long-lived gRPC streams.

## The routing peer: how students reach `10.24.0.0/16`

A NetBird peer can advertise subnets to the rest of the network. That peer is
what bridges the overlay into the tenant VLANs, and **it should be the lab
gateway**, not the Proxmox host.

> **Not yet possible here.** As of 2026-09-22 pve2 has no lab gateway VM —
> `qm list` shows 100-102, 200-202, 900 and the 8001 template, and nothing
> else. So the control plane below is up but there is no routing peer, and the
> overlay therefore carries no path to `10.24.0.0/16` yet. Build the gateway
> from [lab-gateway-vm.md](lab-gateway-vm.md) first; this is the step that
> makes the overlay actually useful.

If you have built the router VM from [lab-gateway-vm.md](lab-gateway-vm.md),
install the NetBird agent there — it already terminates every tenant VLAN, so
it is the natural place. If the gateways are still on the Proxmox host, note
what you are choosing: installing the agent there puts a routing peer on the
hypervisor, and an overlay misconfiguration then reaches the machine the whole
range runs on. That is a good reason to build the router VM first.

On the chosen peer:

```sh
netbird up --management-url https://netbird.hausoc.org --setup-key <key>
```

That URL is the public one, so it only works once DNS and the openresty vhost
are in place. Setup keys come from the dashboard at
`https://netbird.hausoc.org/setup-keys`, once it is reachable.

Then, in the NetBird dashboard, add a **Network Route**:

| Field | Value |
|-------|-------|
| Network range | `10.24.0.0/16` (the whole tenant pool, so new tenants need no new route) |
| Routing peer | the lab gateway |
| Distribution group | the student group |
| Masquerade | on — lab VMs have no route back to overlay addresses |

Masquerade matters: without it the lab VM replies to an overlay source address
it has no route to, and the connection hangs rather than fails, which is a
miserable thing to debug.

## Access control

Default-deny, then one rule. In NetBird's Access Control:

- Group `students` → group `lab-gateways`, protocol TCP, port 22.
- Nothing else. Students do not need to reach each other, and they certainly
  do not need the control plane.

The Layer 1 firewall still applies underneath: even a student on the overlay
cannot reach `192.168.3.0/24` or `10.0.10.0/24`, because the gateway drops it.
The overlay grants a path to the labs, not to the site.

## Point PalestrIX at it

In the backend `.env`, then restart `palestrix-api` and `palestrix-worker`:

```
PALESTRIX_NETBIRD_MANAGEMENT_URL=https://netbird.hausoc.org
PALESTRIX_NETBIRD_NETWORK_NAME=palestrix-labs
PALESTRIX_NETBIRD_SETUP_KEY_URL=https://netbird.hausoc.org/setup-keys
```

`PALESTRIX_NETBIRD_DOCS_URL` defaults to NetBird's own getting-started page and
only needs setting if you write your own.

These are read by `GET /instances/access` and rendered in the lab page's
connection modal. Nothing here is a secret: the platform never calls NetBird,
and the setup key is issued to the student by NetBird's own console.

**Set these last**, after DNS and the vhost resolve. Filling them in early is
worse than leaving them empty: the modal would hand students a management URL
that does not answer, where an empty setting correctly tells them remote
access is not set up yet. They are still unset as of this build.

## Verification

1. A student device runs `netbird status` and shows connected, with the lab
   gateway among its peers.
2. From that device, `ssh student@<lab ip>` succeeds while the lab is running.
3. From that same device, `192.168.3.6:8006` and `10.0.10.12:80` are still
   **unreachable** — the overlay must not have widened Layer 1.
4. With NetBird disconnected, the lab address is unreachable again.
5. On the lab page, "How do I connect?" shows your management URL rather than
   the not-configured message.

Step 3 is the one worth repeating after any routing change. It is the property
that lets you hand students root on a lab machine.

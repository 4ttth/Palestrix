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

Pick one before you start:

- **Different external ports** for the new server (e.g. forward `:3479/UDP`
  externally to `:3478` internally), and a different hostname on the reverse
  proxy. Workable, slightly awkward to document to students.
- **Reuse the existing deployment** and give PalestrIX its own NetBird *group*
  and network routes rather than its own server. Least infrastructure, but the
  student overlay then shares a control plane with the SOC range.
- **Retire the old one** if it is not in active use.

Nothing below works until this is settled, because the port forwards are the
part that cannot be shared.

## The VM

On pve2 (`socproxmoxa`), where the labs are — the routing peer should be near
the subnets it advertises.

| | |
|---|---|
| OS | Debian 12 |
| Size | 2 vCPU, 4 GB RAM, 20 GB disk |
| NIC | `vmbr0` (LAN) — it needs to be reachable from the router for its forwards |
| Name | `netbird-labs`, to keep it distinct from the existing `netbird-server` |

It must **not** get a leg on a tenant VLAN. It is the control plane; the
routing peer is a separate role (below).

## Install

NetBird's self-hosted quickstart brings up management, signal, the dashboard,
a TURN server and an identity provider together. Follow the upstream guide
rather than a copy of it here — it changes, and a stale transcription is worse
than a link:

<https://docs.netbird.io/selfhosted/selfhosted-quickstart>

What it will ask you for, and what this site's answers are:

- **A domain**, e.g. `netbird.hausoc.org`. Point it at `122.3.149.244`.
- **TLS.** The installer can obtain Let's Encrypt certificates itself, which
  needs 80/443 reaching *this* VM. Your 443 currently goes to LXC 117, so
  either add a proxy host there for `netbird.hausoc.org` and let openresty
  terminate TLS, or move the forward. The proxy route is less disruptive.
- **Ports.** Confirm the current list against upstream, but expect roughly:
  `443/TCP` (dashboard, management, signal), `3478/UDP` (STUN/TURN) and a
  TURN relay range. **Only the UDP ones need a genuine router forward** — the
  HTTP side can sit behind openresty like everything else.

> openresty cannot carry STUN/TURN. It proxies HTTP(S); those are UDP and
> need their own forward. This is the same constraint that stopped the
> reverse proxy from being an answer for WireGuard.

## The routing peer: how students reach `10.24.0.0/16`

A NetBird peer can advertise subnets to the rest of the network. That peer is
what bridges the overlay into the tenant VLANs, and **it should be the lab
gateway**, not the Proxmox host.

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

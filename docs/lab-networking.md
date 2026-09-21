# Lab networking: isolation, DHCP, and student VPN access

How a student on the internet reaches a lab VM's private IP over SSH while
**never** touching the Proxmox management network, the platform host, or the
campus/home WAN — and how to do it from behind CGNAT with a small cloud relay.

This is the deployment counterpart to the tenancy model in
[ephemeral-lifecycle.md](ephemeral-lifecycle.md): PalestrIX allocates each
tenant a VLAN tag and a `/24`, and the Proxmox adapter tags each instance's
`net0` with that VLAN. This document supplies the two pieces the platform
does **not** provide because they live in the network, not the app:

1. an isolated lab network with **DHCP + a gateway per tenant VLAN** (fixes
   the "instance comes up on a `169.254.x` APIPA address" symptom), and
2. a **WireGuard** path from students to those private IPs, relayed through a
   cheap cloud instance so it works behind CGNAT.

> **Why APIPA happened.** A VM whose NIC is tagged onto a VLAN with no DHCP
> server never gets a lease, so it self-assigns a `169.254.0.0/16`
> (APIPA / link-local) address — unroutable. PalestrIX now refuses to publish
> a link-local address as the SSH target and waits for a real lease
> (`orchestration/proxmox.py`), but the lease only exists once you give the
> tenant VLANs DHCP. That is Layer 1 below.

---

## The target topology

```
                          Internet
                             │
                    ┌────────┴─────────┐
                    │  EC2 relay (VPS)  │   public IP, only UDP/51820 open
                    │  WireGuard hub    │   forwards; holds no lab data
                    └────────┬─────────┘
             site tunnel ▲   │   ▲ student tunnels
        (dialed OUT from │   │   │ (students connect IN to the relay)
         the lab, so     │   │   │
         CGNAT is fine)  │   │   │
                    ┌─────┴───┴───┴─────┐
                    │  Proxmox host      │
                    │                    │
                    │  vmbr0  MGMT/WAN ──┼──► Proxmox UI, host, internet
                    │         (NEVER on the VPN)
                    │                    │
                    │  vmbr1  LAB (VLAN-aware, no host IP)
                    │    ├ VLAN 100  10.24.0.0/24  ← tenant A instances
                    │    ├ VLAN 101  10.24.1.0/24  ← tenant B instances
                    │    └ …          dnsmasq gives each VLAN DHCP+gateway
                    │                    │
                    │  wg0  lab gateway ─┼──► routes VPN ⇄ lab subnets,
                    │       (on host or a tiny gateway VM)
                    └────────────────────┘
```

Three trust zones, and the whole point is the boundaries between them:

| Zone | Carries | Reachable from the student VPN? |
| --- | --- | --- |
| **MGMT/WAN** (`vmbr0`) | Proxmox UI :8006, host SSH, PalestrIX app, internet | **No** — never routed onto the VPN |
| **LAB** (`vmbr1`, tenant VLANs) | the ephemeral lab VMs | **Yes**, but only the tenant subnets |
| **Relay** (EC2) | WireGuard only | it *is* the entry point; it sees no lab data |

---

## Layer 1 — Isolate the lab network and give it DHCP

The fix for the APIPA problem and for "students must not see Proxmox" is the
same: put lab VMs on a **separate bridge from management**, and run DHCP on
each tenant VLAN. Use Option A below. Option B is kept only to record why the
obvious SDN route does not work here.

### Option A — one dnsmasq, manual VLAN interfaces

Create a VLAN-aware `vmbr1` with no IP, then give the host a gateway interface
**inside each tenant VLAN** and run one dnsmasq. This matches how the Proxmox
adapter attaches a NIC — one shared VLAN-aware bridge
(`PALESTRIX_PROXMOX_BRIDGE`) plus the tenant's `vlan_id` as the tag — so one
bridge serves every tenant. `/etc/network/interfaces` on the node:

```
auto vmbr1
iface vmbr1 inet manual
    bridge-ports none
    bridge-stp off
    bridge-fd 0
    bridge-vlan-aware yes
    bridge-vids 100-1999

# gateway address inside tenant VLAN 100 (repeat per active tenant VLAN)
auto vmbr1.100
iface vmbr1.100 inet static
    address 10.24.0.1/24
```

`ifreload -a`, then `/etc/dnsmasq.d/lab.conf`:

```
interface=vmbr1.100
dhcp-range=set:t100,10.24.0.50,10.24.0.250,255.255.255.0,12h
dhcp-option=tag:t100,3,10.24.0.1      # gateway
dhcp-option=tag:t100,6,1.1.1.1        # DNS (or drop entirely for no egress)
# add an interface= + dhcp-range= block per tenant VLAN
```

`systemctl restart dnsmasq`. Leases land on the tenant subnet, no APIPA.

> Bind dnsmasq to just these interfaces (`bind-interfaces`, and `port=0` if you
> do not want it answering DNS). The node may already run SDN's own dnsmasq for
> a `simple` zone, and two unbound instances will fight over `:53`.

Point PalestrIX at the lab bridge in the backend `.env`, then restart the API
and worker:

```
PALESTRIX_PROXMOX_BRIDGE=vmbr1
```

### Option B — Proxmox SDN DHCP (does **not** work for tenant VLANs)

The obvious route is Proxmox's built-in SDN: VLANs, subnets, an IPAM and
dnsmasq DHCP with no extra packages. It cannot serve this design, for two
reasons that compound:

1. **SDN's DHCP is implemented for `simple` zones only.** A `vlan` zone has no
   `dhcp` property at all, so there is nowhere to enable it:
   ```
   # pvesh set /cluster/sdn/zones/lab --bridge vmbr1 --dhcp dnsmasq
   update sdn zone object failed: unexpected property 'dhcp'
   ```
   Confirm on the node — `VlanPlugin` offers `nodes mtu dns reversedns dnszone
   ipam`, while `SimplePlugin` adds `dhcp`:
   ```sh
   sed -n '/sub options/,/^}/p' /usr/share/perl5/PVE/Network/SDN/Zones/VlanPlugin.pm
   ```
2. **A `simple` zone cannot carry the tenant VLAN.** Its VNets are standalone
   bridges with no 802.1Q tag, whereas the adapter attaches every instance as
   `bridge=<PALESTRIX_PROXMOX_BRIDGE>,tag=<tenant.vlan_id>`. Switching to simple
   zones would mean one bridge per tenant and an adapter that looks the bridge
   name up per tenant, instead of one shared bridge plus a tag.

So SDN DHCP is only an option alongside a change to `ProxmoxProvider`: drop the
global bridge + tag in favour of a per-tenant VNet name. Worth doing if you want
Proxmox's IPAM to own lease tracking; until then, Option A is the supported
path.

### Locking the lab away from MGMT/WAN

> **The isolation is NOT structural — you must add firewall rules.** An
> earlier version of this document claimed that giving `vmbr1` no WAN uplink
> and no management IP was sufficient. It is not, and a default Proxmox host
> fails the check below. The tenant gateway (`vmbr1.100`) lives *on the
> Proxmox host*, which is also on `vmbr0` and the platform's management
> network, and Proxmox ships `net.ipv4.ip_forward=1`. DHCP hands the lab VM a
> default route via that gateway, so the host happily routes lab traffic
> straight into MGMT. Measured on a freshly provisioned lab VM:
>
> ```
> lab VM -> 10.24.0.1      (its gateway)        REACHABLE   expected
> lab VM -> 192.168.3.6:8006 (Proxmox UI)       REACHABLE   MUST NOT BE
> lab VM -> 10.0.10.12:80  (PalestrIX app)      REACHABLE   MUST NOT BE
> lab VM -> 1.1.1.1:443    (internet)           blocked     expected, no NAT
> ```
>
> A student with root on a lab VM — which is the whole point of a lab — can
> therefore reach the hypervisor API and the platform itself. Close it before
> any untrusted user gets an instance.

`vmbr1` having no WAN uplink does buy you one thing: no egress without an
explicit NAT rule. Everything else needs enforcement. Drop forwarding between
the tenant pool and every management network, and keep the lab off the host's
own services apart from DHCP:

```sh
# lab VLANs must not be routed into MGMT or the platform network
iptables -I FORWARD 1 -s 10.24.0.0/16 -d 192.168.3.0/24 -j DROP
iptables -I FORWARD 1 -s 10.24.0.0/16 -d 10.0.10.0/24  -j DROP
# ...nor reach the host itself, except the DHCP it needs. Give the positions
# explicitly: two bare `-I` inserts both land at the top, which would leave
# the catch-all drop ABOVE the DHCP exception and silently kill every lease.
iptables -I INPUT 1 -s 10.24.0.0/16 -p udp --dport 67 -j ACCEPT
iptables -I INPUT 2 -s 10.24.0.0/16 -p icmp --icmp-type echo-request -j ACCEPT
iptables -I INPUT 3 -s 10.24.0.0/16 -j DROP
```

The ICMP exception is what keeps `ping <gateway>` working from a lab, which
is the first line of the verification checklist below; without it the
catch-all drop swallows echo requests to the gateway too.

Check the order came out right — the accept must be listed first:

```sh
iptables -S INPUT
```

Persist them (`iptables-persistent`, or the Proxmox host firewall) — an
unsaved rule set dies at the next reboot and silently reopens the hole. If a
lab needs internet (e.g. `apt`), add a NAT rule for that VLAN explicitly —
never a bridge. Inter-tenant isolation *is* structural: different VLAN tags
cannot see each other on a VLAN-aware bridge.

A stronger variant, if you want the guarantee not to rest on the hypervisor's
rule set: move the tenant gateways off the Proxmox host onto a small dedicated
router VM. The host then holds no address in any tenant VLAN, so it is not the
labs' next hop and no host rule set has to hold. Build steps and the honest
limits of that claim are in [lab-gateway-vm.md](lab-gateway-vm.md).

Verify from a lab VM's console: it can ping its gateway (`10.24.0.1`) and
another VM in its own VLAN, but **cannot** reach the Proxmox host's management
IP or `:8006`.

---

## Layer 2 — WireGuard access through a CGNAT-friendly relay

Students need to reach `10.24.x.x`. Your Proxmox site is behind CGNAT (no
public IP, can't port-forward), so inbound VPN to your site is impossible.
The standard workaround: a **cloud relay with a public IP** that both sides
connect to. The lab **dials out** to the relay (outbound works through
CGNAT); students connect **in** to the relay; the relay forwards between them.

### 2.1 The relay (a t4g.nano/t3.micro EC2 is plenty)

It moves packets only — no lab data ever lives here. Harden it to a single
open UDP port:

- Security group / firewall: allow **only** UDP `51820` inbound (WireGuard),
  plus your own admin SSH from a fixed IP. Deny everything else.
- No HTTP, no other services, **no reverse-DNS PTR record** on the elastic IP.

Enable forwarding and install WireGuard:

```sh
echo 'net.ipv4.ip_forward=1' | sudo tee /etc/sysctl.d/99-wg.conf && sudo sysctl --system
sudo apt-get update && sudo apt-get install -y wireguard
wg genkey | tee relay.key | wg pubkey > relay.pub
```

Address plan for the tunnel overlay:

- Relay: `10.8.0.1/24`
- Lab gateway (your Proxmox site): `10.8.0.2`
- Students: `10.8.0.101`, `.102`, …

`/etc/wireguard/wg0.conf` on the **relay**:

```ini
[Interface]
Address = 10.8.0.1/24
ListenPort = 51820
PrivateKey = <relay.key>
# Forward student traffic toward the lab tunnel and back.
PostUp   = iptables -A FORWARD -i wg0 -j ACCEPT
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT

# --- the lab site (dials out from behind CGNAT) ---
[Peer]
PublicKey = <lab-gateway.pub>
# The relay must know which lab subnets live behind the site tunnel, so it
# routes student packets for 10.24.0.0/16 into this peer.
AllowedIPs = 10.8.0.2/32, 10.24.0.0/16

# --- students (one [Peer] block each; see 2.4) ---
```

`sudo systemctl enable --now wg-quick@wg0`.

### 2.2 The lab gateway (Proxmox host or a tiny gateway VM)

This end **initiates** the tunnel to the relay, so CGNAT never has to accept
an inbound connection. Run it on the Proxmox host, or better, a small
dedicated "gateway" VM that has a leg in each tenant VLAN (cleaner blast
radius than routing on the host). Enable `ip_forward`, then
`/etc/wireguard/wg0.conf`:

```ini
[Interface]
Address = 10.8.0.2/24
PrivateKey = <lab-gateway.key>
# NAT VPN traffic onto the lab VLANs so return packets find their way back
# through the tunnel. Replace vmbr1.100 with each tenant VLAN interface, or
# route if your gateway VM has an interface per VLAN.
PostUp   = iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -o vmbr1.100 -j MASQUERADE; iptables -A FORWARD -i wg0 -j ACCEPT; iptables -A FORWARD -o wg0 -j ACCEPT
PostDown = iptables -t nat -D POSTROUTING -s 10.8.0.0/24 -o vmbr1.100 -j MASQUERADE; iptables -D FORWARD -i wg0 -j ACCEPT; iptables -D FORWARD -o wg0 -j ACCEPT

[Peer]
PublicKey = <relay.pub>
Endpoint = relay.example.net:51820     # a HOSTNAME, not the raw EC2 IP (see 2.5)
# Pull student-overlay traffic down; hand nothing about MGMT/WAN.
AllowedIPs = 10.8.0.0/24
# Keep the CGNAT/NAT mapping open so the relay can reach back in.
PersistentKeepalive = 25
```

`sudo systemctl enable --now wg-quick@wg0`. The keepalive is what makes CGNAT
work: the site holds the outbound mapping open, so the relay can push student
packets back down an already-established flow.

### 2.3 What the lab gateway must NOT route

The gateway's `AllowedIPs` toward the relay is `10.8.0.0/24` (the VPN overlay)
only. It must **never** advertise or route `vmbr0`, the Proxmox management
subnet, or a default route. Students get exactly the tenant lab subnets and
nothing else. Double-check with a `DROP` rule for management from the VPN:

```sh
iptables -A FORWARD -i wg0 -d <proxmox-mgmt-cidr> -j DROP
```

### 2.4 Student configs

Each student is one `[Peer]` on the **relay** plus a `.conf` you hand them.
Generate a keypair per student, add to the relay:

```ini
# on the relay's wg0.conf, one block per student
[Peer]
PublicKey = <student1.pub>
AllowedIPs = 10.8.0.101/32
```

`sudo wg set wg0 peer <student1.pub> allowed-ips 10.8.0.101/32` applies it
without a restart. The file the student imports (WireGuard app on
Win/Mac/Linux/mobile):

```ini
[Interface]
PrivateKey = <student1.key>
Address = 10.8.0.101/32
DNS = 10.24.0.1              # optional: resolve lab hostnames via the gateway

[Peer]
PublicKey = <relay.pub>
Endpoint = vpn.labs.example.net:51820
# Split tunnel: ONLY lab traffic goes through the VPN; their normal internet
# does not, and they never see a route to your MGMT/WAN.
AllowedIPs = 10.24.0.0/16
PersistentKeepalive = 25
```

`AllowedIPs = 10.24.0.0/16` is the security control on the client side: the
student's machine only routes the lab supernet into the tunnel. They connect,
then `ssh student@10.24.0.x` — the private IP shown on the lab page. The
Proxmox UI, your host, and the internet-at-large are simply not in their
routing table.

> Automate this: a small script that `wg genkey`s a student, appends the peer
> to the relay, and prints the `.conf` turns onboarding a class into a loop.
> PalestrIX doesn't mint these today (it's out of the app's trust boundary),
> but the handles in Admin → Users map one-to-one to the peers you create.

### 2.5 About "hiding" the EC2 IP — the honest version

You asked to hide the relay's IP so students can't reverse-look-up your main
server. Two separate things there, and one is achievable, one isn't:

- **Your real server (the Proxmox/home site) is already hidden.** Because the
  site *dials out* to the relay, students only ever see the relay. Your CGNAT
  address and home/campus IP never appear in any student config or `wg show`.
  This is the main win and it's automatic with this topology.

- **The relay's own IP cannot be cryptographically hidden from its clients.**
  WireGuard is point-to-point: the client must send UDP to the endpoint, so
  the endpoint address is inherently visible in the `.conf` and in the OS's
  `wg show`. You can only make it *uninformative*:
  - Use a **hostname** (`vpn.labs.example.net`) in `Endpoint`, not the raw IP.
    A student sees the name; a determined one still resolves it. Cosmetic, not
    secret.
  - **Harden the relay** so the IP reveals nothing: only UDP/51820 open, no
    PTR record, no web server, no SSH from the world. A reverse lookup returns
    nothing and a port scan sees one silent UDP port.
  - If you genuinely need the *working* host hidden behind a disposable
    address, add a **second, throwaway relay** as a plain UDP forwarder
    (`socat`/`nftables` DNAT of `:51820`) in front of the real relay. Students
    connect to the front IP; you can rotate/replace it without touching the
    real hub. This only moves the visible IP to something you don't mind
    exposing — it does not make WireGuard's endpoint invisible, because no
    VPN can (the client has to send packets *somewhere*).
  - True origin-hiding for UDP needs an anycast/Spectrum-style proxy
    (e.g. Cloudflare Spectrum) — enterprise, and overkill for a class range.

Bottom line: this design hides the asset you actually care about (your
server) for free; treat the relay as a deliberately exposed, hardened,
replaceable front door rather than a secret.

---

## Verification checklist

- [ ] Lab VM boots with a `10.24.x.x` lease (not `169.254.x`); the lab page
      shows `ssh student@10.24.x.x`. If it still times out, DHCP isn't
      reaching the tenant VLAN — recheck Layer 1.
- [ ] From a lab VM: can reach its gateway and same-VLAN peers; **cannot**
      reach the Proxmox management IP or `:8006`.
- [ ] Relay: `sudo wg show` lists the lab-gateway peer with a recent handshake
      and the student peers.
- [ ] Student (VPN up): `ssh` to a lab IP works; `traceroute` to the Proxmox
      management IP dies at the gateway; the Proxmox UI is unreachable.
- [ ] Relay firewall: only UDP/51820 (and your admin SSH) is open; no PTR
      record on the elastic IP.

## Where PalestrIX fits

The app owns tenant→VLAN/CIDR allocation and publishes each instance's leased
private IP on the lab page; the network layer above owns DHCP, isolation, and
the VPN. They meet at exactly one place: the tenant's `vlan_id` and
`network_cidr` (Admin → Infrastructure → Tenants) must match the VLAN tags and
subnets you configure in Layer 1. Keep those in sync and a launch flows all
the way to a student's SSH session.

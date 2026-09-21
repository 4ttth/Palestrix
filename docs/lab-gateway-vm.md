# The lab gateway VM: taking the hypervisor out of the lab's routing path

Companion to [lab-networking.md](lab-networking.md). That document builds the
tenant VLANs with the **Proxmox host** as their gateway, and then closes the
resulting hole with firewall rules. This one removes the hole instead, by
moving the tenant gateways onto a dedicated router VM with no reason to reach
management.

Nothing in PalestrIX changes. The Proxmox adapter attaches every instance as
`bridge=$PALESTRIX_PROXMOX_BRIDGE,tag=<tenant.vlan_id>` and never talks to the
gateway, so this is purely a networking swap.

---

## Why

With the host as gateway, a freshly provisioned lab VM measured like this:

```
lab VM -> 10.24.0.1        (its gateway)       REACHABLE   expected
lab VM -> 192.168.3.6:8006 (Proxmox UI)        REACHABLE   must not be
lab VM -> 10.0.10.12:80    (PalestrIX app)     REACHABLE   must not be
lab VM -> 1.1.1.1:443      (internet)          blocked     expected, no NAT
```

The cause is not a missing rule so much as a misplaced role. `vmbr1.100` is an
address **on the Proxmox host**; the host is also on `vmbr0` and on the
platform's management network; and Proxmox ships `net.ipv4.ip_forward=1`. DHCP
hands the lab a default route pointing at that address, so the hypervisor
cheerfully routes lab traffic into MGMT. Labs exist to hand students root, so
this is root plus a path to the hypervisor API and the platform.

Firewall rules on the host do close it. They are also the only thing standing
between a student and the API, they live on the machine under attack, and a
flush, a package upgrade or an unsaved rule set at reboot reopens it silently.

## What moving the gateway actually buys

Be precise about the claim, because the router VM still needs one path out.

**Structural, after the move:** the Proxmox host holds **no address in any
tenant VLAN**. It is not the labs' next hop, so `ip_forward` on the host is
irrelevant to them and no host rule set has to hold for the guarantee to stand.
That is the part that stops depending on configuration.

**Still policy, after the move:** the router needs to reach the WireGuard relay
(Layer 2 in [lab-networking.md](lab-networking.md)), so it keeps one LAN leg
for egress. Traffic from tenant VLANs to MGMT is denied by rules *on the
router*. The difference is blast radius and custody: the rules live on a
single-purpose VM that no student has an account on, a compromise costs you a
router rather than the hypervisor, and the hypervisor's own firewall state
stops being load-bearing.

If you want the LAN leg gone too, the relay has to be reachable some other way
— a second physical NIC on its own uplink, or an on-site relay inside the lab
segment. On a single-workstation deployment (use case A) there is one uplink,
so the LAN leg stays.

---

## Topology

```
                    ┌──────────────────────────────────────┐
  eno1 ── vmbr0 ────┤ Proxmox host  192.168.3.6            │
   (LAN/MGMT)       │ NO address in any tenant VLAN        │
                    │ plxmgmt 10.0.10.1  (platform only)   │
                    └──────────────────────────────────────┘
                              │                    │
                       (tap, untagged)      (tap, trunk)
                              │                    │
                    ┌─────────┴────────────────────┴───────┐
                    │  labgw VM                            │
                    │   eth1  192.168.3.x   egress only    │
                    │   eth0  trunk on vmbr1               │
                    │     eth0.100  10.24.0.1/24  ─┐       │
                    │     eth0.101  10.24.1.1/24   ├ dnsmasq
                    │     …                        ─┘       │
                    │   wg0   to the EC2 relay             │
                    │   nftables: default-deny forward     │
                    └──────────────────────────────────────┘
                                       │
                          vmbr1 (VLAN-aware, no host IP)
                                       │
                         lab VMs, tagged per tenant VLAN
```

`vmbr1` keeps exactly the role it has now — a VLAN-aware bridge with no ports
and no host address — and `PALESTRIX_PROXMOX_BRIDGE=vmbr1` is unchanged.

---

## Build

### 1. The VM

Debian 13, 1 vCPU, 512 MB, 8 GB disk is plenty. Two NICs:

| NIC | Bridge | Purpose |
|-----|--------|---------|
| `net0` | `vmbr1`, **no tag** | trunk carrying every tenant VLAN |
| `net1` | `vmbr0` | egress to the WireGuard relay, nothing else |

```sh
qm set <vmid> --net0 virtio,bridge=vmbr1
qm set <vmid> --net1 virtio,bridge=vmbr0
```

`net0` must be untagged so the guest sees the 802.1Q tags and can terminate
each VLAN itself.

### 2. Tenant gateways on the router

One subinterface per active tenant VLAN, addressed as that tenant's
`network_cidr` gateway. In `/etc/network/interfaces` on **labgw**:

```
auto eth0
iface eth0 inet manual

auto eth0.100
iface eth0.100 inet static
        address 10.24.0.1/24

# repeat per active tenant VLAN: eth0.<vlan_id>, <tenant network_cidr> .1

auto eth1
iface eth1 inet dhcp
```

Read the VLAN and CIDR from PalestrIX (Admin → Infrastructure → Tenants), or:

```sh
sudo -u postgres psql -d palestrix -c \
  'select id, vlan_id, network_cidr from tenants where not archived order by vlan_id;'
```

### 3. DHCP, on the router

`/etc/dnsmasq.d/lab.conf` on **labgw** — the same content that was on the host:

```
interface=eth0.100
bind-interfaces
port=0
dhcp-range=set:t100,10.24.0.50,10.24.0.250,255.255.255.0,12h
dhcp-option=tag:t100,3,10.24.0.1
# one interface= + dhcp-range= block per tenant VLAN
```

`port=0` keeps it DHCP-only. Leave DNS option 6 out unless a lab is meant to
have egress.

### 4. Default-deny forwarding

`/etc/nftables.conf` on **labgw**:

```
table inet labgw {
  chain forward {
    type filter hook forward priority 0; policy drop;

    # the relay reaches labs, labs answer
    iifname "wg0" oifname "eth0.*" accept
    iifname "eth0.*" oifname "wg0" ct state established,related accept

    # never toward management
    ip daddr { 192.168.3.0/24, 10.0.10.0/24 } drop
  }

  chain output {
    type filter hook output priority 0; policy accept;
    # egress on the LAN leg is the relay tunnel only
    oifname "eth1" ip daddr != <RELAY_PUBLIC_IP> udp dport != 51820 drop
  }
}
```

`systemctl enable --now nftables`. Inter-tenant isolation needs no rule:
different VLAN tags cannot see each other on a VLAN-aware bridge, and each
VLAN terminates on its own subinterface here.

### 5. Retire the host-side gateway

This is the step that makes the host structurally uninvolved — do not skip it,
or both gateways answer and the old path stays open.

```sh
# on the Proxmox host
systemctl disable --now dnsmasq
# remove the vmbr1.<vlan> stanzas from /etc/network/interfaces, keep vmbr1
ifreload -a
ip -br a | grep vmbr1      # expect vmbr1 with NO ipv4 address
```

### 6. WireGuard

Per Layer 2 of [lab-networking.md](lab-networking.md), with `wg0` on **labgw**
instead of the host, and the tenant subnets as its `AllowedIPs`.

---

## Verification

Provision a real lab, then from its console or the guest agent
(`qm guest exec <vmid> -- ...`):

```
lab VM -> 10.24.0.1         its gateway            REACHABLE
lab VM -> 192.168.3.6:8006  Proxmox UI             must be BLOCKED
lab VM -> 10.0.10.12:80     PalestrIX app          must be BLOCKED
lab VM -> 1.1.1.1:443       internet               BLOCKED unless NATed
lab VM -> a peer in another tenant VLAN            must be BLOCKED
```

And on the Proxmox host, the check that this design is really in force:

```sh
ip -br a | grep vmbr1       # no ipv4 address on vmbr1 or any vmbr1.<vlan>
```

If the host still holds a tenant gateway address, step 5 did not take and the
guarantee is still resting on host firewall rules.

---
summary: A flat network turns one compromised laptop into every server. Segmentation is how you make the blast radius smaller than the estate.
---

# Segmentation, VLANs, and the flat-network problem

Every intrusion starts somewhere unimportant: a laptop, a printer, a meeting
room display. What decides whether that stays a small problem is whether the
unimportant thing can reach the important ones.

On a flat network it can reach all of them.

## What "flat" costs you

One broadcast domain, one subnet, everything routable to everything else. The
consequences compound:

- **Lateral movement is free.** No control to bypass, because there is no
  control — just ARP and a switch.
- **You cannot see it.** East-west traffic never crosses a router, so nothing
  inspects it and nothing logs it. The intrusion is invisible until it touches
  something that does log.
- **Layer 2 attacks work.** ARP spoofing, DHCP spoofing and LLMNR/NBT-NS
  poisoning all operate within a broadcast domain. A larger domain is a larger
  attack surface for all three.
- **Containment means unplugging things.** With no boundaries to close, the
  only lever is disconnection, which is why incidents on flat networks are so
  disruptive.

## Segment by trust, not by geography

The instinct is to segment by building or department. Segment by **what
happens if this is compromised** instead:

- User workstations. Numerous, high-risk, low-value individually.
- Servers, split by function: application, database, file.
- Management and infrastructure — hypervisors, switches, out-of-band cards.
  Always its own segment, always the most restricted.
- Unmanaged and unpatchable devices: printers, cameras, building control,
  lab equipment. These never get patched, so isolate them instead.
- Guest and BYOD, with no path inward at all.

The most valuable single boundary in most estates is **management**. A
hypervisor API or a switch's admin interface reachable from a user VLAN means
one phishing email reaches the infrastructure everything else runs on.

## VLANs, and what they are not

A VLAN is a broadcast domain. Two VLANs on the same switch cannot see each
other's traffic at layer 2 — that part is real isolation.

But VLANs alone do not stop anything at layer 3. The moment a router has an
interface in both VLANs, traffic flows freely unless an ACL says otherwise.
**The control is the ACL, not the VLAN.** The VLAN is only what makes the ACL
possible.

Two things to get right:

- **Never use VLAN 1** for anything, and never leave it as the native VLAN on
  a trunk. Double-tagging attacks depend on the native VLAN being predictable.
- **Prune trunks explicitly.** A trunk carrying every VLAN to every switch
  undoes the design; carry only what the far end needs.

## Default deny, written down

A segmentation policy is a matrix of which segments may initiate to which,
and on what ports. Written as rules, the shape is always:

```
allow  workstations -> app-servers      443
allow  app-servers  -> db-servers       5432
allow  management   -> everything       22, 443
deny   any          -> management       any
deny   any          -> any              any        (log)
```

Two disciplines make it real. **Direction matters**: app servers must not
initiate to workstations, and writing the rule one-way costs nothing. And the
final deny must **log**, because the log is how you learn what you broke and
how you detect what is probing.

## Microsegmentation, and being honest about cost

Per-workload policy — host firewalls, identity-based rules, service mesh —
is strictly better and considerably more work. It is worth it around the
crown jewels and rarely worth it everywhere.

A realistic order for a small estate:

1. Get management off every user-reachable segment.
2. Put unmanageable devices in their own VLAN with no inward path.
3. Separate servers from workstations, with default deny between them.
4. Split the server tiers.
5. Only then consider per-workload policy.

Most of the benefit is in the first two steps.

## Verify it, or you do not have it

Segmentation that has never been tested is a diagram. Test from inside each
segment, in both directions, and keep the results:

```
nmap -sS -Pn -p 22,443,3389,5432,8006 10.0.10.0/24
```

Run it after every firewall change. A rule added for a project three months
ago, never removed, is the most common way segmentation quietly dies.

## Check yourself

- Why is east-west traffic on a flat network invisible to most monitoring?
- A VLAN separates two groups of hosts. What does that actually stop, and what
  does it not?
- Which single segmentation boundary gives the most security for the least
  work, and why?

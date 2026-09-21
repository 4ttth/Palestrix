---
summary: The remote access box is internet-facing, holds credentials, and terminates inside. It is the first thing attacked and the first thing to get right.
---

# Hardening the edge: VPN and remote access

A remote access gateway is reachable from everywhere, authenticates users, and
lands them inside the network. That combination makes it the single most
attacked device most organisations own.

It is also, historically, one of the least well maintained.

## Patch it first, and treat that as non-negotiable

Remote access appliances have a long record of pre-authentication remote code
execution. When one of those is published, mass exploitation follows within
days — often hours — because the devices are trivially discoverable from the
internet.

This class of device earns an out-of-cycle patching commitment. If your change
process cannot apply a critical VPN patch within days, the process is the
vulnerability.

Two habits that matter as much as patching:

- **Subscribe to the vendor's advisory feed directly.** Waiting to hear about
  it through general news costs you the window.
- **Assume compromise if you patched late.** Several of these bugs leave
  persistence that survives the update. Patching closes the door; it does not
  evict anyone already inside.

## Authentication: phishing resistance or nothing

Credentials to a VPN are credentials to the network. Password-only remote
access is not defensible in 2026.

- **Certificate-based device authentication plus user authentication.** The
  device certificate means a stolen password alone is insufficient.
- **Phishing-resistant MFA.** WebAuthn or smart cards. Push-based MFA is
  meaningfully weaker: push fatigue works, and attackers know it.
- **No shared accounts.** Ever. Attribution is the point.
- **Account lifecycle that actually runs.** Dormant accounts on remote access
  are a standing invitation; disable on inactivity, automatically.

## Terminate somewhere that is not "inside"

The common failure is a VPN that drops users straight onto a flat internal
network with full reachability.

- Terminate into a **dedicated segment**, and apply policy from there to
  internal resources.
- **Default deny** out of that segment. Grant access per role, per service.
- **Split-tunnel decisions are a trade-off:** full tunnel gives you visibility
  over all the client's traffic and costs bandwidth; split tunnel is cheaper
  and blinds you to everything not destined inward. Decide deliberately.
- **Device posture** before access: patch level, disk encryption, EDR running.

## Reduce what is exposed at all

- **Management interfaces must never face the internet.** The administrative
  console of the VPN itself is a favourite target — put it on management only.
- **Geofence or allowlist** if your user population permits it.
- **Retire protocols you are not using.** Legacy IKEv1, SSL VPN web portals,
  clientless modes with Java applets. Every extra mode is attack surface for
  a feature nobody uses.
- **Consider whether a VPN is the right shape at all.** Identity-aware proxies
  publish individual applications rather than granting network access, which
  removes the "one credential, whole network" property entirely.

## Monitor it like it is compromised

The gateway's logs are high-signal because the population is well-defined:

- **Impossible travel** and sign-ins from unexpected countries.
- **First-time device or client version** for an established user.
- **Authentication succeeding after a burst of failures**, per account and per
  source — the credential-stuffing shape from the SOC path.
- **Sessions at unusual hours** for that individual.
- **Configuration changes**, which on a compromised appliance are how
  persistence is installed.
- **Concurrent sessions** for one account from two places.

Forward all of it off the device. An attacker with administrative access to
the gateway will edit its local logs, and logs that only exist on the
compromised box are not evidence.

## Have a revocation plan before you need one

Write down, in advance, how you would: disable one user's access immediately,
force re-authentication for everyone, roll the device certificates, and take
the gateway offline while keeping an administrative path to it.

> During an incident is the wrong time to discover that revoking access
> requires a vendor support ticket.

## Check yourself

- Why does patching a VPN appliance late warrant a compromise assessment
  rather than just an update?
- Why is push-based MFA weaker than WebAuthn for remote access specifically?
- Why must gateway logs be forwarded off the device, and what does the local
  copy become worth after a compromise?

---
summary: Breaking TLS to inspect it is a real capability with real costs. Decide deliberately, and decide what not to decrypt.
---

# TLS inspection and what it costs you

Almost all traffic is encrypted, so payload-based detection sees almost
nothing. TLS interception restores that visibility by terminating the session
on a middlebox, inspecting the plaintext, and re-encrypting onward.

It works. It is also the security control most likely to make an estate less
safe if deployed carelessly, and this module is mostly about the second half.

## How it works

The middlebox holds a CA certificate that every managed client trusts. For an
intercepted connection it generates a certificate for the requested hostname
on the fly, signs it with that CA, and presents it to the client. The client
validates it successfully — because the CA is trusted — and never knows.

Two consequences follow immediately, and both are structural:

- **Every client must trust your CA.** Unmanaged devices cannot be intercepted
  without breaking them.
- **That CA's private key can impersonate any site on the internet** to every
  device in your estate. It is now the most valuable key you own.

## What you gain

- Payload inspection: IDS rules, malware scanning, DLP on actual content.
- Visibility into exfiltration that would otherwise be an opaque upload.
- Enforcement of file-type and content policy.
- URL-level rather than domain-level control.

These are genuine. An estate with no payload visibility is blind to a large
class of attack.

## What you pay

**You become a single point of catastrophic failure.** The middlebox holds
plaintext for every session: credentials, health records, banking. A
compromise there is a compromise of everything at once, with no encryption
anywhere to slow it down.

**You may downgrade security without noticing.** Some appliances negotiate
weaker ciphers upstream than the client would have, do not validate upstream
certificates properly, or fail open on validation errors. The client sees a
green padlock that now means only "my employer's box says this is fine" —
and if the box is not checking, it means nothing at all.

**You break things, continuously.** Certificate pinning — in mobile apps,
updaters, and increasingly desktop software — is designed to detect exactly
this and refuse to connect. Mutual TLS breaks. Non-browser clients with their
own trust stores (Java, Python, Go, `curl`) do not know about your CA and
fail with errors that look nothing like a proxy problem.

**You create legal and ethical exposure.** Decrypting an employee's banking or
medical traffic is a different act from inspecting their use of a corporate
application, and in many jurisdictions it is regulated. This is a policy
decision with a legal dimension, not a networking one.

## Decide what *not* to decrypt

The competent deployment is defined by its bypass list, which should be
policy, documented, and reviewed:

- Banking and financial services.
- Healthcare and insurance.
- Government services.
- Legal services.
- Anything hosting employee benefits or HR self-service.
- Applications that pin certificates, because the alternative is an outage.
- Software update channels, where interception can break signature validation.

Bypass by SNI or by category, and log that a bypass occurred so the decision
stays visible.

## Protect the key like it is the estate

- Hardware security module or equivalent. Not a file on the appliance.
- A dedicated intermediate CA, not your internal root, so it can be revoked.
- Name constraints where supported, limiting what the CA may issue for.
- Audit every issuance.
- A tested revocation and rotation plan, because "replace the CA every device
  trusts" is not something to improvise during an incident.

## What you can do instead

Much of the value is available without decryption, and it is worth exhausting
these first:

- **SNI and certificate metadata.** The destination hostname, issuer and
  validity are cleartext in the handshake.
- **JA3/JA4 fingerprinting.** Identifies the client TLS stack. Non-browser
  malware stands out against a browser-shaped baseline.
- **Flow shape.** Beaconing, exfiltration volume and timing survive
  encryption.
- **DNS telemetry**, which is cleartext at your own resolver.
- **Endpoint agents.** EDR sees plaintext *before* it is encrypted, with no
  middlebox and no key to protect. For most estates this is a better answer to
  the same question.

> If the goal is seeing what left the building, an endpoint agent usually
> beats a TLS proxy — at lower risk, with better attribution, and without a
> key that can impersonate the internet.

## Check yourself

- Why does TLS interception make the middlebox's CA key the most valuable
  asset in the estate?
- Name three categories of destination that should be on a bypass list, and
  the reason for each.
- Give three detections you can still run on fully encrypted traffic.

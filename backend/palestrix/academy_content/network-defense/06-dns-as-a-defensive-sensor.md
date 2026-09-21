---
summary: Nearly everything looks up a name before it connects. That makes the resolver the cheapest sensor you own.
---

# DNS as a defensive sensor

Before almost any connection, something resolves a name. Malware does it,
implants do it, the exfiltration tool does it. Your resolver sees all of it,
in one place, in cleartext, before the connection happens.

No other sensor is this cheap or this early.

## Log the right thing

Query logs at the resolver, retained. For each query you want: timestamp,
client address, query name, query type, response code, and the answer.

Two properties make this uniquely useful:

- **It precedes the connection.** You can block at resolution time, before a
  packet reaches the destination.
- **It is client-attributed.** The record names the internal host, which flow
  data from beyond a NAT boundary often cannot.

## What to look for

**NXDOMAIN bursts.** Domain generation algorithms produce many names, most of
which do not exist. A host generating dozens of failed lookups for
random-looking names, in a burst, is running something that is hunting for its
controller.

**High-entropy labels.** `k3j5h2n4bk3j.example.com` is not a hostname a person
typed. Long labels with near-uniform character distribution are either DGA or
tunnelling.

**Excessive `TXT` queries.** `TXT` carries arbitrary text and is the most
common tunnelling record type. A workstation issuing hundreds of `TXT`
lookups is not doing SPF checks.

**Query volume to one domain.** Tunnelling requires one lookup per data chunk,
so it shows up as an enormous number of unique subdomains under a single
parent. Aggregate by registered domain, count distinct children, and sort.

**Very low TTLs.** Fast-flux infrastructure uses TTLs of 60 seconds or less so
the address can rotate. Legitimate CDNs do this too, so it is a supporting
signal, not a conclusion.

**Newly registered domains.** A domain first seen globally three days ago,
being resolved by one host in your estate, is worth a look. Age is one of the
highest-yield enrichments available.

**Clients bypassing the resolver.** Outbound `53`, `853`, or DNS-over-HTTPS to
anything other than your resolvers. A host doing its own resolution has
removed itself from this sensor — which is sometimes a privacy tool and
sometimes the point.

## A tunnelling detection you can write today

```
# domains with an unusual number of distinct subdomains today
awk '{print $5}' /var/log/dns/query.log \
  | rev | cut -d. -f1,2 | rev \
  | sort | uniq -c | sort -rn | head -20
```

Your own domain and the big CDNs will top that list. Anything else with
thousands of distinct children is the finding.

## Blocking, and where it goes wrong

Response Policy Zones let the resolver refuse or rewrite answers. Feed them
with threat intelligence, newly-registered-domain lists, and your own
indicators.

Two cautions:

- **Sinkhole rather than `NXDOMAIN`.** Pointing bad names at a host you
  control turns a block into a detection: every client that connects to the
  sinkhole identifies itself as infected. An `NXDOMAIN` just makes the malware
  try its next domain quietly.
- **Blocklists have false positives**, and a blocked domain looks to users
  exactly like a broken network. Have a review path, or the first bad block
  gets the whole system turned off.

## Encrypted DNS changes who the sensor belongs to

DoH and DoT encrypt queries to the resolver. That is good for users on hostile
networks and bad for a defender who is not the resolver — if a workstation
resolves through a public DoH provider, your query log is empty.

The defensive posture is not to fight encryption but to **own the resolver**:
run internal DoH/DoT, point clients at it by policy, and block outbound DNS to
everything else at the firewall. Then queries are encrypted on the wire and
still logged where you can see them.

> Whoever runs the resolver gets the telemetry. Make sure that is you.

## What is noisy and innocent

- CDN and cloud names with high-entropy labels — legitimate and everywhere.
- Certificate revocation, telemetry and update lookups, constantly.
- `NXDOMAIN` from search-domain suffixing, where a short name gets tried
  against every domain in the client's search list.
- Antivirus and reputation lookups, which are themselves query-heavy and
  encode data in subdomains — structurally identical to tunnelling.

That last one is worth internalising: some security products tunnel over DNS
by design, so baseline your estate's own tooling before you alert on the
pattern.

## Check yourself

- Why is the resolver an earlier sensor than the firewall?
- What does a single parent domain with thousands of distinct subdomains
  suggest, and which query type supports it best?
- Why is sinkholing a malicious domain more useful than returning `NXDOMAIN`?

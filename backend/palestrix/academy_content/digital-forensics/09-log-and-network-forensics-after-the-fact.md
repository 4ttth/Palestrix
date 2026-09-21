---
summary: Investigating an intrusion that happened months ago, from whatever survived — and reasoning honestly about what did not.
---

# Log and network forensics after the fact

Live response is a luxury. Most investigations begin with "we think something
happened in January" and a set of logs whose retention nobody has checked.

The discipline here is different: you are reconstructing from partial records,
and the hardest skill is stating clearly what the records cannot tell you.

## Find out what survived, first

Before any analysis, inventory the sources and their retention. Do it in
writing, because the gaps become a section of the report:

- Authentication: domain controllers, VPN, SSO, cloud identity.
- Endpoint: EDR telemetry, Windows event logs, `auditd`.
- Network: firewall, proxy, NetFlow, resolver.
- Application: web server access logs, database audit, admin actions.
- Email: message tracking, mailbox audit.
- Cloud: control-plane audit logs.

For each, ask three questions: how far back does it go, what does it record,
and has it been modified? An hour spent here prevents a week spent chasing an
artefact that was rotated out in February.

## Retention is the constraint everything bends around

The attack was in January. The firewall keeps 30 days. That data is gone, and
no amount of analysis recovers it.

But absence in one source is not absence everywhere. Look for **derived or
duplicated copies**:

- The SIEM may hold parsed events long after the device rotated them.
- Backups of the log server.
- Aggregated or sampled data — NetFlow summaries, proxy reports — kept longer
  than raw records.
- Endpoints hold their own local event logs independent of central collection.
- Cloud providers often retain control-plane logs beyond your own settings.
- Third parties: the email gateway vendor, the CDN, the identity provider.

> "We have no logs" is usually wrong. "We have no logs *from that device*" is
> usually right, and the difference is where the investigation lives.

## Endpoint logs after the fact

Windows event logs are files, so image them and parse offline:

```
C:\Windows\System32\winevt\Logs\Security.evtx
                              \System.evtx
                              \Microsoft-Windows-Sysmon%4Operational.evtx
```

Key events: `4624`/`4625` logon and failure, `4688` process creation, `4672`
special privileges, `7045` service install, `1102` audit log cleared.

`1102` deserves its own note. Clearing the Security log is itself logged, and
it is one of the loudest things an intruder can do. Similarly, Linux `wtmp`
and `btmp` truncation leaves a file whose size and mtime contradict its
contents.

Event logs also support recovery: `.evtx` records are recoverable from
unallocated space by carving, so a cleared log is not necessarily a lost one.

## Network, without a capture

Full packet capture from months ago will not exist. Flow, proxy and resolver
records may:

- **Flow** gives you who talked to whom, when, and how much. Enough to
  establish contact with known infrastructure and to find other hosts that
  did the same.
- **Proxy logs** add URLs, user agents and usernames, which is a large
  upgrade over flow.
- **Resolver logs** place a lookup at a moment and attribute it to a client.
- **Certificate transparency and passive DNS** are external sources: what a
  domain resolved to historically, even though you did not record it.

## The retrospective sweep

Once you have an indicator — an address, a domain, a hash, an account — sweep
every source for every other appearance of it. This is what converts a single
compromised host into a scoped incident.

Sweep for time too: take the window in which you know the intruder was
active, and look at everything that happened then, not only things matching
your indicator. The second host is rarely found by the first indicator.

## Reason honestly about what is missing

Three failure modes, all of which produce confident wrong answers:

**Absence of evidence.** No log entry can mean it did not happen, or that
logging was off, or that retention expired, or that the log was cleared. Say
which you believe and why.

**Clock skew.** Sources disagree. Establish each one's offset against a
reference and state corrections explicitly.

**Incomplete coverage.** You are looking at 40% of the estate. Conclusions
apply to what you looked at, and the report should say what you did not.

The strongest section in a retrospective report is often the one titled *What
we could not determine, and why*. It is also the section that generates the
logging recommendations, because each gap names a source that would have
answered the question.

## Check yourself

- Why does inventorying log sources and retention come before analysis?
- Give three places a log might survive after the originating device rotated
  it.
- A search returns no results. Name three explanations, and say how you would
  distinguish them.

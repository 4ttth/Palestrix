---
summary: The report is the only part of an incident that outlives it. Write it for the people who will act on it.
---

# Writing the incident report

Everything else you did during the incident — the queries, the containment,
the long night — becomes inaccessible the moment the incident closes. The
report is what remains. It is read by people deciding whether to spend money,
whether to notify a regulator, and what to do differently, and none of them
were in the room.

## Three readers, one document

Write for all three, in this order, because they stop reading at different
points:

- **An executive** who needs the impact and the decision in ninety seconds.
- **An engineer** who has to implement the fix and needs the mechanism exactly.
- **A future analyst** investigating something that rhymes with this, two
  years from now, who needs the indicators and the timeline.

The structure below is just those three readers in sequence.

## The structure

**Summary.** Five sentences, no jargon. What happened, how it started, what
was affected, what you did, what is still open. If someone reads only this,
they should not be misled.

**Timeline.** Timestamps in UTC, one line each, earliest first. Separate what
the *attacker* did from what *you* did — two columns of activity in one
sequence, clearly labelled, so the gap between first compromise and first
detection is visible. That gap is the number the whole organisation should
care about.

**Scope.** Which accounts, hosts, and data. State confidence: "confirmed",
"suspected", "ruled out". An unqualified list reads as certainty you do not
have.

**Root cause.** How they got in, mechanically. Not "phishing" — *which* email,
*which* link, *which* credential, and why the control that should have caught
it did not.

**Response.** What you did and when. Include the things that did not work.

**Recommendations.** Specific, owned, dated. See below.

**Indicators.** Addresses, hashes, domains, account names, rule ideas. This is
the section the future analyst greps.

## Timestamps, and the one rule about them

UTC. Everywhere. With the offset written out.

An incident spans log sources in different zones, and a report mixing them is
worse than useless — it produces a false ordering, and a false ordering
produces a false causal story. Convert everything once, at the start, and say
in the report that you did.

```
2026-03-14T02:14:07Z  ATTACKER  First failed SSH, 203.0.113.45 -> web-01
2026-03-14T02:19:51Z  ATTACKER  Successful publickey, user deploy
2026-03-14T02:20:02Z  ATTACKER  sudo to root
2026-03-14T06:40:11Z  DEFENDER  Alert fired (cron persistence rule)
2026-03-14T07:02:00Z  DEFENDER  Host isolated
```

Four hours and twenty minutes between root and detection. Stated that plainly,
nobody has to argue for detection investment; the table does it.

## Write what you know, mark what you infer

The most damaging sentence in an incident report is a plausible guess written
in the same voice as a fact.

- **Fact:** "auth.log records a successful publickey authentication for
  `deploy` from 203.0.113.45 at 02:19:51Z."
- **Inference:** "The key was most likely taken from the developer laptop
  compromised on the 11th; we have not confirmed this."
- **Unknown:** "We cannot determine whether the database was read. Query
  logging was not enabled."

Say "we do not know" in writing. It is the sentence that protects everyone
later, and the one people are most tempted to soften.

## Recommendations that survive the meeting

A recommendation without an owner and a date is a wish. Three that will be
done beat ten that will not.

```
1. Rotate all deploy keys and move to short-lived certificates.
   Owner: Platform. Due: 2026-04-01.
2. Enable query logging on the customer database.
   Owner: DBA. Due: 2026-03-28.
3. Alert on new authorized_keys entries across the estate.
   Owner: Detection. Due: 2026-04-15.
```

Rank them by the incident you are preventing, not by ease.

## What to leave out

- Blame. Name systems and controls, not people. A report that punishes
  reporting produces later reports.
- Tool narration. Nobody needs to know which console you clicked.
- Vendor language. "Advanced persistent threat" where "they had a valid SSH
  key for four hours" is what you actually mean.

> Write it as if the person who has to act on it is hostile to the conclusion
> and short of time. That is frequently the case.

## Check yourself

- Why must attacker actions and defender actions be distinguishable in the
  timeline?
- What is the difference between a fact, an inference and an unknown in a
  report, and why does collapsing them cause harm?
- What two things turn a recommendation from a wish into work?

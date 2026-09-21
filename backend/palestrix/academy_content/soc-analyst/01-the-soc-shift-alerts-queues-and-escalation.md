---
summary: What a shift actually looks like, why the queue is never empty, and how to decide what to touch first.
---

# The SOC shift: alerts, queues, and escalation

A security operations centre is not a room where people watch attacks happen.
It is a queue, and the job is deciding what in that queue deserves your
attention in the next ten minutes.

## The queue is never empty, and that is not a failure

New analysts often assume a clean queue is the goal, and treat the backlog as
evidence something has gone wrong. It is not. A detection rule that never
fires is a rule nobody has tested; a queue at zero usually means detections
are too narrow, not that the network is quiet.

The thing to optimise is not queue length. It is **time-to-decision on the
alerts that matter**. An analyst who closes ninety low-value alerts and misses
one real intrusion has had a worse shift than one who closed nine and caught
it.

## Triage is a sorting problem

Every alert gets one of four outcomes, and you should be able to reach one of
them quickly:

- **Close as benign** — explained by known activity. Write down *why*, because
  the next analyst will see it again.
- **Tune** — the rule is wrong, not the host. This is work on the detection,
  not on the incident.
- **Investigate** — needs evidence you do not have yet.
- **Escalate** — someone with more authority or context needs it now.

Most alerts are the first two. Getting fast at them is what buys you time for
the third.

## What makes an alert worth escalating

Escalation is a judgement about *blast radius and reversibility*, not about
how alarming the alert text sounds. Ask:

- Does this touch identity? Credential and token theft spreads sideways in
  ways a single compromised host does not.
- Is the affected system a control point — a domain controller, a build
  server, a jump host, a backup system?
- Is there evidence of **attacker decision-making**? Automated noise is
  repetitive. A human adapting to what they find is the signal that the thing
  in your network is thinking.
- Is it reversible? Data that has already left cannot be un-left.

> A rule of thumb: escalate on *pattern*, not on *severity label*. Three
> medium alerts describing one host reaching further each time beat one
> critical alert that fires on every workstation daily.

## Writing the note

The note you leave is the deliverable. An alert you closed with no reasoning
is an alert the next analyst has to redo. A usable note has three parts:

```
What fired:    Impossible-travel sign-in, user j.reyes, 02:14 and 02:51 UTC
What I found:  Both from corporate VPN egress; second session is the
               user's phone re-registering after a password change.
Decision:      Benign. Tuning ticket SOC-441 to exclude the VPN egress
               range from this rule's geo calculation.
```

Anyone reading that in six months can tell what happened and whether you were
right. That is the whole bar.

## Shift handover

The queue outlives your shift. Hand over the things that do not fit in the
ticketing system: what you are suspicious of but cannot prove, which rule is
behaving oddly today, which host you would look at again if you had another
hour. The incidents that get missed are usually the ones that spanned a
handover and nobody carried across.

## Check yourself

- Why is an empty alert queue a warning sign rather than a goal?
- Give two reasons to escalate an alert that is labelled *low* severity.
- What three things belong in a triage note?

---
summary: A runbook turns one analyst's judgement into the whole team's floor. How to write one that gets used.
---

# Building a triage runbook

A runbook is the answer to a question a tired analyst will ask at 03:00: *what
do I do with this?* If the answer only exists in the head of whoever is on
holiday, you do not have a detection — you have an alert that someone
sometimes handles well.

## What a runbook is for

Not to replace judgement. To **raise the floor**, so the worst handling of an
alert is still competent, and to make handling consistent enough that you can
tell whether a rule is any good.

A detection without a runbook produces alerts nobody knows how to close. Those
alerts get closed anyway, arbitrarily, and the rule's statistics become
meaningless. Writing the runbook is part of shipping the rule, not paperwork
that comes after.

## The shape that works

One page. Six sections. If it does not fit on a screen, it will not be read
during an incident.

**What fired, in one sentence.** Plain language, not the rule's name.
"A user authenticated successfully from a country we have never seen them in."

**Why we care.** The threat this detects. An analyst who understands the
*why* will handle the case the rule did not anticipate; one who does not will
follow the steps and miss it.

**What to check, in order, with the query.** The actual query, pasteable, with
the field names of *your* environment. A runbook that says "check for related
activity" has outsourced the work back to the analyst.

**What benign looks like.** The common false positives, explicitly. This is
the section that saves the most time and the one most often omitted.

**What bad looks like.** The pattern that means escalate.

**The decision.** Close, tune, investigate, escalate — and for escalate, who,
by what channel, with what in the message.

## A worked example

```
ALERT:  Successful sign-in from an unfamiliar country

WHY:    Credential theft shows up as a valid login from the wrong place.
        Rare enough to be worth a look, common enough to need triage.

CHECK:  1. index=auth user=$user earliest=-30d | stats values(country)
           -> has this user ever signed in from here?
        2. Same session: any MFA prompt, or password-only?
        3. index=auth src_ip=$src | stats dc(user)
           -> is this address touching other accounts?
        4. What did the session do in the 15 minutes after?

BENIGN: Corporate VPN egress in another region. Travel (check the calendar
        or ask the user). Cloud provider ranges for CI that runs as a
        service account.

BAD:    No MFA. Address seen against more than one user. Mailbox rule
        created, or an OAuth grant issued, shortly after sign-in.

ACTION: Benign -> close with the reason. One user, MFA satisfied, no
        follow-on -> close and note. Anything in BAD -> escalate to the
        IR channel, include user, source IP, session id, and timestamps.
```

An analyst who has never seen this alert can work it from that, and two
analysts working it will reach the same place.

## Write the false positives down first

Counter-intuitive and worth the habit. Before shipping a rule, run it over
historical data and read what it catches. Those results are your BENIGN
section, written from evidence rather than imagination.

This has a second benefit: if the historical run returns four thousand hits,
you have learned the rule is not ready, and you learned it before it reached
the queue.

## Keeping it alive

A runbook rots the moment the environment moves. Field names change, a new VPN
range appears, the application is retired.

- Date it, and name an owner.
- When an analyst finds the steps wrong, the fix is part of closing the
  ticket, not a separate task for later. Later does not come.
- Review the ones attached to your noisiest rules quarterly; leave the quiet
  ones alone until they fire.

> The test of a runbook is not whether it is accurate. It is whether the last
> three people who used it changed anything.

## What does not belong in it

- Background reading. Link to it; do not inline it.
- Every possible edge case. The runbook covers the common path and says when
  to escalate; the escalation exists precisely for the rest.
- Screenshots of the console. They are stale within a release.

## Check yourself

- Why is a detection without a runbook worse than no detection, statistically?
- Which section saves the most analyst time, and why is it usually missing?
- What is the argument for writing the false-positive list *before* the rule
  goes live?

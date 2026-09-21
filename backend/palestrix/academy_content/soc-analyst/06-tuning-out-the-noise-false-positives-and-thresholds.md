---
summary: Tuning is detection engineering, not admin. How to cut volume without cutting the detection.
---

# Tuning out the noise: false positives and thresholds

A rule that fires two hundred times a day is not a detection. It is a queue
nobody reads, and the danger is not the wasted time — it is that the two
hundredth alert is real and gets the same three seconds as the other
hundred and ninety-nine.

Tuning is how you fix that. Done badly, it is how a detection quietly stops
detecting.

## Name the false positive before you suppress it

The instinct is to add an exclusion until the noise stops. Resist it long
enough to answer: **what is actually generating these?**

There is a real difference between:

- *"The vulnerability scanner authenticates to every host at 02:00"* — a
  known, named, bounded source. Safe to exclude precisely.
- *"It's mostly noise"* — not a finding. An exclusion built on this removes
  whatever else happened to be in the noise.

If you cannot name the process, the account, or the schedule producing the
alerts, you are not ready to tune. You are ready to investigate.

## Exclude narrowly, on stable fields

An exclusion should be as specific as the thing it describes.

```
# too broad: every future service account is now invisible
AccountName|startswith: 'svc-'

# specific: this scanner, from its host, doing its job
AccountName: 'svc-vulnscan'
SourceHost: 'scanner-01.campus.local'
```

Prefer fields an attacker cannot set. A hostname or an account name is
reasonable. A user agent, a window title, or a process *name* alone is not —
anyone can name their binary `chrome.exe`, and an exclusion on that is a gift.

## Thresholds change what you detect, not how much

"Alert after five failures in a minute" is not the same rule as "alert on a
failure" with the volume turned down. It is a **different detection**: it now
finds bursts and misses slow, patient guessing. That may well be what you
want. Just be aware you chose it.

Two failure modes to hold in mind:

- **Threshold too low** — you have rebuilt the noisy rule with extra steps.
- **Threshold too high** — you have written a rule that only catches the
  loudest attacker, which is the one you would have noticed anyway.

Password spraying is the case that punishes this: one attempt against five
hundred accounts never trips a per-account threshold. The right aggregation is
across accounts from a single source, not attempts against a single account.

## Suppression is not tuning

Most SIEMs let you suppress duplicate alerts for a window. That is useful for
your queue and useless as a detection improvement: the rule still fires, you
just stop seeing it. Suppression is a display setting. Tuning changes the
logic. Do not let the first hide the need for the second.

## Write the reason down, in the rule

An exclusion with no comment is a landmine for whoever reads it in a year.

```
  # svc-vulnscan authenticates to every host nightly (CHG-2291, owner: infra).
  # Review when the scanner is replaced.
  known_good:
    AccountName: 'svc-vulnscan'
```

The ticket reference and the review trigger matter more than the exclusion.
They are what let a future analyst decide whether it is still true.

## Measure the rule, not the queue

A tuned rule set should be judged on:

- **Alerts per day per rule.** Rules that dominate the queue get attention
  first.
- **Close reason distribution.** A rule closed "benign" 100% of the time for
  a month is either mis-scoped or should be `informational`.
- **True positives it has ever produced.** A rule that has never once caught
  something real, after a year, is a candidate for deletion. Deleting a rule
  is a legitimate outcome, and a rule set that only grows is a rule set that
  is slowly failing.

> The goal is not zero false positives. It is that every alert in the queue is
> one a competent analyst would want to see.

## Check yourself

- Why is "it's mostly noise" not sufficient grounds for an exclusion?
- Why is excluding on a process name weaker than excluding on an account name?
- Why does a per-account failure threshold miss password spraying, and what
  should the rule aggregate on instead?

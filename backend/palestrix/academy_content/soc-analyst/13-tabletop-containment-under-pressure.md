---
summary: Containment is a set of trade-offs made badly under time pressure. Practise the trade-offs before you need them.
---

# Tabletop: containment under pressure

Containment decisions are made with incomplete information, on a clock, with
people watching. The technical part is rarely the hard part. The hard part is
that every option costs something, and the cost lands on someone who will
object.

This module is a scenario. Work it before reading the discussion.

## The scenario

You are the on-call analyst. It is Friday, 16:40.

An EDR alert fires on `FIN-APP-02`, a finance application server: a
PowerShell process spawned by `w3wp.exe` — the IIS worker — running an
encoded command. You confirm it in the logs. You also find:

- The same encoded command ran on `FIN-APP-02` twice more, at 14:12 and 15:55.
- A successful network logon (`4624` type 3) to `FIN-DB-01` from
  `FIN-APP-02` at 15:58, using the service account `svc_finapp`.
- `svc_finapp` is a domain account. It is a local administrator on eleven
  servers. You do not yet know which.
- Outbound connections from `FIN-APP-02` to `45.83.__.__` every ~600 seconds
  since 14:10.
- Payroll runs tonight at 19:00. It runs on `FIN-DB-01`.

Your options are: isolate `FIN-APP-02`, disable `svc_finapp`, block the
outbound address at the perimeter, shut down `FIN-DB-01`, or wait and watch.

Decide what you do in the first ten minutes, and in what order. Write it down
before continuing.

## The discussion

**Blocking the C2 address is nearly free, and nearly useless alone.** It costs
no availability, so do it — but implants carry fallback addresses and domain
generation, and blocking one address tells the operator you are there while
probably not cutting them off. Free, low value, mild downside. Do it, do not
count on it.

**Isolating `FIN-APP-02` is the obvious move and is mostly right.** It stops
the beachhead. Two cautions: isolate at the network layer in a way that
preserves the running system, because powering it off destroys the memory you
will want; and understand that isolation is *visible* to the operator.

**Disabling `svc_finapp` is the decision that actually matters, and it is the
one that breaks things.** The account has already been used to reach
`FIN-DB-01`. Leaving it live leaves a working path to eleven servers. Disabling
it breaks the finance application, and probably payroll.

**Shutting down `FIN-DB-01` is almost certainly wrong.** You have one network
logon and no evidence of action on it. Shutting down a database mid-write
creates a recovery problem on top of an incident, and destroys volatile
evidence.

**Waiting and watching is defensible only with a boundary.** "Wait" is a real
option when scope is unknown and the intruder is not visibly acting — but only
as "watch for fifteen minutes *while* scoping, then act regardless". Open-ended
waiting is how four-hour dwell becomes four-week dwell.

## The trap: acting in sequence

The strongest instinct is to fix things one at a time as you find them.
Disable the account now, isolate the host in ten minutes when you have
confirmed it, block the address after that.

That is the worst available order. The first action tells the operator they
have been seen, and everything after it is a race against someone who now
knows to move. If they hold a second credential — and they usually do — they
will use it while you are still working on the first.

> Scope first, then contain everything you know about **simultaneously**.
> Partial containment is not half-safe. It is a warning shot.

## The payroll problem

You cannot answer this one technically, and pretending otherwise is the
mistake. Disabling `svc_finapp` probably stops payroll. That is a business
decision about business risk, and it is not yours to make silently.

What is yours is presenting it in the next ten minutes, in a form someone can
decide on:

```
An intruder has code execution on the finance app server and has already
authenticated to the finance database using svc_finapp. That account is
admin on eleven servers.

Disabling it now contains the intrusion and will stop tonight's payroll run.
Not disabling it leaves a working path to those servers for as long as we
wait. I need a decision in the next fifteen minutes; my recommendation is to
disable and run payroll late.
```

Impact, options, cost, deadline, recommendation. Five lines. Escalating
without a recommendation pushes the decision to someone with less information
than you.

## The second trap: containment is not eradication

Isolating the host and disabling the account stops the bleeding. It does not
remove persistence, and it does not tell you what else was touched. A host
brought back before you know how they got in gets compromised again, usually
within days, and the second time everyone is tired.

## Check yourself

- Why is disabling one compromised account, before scoping, worse than
  disabling several at once?
- What is lost by powering off a compromised host rather than isolating it on
  the network?
- The payroll conflict is not a technical decision. What is the analyst's
  actual job in that moment, and what must the escalation contain?

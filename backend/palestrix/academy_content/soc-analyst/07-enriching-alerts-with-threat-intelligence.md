---
summary: Intel should change a decision. If it does not, it is trivia attached to a ticket.
---

# Enriching alerts with threat intelligence

Enrichment means attaching context to an alert so the analyst decides faster
and better. The test for any feed, lookup or integration is exactly that: **did
it change what anyone did?** A field that never changes a decision is cost
without benefit, and most intel programmes accumulate a lot of those.

## What enrichment is actually for

Three honest uses:

- **Raising confidence.** The address your host beaconed to was reported as a
  C2 panel last week. You were already suspicious; now you can act.
- **Lowering it.** The address belongs to your own CDN, or to a scanner you
  pay for. That closes the ticket, and closing tickets correctly is most of
  the job.
- **Naming the thing.** Matching tooling or infrastructure to a known cluster
  tells you what usually happens next, which tells you where to look.

## The pyramid, and why it matters

Indicators differ in how much they cost an attacker to change:

- **Hashes** — a rebuild changes them. Cheap to evade, trivially precise.
- **IP addresses** — a new VPS. Cheap.
- **Domains** — a new registration. Slightly less cheap.
- **Network and host artifacts** — a named pipe, a URI pattern, a user agent.
  Annoying to change.
- **Tools** — real work to replace.
- **Tactics, techniques, procedures** — changing these means changing how the
  operator works. Expensive.

Detections built low on that list expire fast; detections built high survive.
Both are worth having, but do not mistake a feed of ten million hashes for a
detection capability.

## Reputation is a claim, not a fact

Every "malicious" verdict has a **who, when and why** behind it, and all three
matter:

- **Who** said so? A vendor with visibility into this kind of activity, or an
  aggregator repeating another aggregator?
- **When**? Cloud addresses churn. An IP flagged as a C2 eight months ago may
  now be someone's blog. Intel without a timestamp is close to useless.
- **Why**? "Seen in a malware sample" is weak — it might have been a sandbox
  artifact or a decoy. "Observed serving beacon traffic for this family" is
  strong.

> Treat a hit as evidence that shifts your prior, never as a verdict. The
> question is always "does this change what I do next?", and often the honest
> answer is no.

## Do not enrich everything

Enriching every field of every alert costs API quota, adds latency, and buries
the useful hit among forty neutral ones. Enrich what you would otherwise look
up by hand:

- External addresses an internal host **initiated** a connection to. Inbound
  scan sources are background radiation.
- Domains from DNS queries that resolved oddly or not at all.
- File hashes from anything that executed.

Everything else can wait for an analyst to ask.

## Internal context beats external feeds

The highest-value enrichment is nearly always your own data, and it is the
part teams skip because it is unglamorous:

- Who owns this host, and what is it for?
- Is this address in our own allocation, our cloud accounts, our partners?
- Has this user logged in from this country before?
- Was there a change request open for this host tonight?

"This is the finance file server" changes triage more than any reputation
score, and "there was a scheduled migration on this host at 02:00" closes more
tickets than any feed.

## Check yourself

- State the single test that decides whether an enrichment is worth its cost.
- Why does the age of a reputation record matter more for an IP address than
  for a TTP?
- Give two pieces of *internal* context that would change how you triage a
  beaconing alert, and say what each one changes.

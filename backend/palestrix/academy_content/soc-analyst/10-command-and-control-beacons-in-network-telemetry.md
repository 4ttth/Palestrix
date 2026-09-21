---
summary: Malware has to phone home, and phoning home on a schedule is a pattern no amount of encryption hides.
---

# Command-and-control beacons in network telemetry

Implanted code is useless to an attacker until it can be told what to do. That
means outbound connections, repeatedly, for as long as the intrusion lasts —
and repetition is the one thing encryption cannot conceal.

You will not read the traffic. You do not need to.

## What a beacon is

A beacon is a check-in: the implant asks "any instructions?", the server
answers "no", and the implant sleeps. Then it does it again. The content is
encrypted and usually uninteresting. The **rhythm** is the detection.

Three properties fall out of that, and all three are visible in NetFlow or
proxy logs with no payload inspection at all:

- **Regularity.** Connections at a near-fixed interval, over hours or days.
- **Small, symmetric transfers.** A few hundred bytes up, a few hundred down,
  over and over. Nothing is being downloaded; a question is being asked.
- **Persistence across time.** It continues through the night, through the
  weekend, through the user being logged out.

## Computing the tell

Take every connection from one internal host to one external address, sort the
timestamps, and difference them. Real user traffic produces a scatter. A
beacon produces a spike at one value.

```
# deltas between successive connections to one destination
awk '{print $1}' flows.txt | sort -n | awk 'NR>1{print $1-prev} {prev=$1}' \
  | sort -n | uniq -c | sort -rn | head
```

If one delta dominates — 3600 appearing four hundred times — you are done.
That is not a browser.

## Jitter, and why it fails anyway

Operators know this, so implants randomise: sleep 60 seconds plus or minus
30%. The perfect spike becomes a cluster.

It does not save them, for two reasons. Jitter widens the distribution but
does not move its **centre**, so the mean interval is still stable and still
unlike human traffic. And a browsing human produces bursts followed by long
silences — dozens of connections while a page loads, then nothing for twenty
minutes. An implant produces an even trickle. The shape stays wrong even when
the spike is gone.

> Look at the variance, not the exact value. Human traffic is bursty with
> gaps. Automated traffic is smooth. Smooth is the anomaly.

## The supporting signals

Interval analysis gets you the candidate. These confirm it:

- **Long-lived, low-volume sessions.** Total bytes tiny, duration enormous.
- **A destination nobody else in the estate talks to.** One host, one external
  IP, no other internal client has ever contacted it.
- **Raw IP with no DNS lookup preceding it.** Legitimate software resolves
  names. A connection with no matching query is either hard-coded or resolved
  somewhere you are not watching.
- **A user agent that is almost right.** Implants imitate browsers and get the
  version string subtly wrong, or never update it while real Chrome does every
  few weeks.
- **Certificate oddities.** Self-signed, or a subject that repeats across
  unrelated infrastructure.

## What is regular and innocent

The estate is full of things that beacon, because beaconing is how software
works:

- **Update checkers.** Windows Update, browsers, every agent you installed.
- **Monitoring and EDR agents.** These are the most beacon-like traffic on
  your network, by design.
- **Certificate revocation and time sync.** OCSP and NTP on fixed intervals.
- **Cloud storage sync clients.** Dropbox, OneDrive, polling forever.

Every one of these will hit an interval-based detection. The answer is a
baseline of known destinations, not a looser threshold — loosening the
threshold gives up the detection to avoid the work of listing your own
software.

## Where to look when you have no NetFlow

Proxy logs, DNS query logs, and firewall accept logs all carry timestamp,
source, destination. Any of them supports the same arithmetic. The technique
needs a clock and a pair of addresses; the rest is bookkeeping.

## Check yourself

- Why does encrypting the channel not defeat beacon detection?
- An implant jitters its sleep by 30%. What survives that, and what does not?
- Your EDR agent triggers your beacon rule every day. Why is raising the
  threshold the wrong fix?

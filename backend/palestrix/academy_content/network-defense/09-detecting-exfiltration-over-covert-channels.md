---
summary: Data leaves inside protocols you cannot block. Detection is about volume, shape and direction, not content.
---

# Detecting exfiltration over covert channels

An intruder who has the data still has to move it. They will not use FTP to a
foreign IP address — they will use something you allow, because you cannot
block DNS, HTTPS or email and still have a network.

So exfiltration detection is not about finding forbidden traffic. It is about
recognising permitted traffic behaving unlike itself.

## The channels, and what each looks like

**DNS tunnelling.** Data encoded in query labels, answers returned in `TXT` or
`NULL` records. Slow — a few KB/s at best — but it works from networks that
permit nothing else, and it often bypasses proxies entirely. The signature is
an enormous number of unique subdomains under one parent, long high-entropy
labels, and sustained query volume from one client.

**HTTPS to a legitimate service.** Uploads to cloud storage, a paste site, a
code host, or a webhook endpoint. This is the most common real-world channel
precisely because the destination is genuinely reputable. You cannot block
`github.com`; you can notice that this workstation has never pushed 4 GB
before.

**ICMP tunnelling.** Payload in echo request and reply bodies. Unusual now,
but ICMP is often unmonitored. Look for echo packets with large or unusual
payloads and a sustained rate.

**Email.** Attachments or body text to an external address, often via the
victim's own mailbox. Watch auto-forwarding rules — creating one is a
persistence *and* exfiltration mechanism in a single click.

**Timing and protocol-metadata channels.** Data encoded in inter-packet
delays, packet sizes, TCP options or TLS record boundaries. Very low
bandwidth, very hard to detect, rare outside research and the most capable
operators. Know they exist; do not build your programme around them.

## What to actually measure

Content inspection will not save you — the data is encrypted or encoded. These
will:

- **Volume against the host's own baseline.** Not a global threshold. "This
  workstation sent 40× its 90-day median" is a detection; "any host sending
  more than 1 GB" is a ticket generator.
- **Direction inversion.** Most hosts receive more than they send. A
  workstation whose outbound exceeds inbound has changed job.
- **Destination novelty.** First contact with this domain, by this host, and
  by anyone in the estate.
- **Timing.** Transfers at 03:00 from a device whose owner works days.
  Steady-rate transfers that look scheduled rather than human.
- **Duration.** Low-and-slow is designed to defeat volume thresholds, so
  aggregate per destination per **day or week**, not per hour. A hundred
  megabytes an hour for a week is invisible hourly and obvious weekly.
- **Session count to one destination**, which catches chunked uploads.

## The aggregation window is the whole trick

Every competent exfiltration tool has a rate limit designed to stay under a
threshold. Your counter-move is not a lower threshold — that floods you — it
is a **longer window**.

```
# outbound bytes per internal host per destination, last 7 days
nfdump -R /var/flows -t '2026-03-05/2026-03-12' \
       -s record/bytes -A srcip,dstip 'src net 10.24.0.0/16' | head -40
```

Rank by total, then compare each host against its own history. The top of that
list is a short, high-quality worklist.

## Where to place controls

- **Egress filtering.** Only the proxy and the resolver should reach the
  internet directly. A workstation that cannot open arbitrary outbound
  connections loses most of these channels immediately.
- **Own the resolver**, and block outbound `53`/DoH elsewhere, which closes
  DNS tunnelling as a bypass.
- **DLP at the proxy** for the categories you can see.
- **Alert on mail forwarding rules** to external addresses.
- **Cap or gate uploads** to personal cloud storage while permitting the
  corporate tenant.
- **Rate limit and log ICMP** rather than allowing it unconditionally.

Egress filtering is the highest-value item and the one most often skipped,
because it requires knowing what your estate legitimately talks to — which is
the same inventory work that segmentation needed.

## What is legitimate and looks identical

Baseline these or you will chase them forever:

- Backup and replication jobs, which are enormous, scheduled, and outbound.
- Cloud sync clients on ordinary workstations.
- Telemetry and crash reporting.
- Video calls, which invert the direction ratio for hours at a time.
- CI and build systems pushing artefacts.
- Security tools uploading samples for analysis.

## Check yourself

- Why is content inspection a poor basis for exfiltration detection?
- An implant is rate-limited to stay under your hourly threshold. What
  changes catch it, and why is lowering the threshold the wrong move?
- Which single network control removes the largest number of covert channels,
  and what work does it require first?

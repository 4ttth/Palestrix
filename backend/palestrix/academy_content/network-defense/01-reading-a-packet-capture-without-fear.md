---
summary: A capture is intimidating because it shows everything. The skill is knowing what to throw away first.
---

# Reading a packet capture without fear

Open a capture of a busy link and you are looking at hundreds of thousands of
packets. Nobody reads that. Analysts who look fast are not reading faster —
they are discarding faster, and they discard in a fixed order.

## Start at the top, not at the packets

Before touching a single frame, ask the capture to summarise itself. In
Wireshark, the **Statistics** menu; on the command line, `tshark`:

```
tshark -r capture.pcap -q -z conv,ip          # who talked to whom, by volume
tshark -r capture.pcap -q -z io,phs           # protocol hierarchy
tshark -r capture.pcap -q -z endpoints,ip     # every address, sorted
```

The conversation list answers most questions on its own. The biggest talker,
the longest-lived flow, and the pair that should not be talking at all are
usually visible in the first ten rows.

> Never start at packet number one. Start at the conversation list and drill
> into the one flow that looks wrong.

## Filter to a question

Capture filters decide what is recorded (BPF syntax). Display filters decide
what you see (Wireshark syntax). They are different languages and confusing
them wastes an afternoon.

```
# capture filter  (tcpdump / dumpcap)
host 10.24.7.31 and not port 22

# display filter  (Wireshark / tshark -Y)
ip.addr == 10.24.7.31 && tcp.port != 22
```

The handful of display filters that do most of the work:

```
tcp.flags.syn == 1 && tcp.flags.ack == 0     connection attempts
tcp.analysis.retransmission                  the network is unhappy
http.request                                 every request, one line each
dns                                          every lookup
tls.handshake.type == 1                      client hellos, with SNI
ip.addr == 10.0.0.5 && frame.len > 1000      bulk transfer from one host
```

## Follow the stream

Individual packets rarely tell a story; the reassembled conversation does.
Right-click a packet and **Follow TCP Stream**, or:

```
tshark -r capture.pcap -q -z follow,tcp,ascii,0
```

For cleartext protocols this is the whole investigation — you read the HTTP
request, the SMTP exchange, the FTP session as text.

## Read the handshake before the payload

The first few packets of a flow tell you what happened without any payload at
all:

- `SYN` with no reply: filtered, or the host is down.
- `SYN` then `RST`: the port is closed and something is scanning.
- `SYN`, `SYN/ACK`, `ACK`: connected. Now the payload matters.
- Many `SYN`s to many ports from one source: a port scan, visible in one
  filter.
- `FIN` versus `RST` at the end: a graceful close versus something being torn
  down.

## When it is encrypted, read the metadata

Most traffic is TLS now, and that removes the payload, not the investigation:

- **SNI** in the Client Hello names the host being visited, in cleartext.
- **The certificate** in the Server Hello gives subject, issuer and validity.
  Self-signed, or a subject that matches nothing, is a finding.
- **JA3/JA4 fingerprints** hash the client's handshake preferences. Malware
  written against a non-browser TLS library produces a fingerprint that does
  not match any browser in your estate.
- **Sizes and timing** survive encryption entirely, which is the whole of the
  beaconing module.

## Timestamps, and the mistake everyone makes once

Set the time display to something absolute before you reason about ordering.
Wireshark defaults to seconds since the capture began, which is fine for
measuring a delay and useless for correlating with a log:

```
View -> Time Display Format -> UTC Date and Time of Day
```

Then confirm the capturing host's clock was right. A capture with a skewed
clock has produced a false sequence of events, and a false sequence produces a
false story.

## What is boring

Most of a capture is:

- ARP, broadcast, and multicast chatter.
- DNS for domains everyone visits.
- TLS to major CDNs.
- Retransmissions on a congested link — a performance problem, not a security
  one.
- NTP, DHCP, and the estate's own management traffic.

Learning to recognise these at a glance is most of what "reading fast" means.

## Check yourself

- Why start at the conversation statistics rather than the first packet?
- What is the difference between a capture filter and a display filter, and
  what goes wrong if you mix them up?
- Traffic is fully encrypted. Name four things a capture still tells you.

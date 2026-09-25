---
summary: Twenty-four hours of telemetry from a network under active attack. Find the pivot, the channel, and the control that failed.
lab: netdef-capstone
pass: 80
---

# Capstone: hold a live network for 24 hours

You have flow records, resolver logs and a firewall drop log covering one day
on a segmented network. Something got in. Your job is not to stop it — that
has already happened — but to reconstruct what it did with the network, and
to name the control whose absence made it possible.

Every skill in this path is needed: reading flow, baselining, DNS as a sensor,
segmentation, and egress policy.

## The network as designed

```
10.24.1.0/24    workstations
10.24.9.0/24    application servers
10.24.20.0/24   database servers
10.0.10.0/24    management  (hypervisor, switches, out-of-band)
```

The documented policy is:

```
allow  workstations -> app-servers     443
allow  app-servers  -> db-servers      5432
allow  management   -> any             22, 443
deny   any          -> management      any
deny   any          -> any             any   (log)
```

## Exhibit A — flow, top outbound talkers by total bytes

```
src              dst                flows   bytes_out   bytes_in   window
10.24.1.42       8.8.8.8:53         41,882    9,140,221     61,204  00:00-23:59
10.24.1.42       45.83.201.14:443      287      214,880    198,340  00:00-23:59
10.24.9.11       10.24.20.7:5432     1,204    4,110,882  1,920,004  00:00-23:59
10.24.1.07       52.96.x.x:443          88   12,400,110    980,220  09:00-17:00
10.24.1.42       10.0.10.5:8006          6        4,180     22,940  02:11-02:14
```

`10.24.1.07` is a designer's workstation uploading to the corporate cloud
tenant; that is her normal weekday pattern and her 90-day median.

## Exhibit B — beacon interval analysis, 10.24.1.42 to 45.83.201.14

```
connections 287   mean interval 600.4s   stddev 41.2s
bytes out 214,880   bytes in 198,340
no DNS query preceded any connection
```

## Exhibit C — resolver log, aggregated by registered domain

```
distinct_subdomains  queries   registered_domain        top_qtype
            18,442    41,882   telemetry-sync.net       TXT
               912     3,140   office365.com            A
               488     1,902   windowsupdate.com        A
               211       640   ubuntu.com               A
```

All 41,882 queries for `telemetry-sync.net` came from `10.24.1.42`. A sample:

```
09:14:02  10.24.1.42  k3j5h2n4bk3j7f2a.telemetry-sync.net  TXT  NOERROR
09:14:02  10.24.1.42  m9x1p0q8vz2c4h6d.telemetry-sync.net  TXT  NOERROR
09:14:03  10.24.1.42  a7b2n5k9j1l3m8p0.telemetry-sync.net  TXT  NOERROR
```

## Exhibit D — firewall drop log, filtered

```
02:11:44  DROP  10.24.1.42 -> 10.0.10.5:22     tcp
02:11:47  DROP  10.24.1.42 -> 10.0.10.5:443    tcp
02:11:52  DROP  10.24.1.42 -> 10.0.10.6:22     tcp
```

Note what is in Exhibit A at 02:11 and *not* in this log.

## Work it

- Exhibit A shows two large outbound totals. One is a person doing her job and
  one is not. What distinguishes them, given that the innocent one is larger?
- The beacon in Exhibit B has 41 seconds of jitter on a 600-second sleep. Why
  did that not hide it, and what does "no DNS query preceded any connection"
  add?
- Exhibit C shows 18,442 distinct subdomains under one parent, queried almost
  entirely as `TXT`. What is that, and roughly how much data can move that way
  in a day?
- Exhibit D shows drops to management on ports 22 and 443. Exhibit A shows a
  *successful* flow from the same source to `10.0.10.5:8006` in the same
  three-minute window. What does the combination prove about the ruleset?
- Which single control, absent here, would have removed both the beacon and
  the tunnel?

## Hand in

Launch the **Network Defense Capstone** lab and record your answers. The
checker reads the files back over the guest agent and scores 20% each; you
need 80% to complete the module.

Answer in lower case, one value per file, exactly as the command shows:

```
mkdir -p /home/student/answers

# 1. The internal address that is compromised
echo '10.0.0.0' > /home/student/answers/pivot-host.txt

# 2. The protocol carrying the bulk exfiltration, one word
echo 'ftp' > /home/student/answers/exfil-protocol.txt

# 3. The registered domain the data went to
echo 'example.com' > /home/student/answers/exfil-domain.txt

# 4. The beacon's mean interval in whole seconds, digits only
echo '0' > /home/student/answers/beacon-interval.txt

# 5. The segment that was reached despite the deny rule, one word
echo 'guest' > /home/student/answers/violated-segment.txt
```

The values above are **placeholders** — replace each with what the exhibits
show. Use `echo` as written so each file ends with a single newline; the
checker compares exact contents.

For question 4, round the mean to the nearest whole second.

## The lesson in Exhibit D

The drop log is doing its job on ports 22 and 443, which is why those two
lines exist. Port 8006 is not in the deny rule's port list, so it was never
evaluated — and 8006 is the Proxmox API.

A deny rule that enumerates ports is not default deny. It is an allowlist
written backwards, and it fails silently on every port nobody thought of. The
policy in this capstone says `deny any -> management any`; the implementation
evidently did not.

> The gap between the policy on paper and the rules on the device is where
> incidents live. The only way to find it is to test from inside each segment
> and compare what answers against what should.

## Check yourself

- Why was the larger of the two big outbound flows the innocent one?
- DNS tunnelling is slow. Why is it still the channel of choice from a
  workstation with a proxy in front of it?
- What test, run monthly, would have caught the port-8006 gap before an
  intruder did?

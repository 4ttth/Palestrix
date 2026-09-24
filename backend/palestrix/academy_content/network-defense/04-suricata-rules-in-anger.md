---
summary: Writing IDS rules that catch the technique, survive contact with real traffic, and do not melt the sensor.
lab: suricata-rules
---

# Suricata rules in anger

An IDS is only as good as its rules, and most estates run thousands of
community rules nobody has read, producing alerts nobody triages. Being able
to read a rule, write one, and judge whether it is worth running is the
difference between a sensor and a noise generator.

## Anatomy

```
alert http $HOME_NET any -> $EXTERNAL_NET any ( \
    msg:"Suspicious PowerShell download cradle in User-Agent"; \
    flow:established,to_server; \
    http.user_agent; content:"WindowsPowerShell"; \
    classtype:trojan-activity; \
    sid:1000001; rev:1; )
```

Read it in three parts:

- **Action and header.** What to do, protocol, source, direction, destination.
  `$HOME_NET` and `$EXTERNAL_NET` come from the sensor's configuration, and
  getting them wrong is the most common reason a rule never fires.
- **Options.** What must be true of the traffic.
- **Metadata.** `msg`, `classtype`, `sid`, `rev`. `sid` must be unique;
  1000000 and above is the local range.

## Make it fast, on purpose

Suricata pre-filters with a fast pattern before running the expensive checks.
You control which one it picks, and the choice decides whether your sensor
keeps up.

- **Always anchor on a content match**, not on `pcre` alone. A rule with only
  a regex is evaluated against far more traffic.
- **Pick the longest, most unusual literal string** as the fast pattern. Four
  characters that appear in half your traffic is worse than useless.
- **Use sticky buffers** so matching happens in the right place:
  `http.uri`, `http.host`, `http.user_agent`, `dns.query`, `tls.sni`,
  `file.data`. Matching `content` against the raw packet when you meant the
  URI is both slower and wrong.
- **Constrain with `flow`.** `flow:established,to_server` skips everything
  that is not the direction you care about.
- **Add `depth`, `offset` and `within`** so the engine stops looking early.

```
# slow and vague
alert tcp any any -> any any (pcre:"/cmd\.exe/i"; sid:1000002;)

# anchored, scoped, and cheap
alert http $HOME_NET any -> $EXTERNAL_NET any ( \
    flow:established,to_server; http.uri; content:"/cmd.exe"; depth:64; \
    sid:1000003; rev:1; )
```

## Write for the technique, not the sample

A rule matching a hash or one hard-coded domain is obsolete the moment the
operator rebuilds. Ask what the attacker cannot easily change:

- The **structure** of a URI, not its exact value.
- A **protocol violation** — HTTP on a non-HTTP port, TLS with an impossible
  handshake.
- A **JA3/JA4 fingerprint**, which reflects the TLS library and is awkward to
  alter.
- The **shape** of a flow: size, direction, interval.

That said, an indicator rule for a live incident is completely legitimate —
just mark it as such and give it an expiry date, so it is removed rather than
lingering as noise.

## Tune before you deploy

Run the rule against captured traffic before it reaches the sensor:

```
suricata -r week-of-traffic.pcap -S local.rules -l ./out/
wc -l out/fast.log
```

Four thousand hits means the rule is not ready. This is the same discipline as
writing the runbook's false-positive section from evidence rather than
imagination — and here it is one command.

Then suppress precisely, rather than deleting the rule:

```
suppress gen_id 1, sig_id 1000003, track by_src, ip 10.24.1.7
threshold gen_id 1, sig_id 1000003, type limit, track by_src, count 1, seconds 300
```

`suppress` removes a known-good source. `threshold` caps a rule that is
correct but chatty. Reach for these before you reach for disabling.

## The sensor has to see the traffic

A perfect rule on a blind sensor catches nothing. Before debugging the rule,
confirm:

- The SPAN or tap actually carries the direction you are matching.
- The sensor is not dropping packets — check `stats.log` for `capture.kernel_drops`.
- `$HOME_NET` matches your real address space.
- The traffic is not encrypted end to end, if you are matching payload. For
  TLS, match on SNI, certificate fields or JA3 instead.

More rules "not working" are capture problems than logic problems.

## Check yourself

- Why does anchoring a rule on a long literal string matter to the sensor's
  performance?
- What is the difference between `suppress` and `threshold`, and when would
  you use each?
- A rule that matched in testing never fires in production. Name three causes
  that have nothing to do with the rule's logic.

## Lab: read the alerts, then tune them

The **Suricata in Anger** lab gives you an `eve.json` from a sensor that
watched a host get compromised, plus the ruleset that produced it. Your job is
to separate the alert that mattered from the alert that is noise, and decide
what an inline sensor should do about the real one. Four findings, read back by
the checker; 80% completes the module.

Everything you need is in `/root/case/`:

- `eve.json` has one `alert` event for an outbound session to a control server.
  Its `signature_id` is **2019401** ("ET TROJAN Generic Reverse Shell") — the
  SID that fired on the C2 channel.
- The same event's `dest_port` is **4444**. That is the port the beacon dialed.
- `eve.json` also carries hundreds of `2013028` alerts ("ET POLICY curl User-
  Agent") from the box's own package updates — matched, but pure false positive
  here. That is the noisy SID.
- `local.rules` shows the C2 rule written with `alert`. On a sensor deployed
  inline (IPS mode), the action that would stop the channel rather than just
  record it is **drop**.

Answer in lower case, one value per file:

```
mkdir -p /root/answers

echo '2019401' > /root/answers/fired-sid.txt
echo '4444'    > /root/answers/c2-port.txt
echo '2013028' > /root/answers/noisy-sid.txt
echo 'drop'    > /root/answers/tuned-action.txt
```

Use `echo` as written; the grader compares exact contents, 25% each.

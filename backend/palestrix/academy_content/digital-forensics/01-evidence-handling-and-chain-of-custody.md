---
summary: Findings are only worth what their handling can support. Chain of custody is what makes an analysis mean something later.
---

# Evidence handling and chain of custody

Forensics is not only about what you can recover. It is about what you can
*defend* — in a disciplinary hearing, in court, or to a regulator who wants to
know how you know. An analysis with a broken evidence trail can be completely
correct and still worthless.

Learn this first, because every later module produces evidence that this one
protects.

## The four properties

Every handling rule exists to preserve one of these:

- **Authenticity.** This is the data from that device, not something else.
- **Integrity.** It has not changed since acquisition, and you can prove it.
- **Completeness.** Nothing relevant was silently omitted.
- **Reproducibility.** Another examiner, given the same evidence, reaches the
  same result.

If you can state how each is satisfied for a piece of evidence, the handling
is sound.

## Chain of custody

A continuous, documented record of who had the evidence, when, and why. Any
unexplained gap breaks it, and a broken chain is an argument that the evidence
could have been altered — which is usually enough.

A record entry has five fields, and you write one for every transfer:

```
Item:      EV-2026-0031  Dell Latitude 5420, S/N 7JX2M93
From:      T. Dela Cruz (custodian)      To:  R. Almazan (examiner)
When:      2026-03-14 08:12 UTC
Why:       Acquisition of internal storage
Condition: Sealed bag 004182 intact; seal signature matches
```

Practical rules that keep it unbroken:

- **Tamper-evident bags, signed across the seal.** The signature is what makes
  the seal evidence rather than packaging.
- **One item, one identifier, from the moment of seizure.** Never renumber.
- **Photograph before you touch anything** — the machine, the screen, the
  cable layout, the serial number plate.
- **A gap in the log is a gap in the chain.** Write the entry when the
  transfer happens, not at the end of the day.

## Order of volatility

Evidence evaporates at very different rates, and you collect in the order it
disappears:

1. CPU registers and cache — effectively unreachable.
2. RAM: running processes, network connections, encryption keys, injected code.
3. Network state: ARP cache, routing table, open sockets.
4. Running system state: logged-in users, open files, mounted volumes.
5. Disk.
6. Remote and backup copies, archived logs.
7. Physical configuration and topology.

The decision this forces is the hard one in the whole discipline: **pulling
the plug preserves the disk and destroys the memory.** Memory holds the
encryption keys, the injected code that exists nowhere on disk, and the
network connections. For most intrusion work, memory is worth more than a
perfectly clean disk image — so acquire memory first, on the live machine,
accepting that doing so changes the system slightly.

Whatever you choose, record the choice and the reasoning. "We powered off to
preserve disk state" is a defensible decision. Silence is not.

## You will change the system. Document it.

Live acquisition writes to memory, updates timestamps and leaves traces. That
is unavoidable and it is fine — the standard is not "changed nothing" but
**"every change is known, minimised, and recorded"**.

- Use tools from your own trusted, read-only media, never the subject's
  binaries, which may be replaced.
- Write the output to external media, not to the evidence drive.
- Log every command you run, with its timestamp, as you run it.
- Record the tool versions. A finding produced by a tool nobody can identify
  is not reproducible.

## Hash everything, immediately

```
sha256sum evidence.dd | tee evidence.dd.sha256
```

Hash at acquisition, and verify before and after every subsequent operation.
The hash is the whole integrity argument: it proves the image you analysed on
Friday is the image you acquired on Monday.

Record it in the custody log as well as on disk. A hash file sitting beside
the image proves less than a hash written down at the moment of acquisition by
a named person.

## Work on copies, always

The original is read once, to make the image, and then sealed. Analysis
happens on a **working copy** of the image, and if the working copy is
corrupted you make another from the master.

The original device should ideally never be mounted at all — that is what the
next module's write blocker is for.

## Notes are part of the evidence

Contemporaneous notes, written as you work, with timestamps. Not written up
afterwards from memory.

What you tried and what failed belongs in them too. An examiner who records
only successful steps has produced a narrative; one who records everything has
produced a record. When the other side asks whether you considered an
alternative explanation, the notes either answer or they do not.

> Assume every case will be reviewed by someone competent, hostile, and
> working two years later from your notes alone. Write for that reader.

## Check yourself

- Why is memory often more valuable than disk in an intrusion, and what does
  acquiring it cost you?
- What does an unexplained gap in the chain of custody allow someone to argue?
- The standard is not "change nothing". What is it, and why is the difference
  practical rather than pedantic?

---
summary: Every technique for destroying evidence leaves evidence of itself. Learn the tells, and why the act of hiding is itself a finding.
---

# Anti-forensics and how it fails

Intruders delete logs, forge timestamps, wipe files and clear history. Most of
it works partially, and partial success is the examiner's opportunity: the
inconsistency between what was cleaned and what was missed is itself evidence,
and often stronger evidence than what was destroyed.

## Timestomping

Forging file timestamps to blend with the operating system's own files.

**How it fails on NTFS.** There are two timestamp sets — `$STANDARD_INFORMATION`,
which tools and the API read and which timestomping utilities modify, and
`$FILE_NAME`, which is much harder to alter. Compare them:

```
mft_dump --output-format csv $MFT | grep -i suspicious.dll
```

Disagreement is forgery. Other tells that cost nothing to check:

- **Zeroed sub-second precision.** Windows records timestamps to
  100-nanosecond resolution; a time ending in exactly `.0000000` was set by a
  tool, not by the filesystem.
- **Timestamps outside the system's own life** — a file "created" before
  Windows was installed.
- **Nanosecond truncation on ext4**, where a tool set seconds only.
- **Contradiction with other artefacts.** The MFT says March 2024; prefetch,
  `$UsnJrnl` and the event log say last Tuesday. The corroborating artefacts
  win, and there are more of them.

## Log clearing

- Windows `1102` records that the Security log was cleared, and `104` covers
  other logs. The act is logged by design.
- Cleared logs are recoverable: `.evtx` records carved from unallocated space,
  and copies already shipped to the SIEM.
- Linux truncation leaves `wtmp`/`btmp` whose size and mtime contradict the
  system's uptime and the accounts that are clearly logged in.
- Selective editing is harder than it looks: removing lines from a journal
  breaks sequence numbers and, where journald signing is enabled, the seal.

**The clean-up window is itself the finding.** A gap in logging, bounded by
normal activity on both sides, tells you when the intruder was active even
though it tells you nothing about what they did.

## Secure deletion, and why it usually is not

Overwriting a file removes its content but not the surrounding evidence:

- MFT records, `$UsnJrnl` and `$LogFile` entries recording the creation and
  deletion.
- `LNK` files, Jump Lists, shellbags and `RecentDocs` referencing the path.
- Prefetch proving the wiping tool itself executed.
- Registry entries created by installing or running that tool.
- Copies elsewhere: backups, cloud sync, temp directories, the page file.

A file that was securely deleted is frequently provable **as an event** even
when the content is unrecoverable. "A file named X existed at path Y, was
opened on this date, and was removed with tool Z at this time" is a finding.

> Anti-forensics converts a content question into a behaviour question. The
> behaviour is often more incriminating than the content would have been.

## Encryption and steganography

Encryption genuinely works. A properly encrypted container with a strong
passphrase and no key in memory is not recoverable, and pretending otherwise
wastes time.

What remains: the container's existence, its size and timestamps, the software
installed to make it, shellbags and `MRU` entries showing it was mounted, and
memory if the system was live.

Steganography is rare in practice. The usual indicator is not statistical
analysis of images but the presence of the tool, plus files whose size is
inconsistent with their apparent content.

## Living off the land, and timeline gaps

Sophisticated operators avoid leaving artefacts rather than deleting them:
using built-in binaries, executing only in memory, taking no files to disk.

This defeats file-based detection and leaves the timeline as the primary
tool — which is why the timeline module sits where it does in this path.
Process creation events, command lines, and memory analysis are what remains
when nothing was written down.

## What this means for how you work

- **Never rely on a single artefact.** Corroboration is the defence against
  every technique above.
- **Look for the absence.** Gaps, contradictions, and things too clean.
  A workstation with an empty browser history and no `RecentDocs` is not a
  tidy user; it is a finding.
- **Collect memory**, which defeats a large share of disk-focused
  anti-forensics.
- **Get logs off the box in real time.** Forwarded logs cannot be edited
  retroactively, and this single control defeats log clearing entirely.

## Check yourself

- Why does comparing `$STANDARD_INFORMATION` with `$FILE_NAME` detect
  timestomping?
- A file was securely wiped and its content is unrecoverable. Name three
  artefacts that still establish it existed.
- Why is centralised log forwarding a more effective counter to log clearing
  than any recovery technique?

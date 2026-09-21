---
summary: One sorted sequence built from every artefact on the system. The most powerful technique in forensics, and the easiest to get wrong.
---

# Timeline analysis from the artifacts up

Individual artefacts answer small questions. A timeline answers the big one:
*what happened, in what order*. Merge every timestamped artefact into one
sorted sequence and causation becomes visible — a download, then an execution,
then a registry write, then an outbound connection, in that order, seconds
apart.

## Build it in two passes

**A filesystem timeline** from metadata alone is quick and shows you where to
look:

```
fls -r -m C: case31.dd > body.txt
mactime -b body.txt -d -z UTC 2026-03-12..2026-03-15 > fs-timeline.csv
```

**A super timeline** merges the filesystem with everything else — event logs,
registry, browser history, prefetch, shellbags, scheduled tasks, journals:

```
log2timeline.py --storage-file case31.plaso case31.dd
psort.py -o dynamic -w super.csv case31.plaso \
         "date > '2026-03-12 00:00:00' AND date < '2026-03-15 00:00:00'"
```

The super timeline is where the work happens. It is also enormous — millions
of rows for a normal workstation — so it is useless until you filter it.

## MACB, and what each letter really means

Four timestamps per file, and their differences are the evidence:

- **M — Modified.** Content last changed.
- **A — Accessed.** Last read. Unreliable: Windows has disabled updates by
  default for years, and Linux is usually mounted `relatime`.
- **C — Changed (metadata).** Permissions, ownership, or the MFT record
  itself. **This is not creation time**, and confusing them is the classic
  beginner error.
- **B — Born (created).**

NTFS keeps two sets: `$STANDARD_INFORMATION`, which is what tools and the API
show and what timestomping utilities modify, and `$FILE_NAME`, which is
copied from the parent directory operation and is much harder to forge.

> When the two sets disagree, you are not looking at a filesystem quirk. You
> are looking at someone editing timestamps. Compare them routinely.

A modification time *earlier* than the creation time is the other free tell —
usually a file copied from elsewhere, sometimes a forgery.

## Time zones will ruin the analysis

Normalise everything to UTC at load time, and record the system's configured
zone separately.

An artefact recorded in local time merged with one in UTC produces a
sequence that is wrong by hours, and a wrong sequence produces a wrong causal
story — which is worse than no story, because it is persuasive.

Check three things before trusting any ordering: the system's time zone, the
hardware clock offset, and whether NTP was actually working. A host with a
skewed clock needs every one of its timestamps corrected by a stated offset,
and the correction goes in the report.

## Pivot, do not read

Nobody reads a super timeline. You pivot through it:

1. Start from one known event with a good timestamp — an alert, a login, a
   downloaded file.
2. Look at a narrow window around it. Five minutes, then an hour.
3. Find the next anchor inside that window.
4. Repeat, widening only when the window runs dry.

Filter aggressively. Exclude the directories that generate constant noise
(`WinSxS`, package caches, browser caches, temp), then re-include them
deliberately if the trail leads there.

## The artefacts that carry the most weight

- **Prefetch** — proves a program executed, when, and how many times.
- **Event logs** — 4624/4625 for logons, 4688 for process creation, 7045 for
  service installation.
- **Registry** — `UserAssist`, `ShimCache`, `AmCache`, `RunMRU`, and the
  persistence keys, all timestamped.
- **Shellbags** — folders that were browsed, including on removable and
  network volumes that are no longer present.
- **`$UsnJrnl`** — creations, renames and deletions, often weeks of them.
- **Browser history and downloads** — usually the origin of the whole story.
- **Scheduled tasks and cron** — with their own creation timestamps.

## What a good timeline entry looks like

```
2026-03-12 09:14:02Z  BROWSER   Downloaded invoice_q1.xlsm from cdn.delivery-net.io
2026-03-12 09:14:05Z  FS        B  C:\Users\r.santos\Downloads\invoice_q1.xlsm
2026-03-12 09:16:31Z  PREFETCH  EXCEL.EXE executed (run count 14)
2026-03-12 09:16:33Z  FS        B  C:\Users\r.santos\AppData\Roaming\mso\upd.dll
2026-03-12 09:16:34Z  REGISTRY  Run key written: "MsoUpdate"
2026-03-12 09:18:07Z  NETWORK   First outbound to 45.83.201.14:443
```

Six lines, four artefact types, one unambiguous story: download, open,
drop, persist, call home. No single artefact says that. The sequence does.

## Check yourself

- What is the difference between the C and B timestamps, and why does the
  confusion matter?
- Why compare `$STANDARD_INFORMATION` against `$FILE_NAME`, and what does a
  mismatch indicate?
- Why is a timeline built from mixed time zones worse than no timeline at all?

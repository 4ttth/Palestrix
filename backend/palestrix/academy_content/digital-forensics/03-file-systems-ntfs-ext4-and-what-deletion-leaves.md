---
summary: Deleting a file removes a pointer, not the data. What survives, for how long, and where to look for it.
---

# File systems: NTFS, ext4, and what deletion leaves

"Deleted" almost never means erased. It means the space is marked reusable and
the directory entry is gone. The content stays until something writes over it,
and the metadata often outlives the content.

Knowing which structures hold what is the difference between recovering a file
and reporting that it is gone.

## NTFS: everything is in the MFT

The Master File Table holds one record per file — name, timestamps, permissions
and either the data itself or pointers to it.

**Resident data.** A file small enough (roughly under 700 bytes) is stored
*inside* its MFT record. Small text files, notes and configuration fragments
are therefore recoverable in full from the MFT alone, even after the clusters
they would have used are long reused.

**Deletion** flips an "in use" flag on the record and clears the bitmap entry.
The record itself — name, timestamps, cluster runs — stays until that slot is
reallocated. `$MFT` is the single highest-value artefact on an NTFS volume.

The other structures worth knowing by name:

- **`$LogFile`** — the transaction journal. Hours to days of recent metadata
  operations, including creations, renames and deletions.
- **`$UsnJrnl`** (`$J`) — the change journal. A record per change per file,
  often covering weeks. It will tell you a file existed and was deleted even
  when the MFT record is gone.
- **`$I30`** — directory index. Slack within index pages retains entries for
  files that were deleted from the directory.
- **`$Recycle.Bin`** — `$I` files hold original path, size and deletion time;
  `$R` files hold the content.
- **Alternate data streams.** A file can carry additional named streams
  (`file.txt:hidden`) that do not appear in a normal listing and do not affect
  the reported size. `Zone.Identifier` is the common benign one, and it is
  itself evidence: it records that a file came from the internet.

## ext4: inodes, and the journal that helps less

Metadata lives in inodes; directory entries map names to inode numbers.

On deletion, ext4 zeroes the block pointers in the inode. That is a real loss
compared to NTFS — you frequently lose the map from file to content, which is
why undelete on ext4 is harder and carving matters more.

What still helps:

- **The journal (`jbd2`)** may contain older copies of inode blocks, including
  the pointers before they were cleared. `ext4magic` and `extundelete` work by
  mining exactly this.
- **Directory entry slack.** Removed entries are unlinked by adjusting record
  lengths; the old name often remains in the gap.
- **Inode timestamps** include `ctime` and a deletion time (`dtime`), which
  alone can establish when a file was removed.

## Slack space

A file rarely fills its last cluster exactly. The remainder is **file slack**,
and it contains whatever was in those bytes before — part of an older,
deleted file.

This is why small fragments of long-gone documents turn up in the middle of
unrelated files, and why searching slack is a standard step rather than an
exotic one.

## Carving: recovery without metadata

When metadata is gone, search the raw image for known file signatures and
recover by structure alone:

```
foremost -t jpg,pdf,doc,zip -i case31.dd -o carved/
scalpel  -c scalpel.conf     case31.dd -o carved/
bulk_extractor -o bulk/      case31.dd     # emails, URLs, card numbers
```

Two consequences of carving that must appear in the report:

- **You lose the filename, the path and the timestamps**, because those lived
  in the metadata you no longer have.
- **Fragmented files usually fail.** Carvers assume contiguity; a file split
  across the disk recovers as its first fragment plus whatever followed it.

`bulk_extractor` deserves a mention of its own — it ignores filesystem
structure entirely and scans for patterns, which means it finds material in
unallocated space, swap, hibernation files and memory dumps that structured
tools skip.

## What actually destroys data

- **Overwriting.** The only reliable method on spinning media. One pass is
  sufficient on any modern drive; multi-pass wiping is folklore.
- **Losing the encryption key.** Instant and complete, which is why encrypted
  volumes make deletion trivial and recovery impossible.
- **SSD garbage collection.** The controller erases TRIMmed blocks on its own
  schedule. This is not deliberate anti-forensics; it is the drive doing its
  job, and it is the largest single reason a recovery fails on modern
  hardware.

## Check yourself

- Why can a small text file be recovered in full from the MFT even after its
  clusters were reused?
- What does ext4 clear on deletion that NTFS does not, and which artefact
  helps you recover from it?
- Name two things you permanently lose when a file is recovered by carving
  rather than from metadata.

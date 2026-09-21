---
summary: Getting a bit-for-bit copy without touching the original, and proving afterwards that you did.
---

# Disk imaging and write blockers

An image is a bit-for-bit copy of a storage device, including the parts the
operating system does not show you: unallocated space, slack, deleted file
content, and the metadata that makes timeline analysis possible.

Copying files is not imaging. A file copy takes what the filesystem admits
exists, which excludes most of what you came for.

## Block the writes before you connect anything

The moment a modern operating system sees a disk, it wants to write to it. It
mounts it, updates access times, writes recovery data, indexes it for search.
Windows will happily write a `System Volume Information` directory to your
evidence.

- **Hardware write blocker.** A physical device between the drive and the
  workstation that passes reads and refuses writes. The defensible option, and
  the one to use when the case may be contested.
- **Software write blocking.** Operating-system-level read-only enforcement.
  Cheaper, adequate for internal investigations, and dependent on
  configuration being right — which is exactly what someone will question.

On Linux, if you must work without hardware:

```
blockdev --setro /dev/sdb
blockdev --getro /dev/sdb        # must print 1 before you proceed
mount -o ro,noload,noatime /dev/sdb1 /mnt/evidence
```

Verify the read-only state rather than assuming it. And be aware that
`--setro` is a courtesy to well-behaved software, not a physical guarantee.

## Formats, and why `dd` alone is the weakest choice

**Raw (`dd`, `.img`).** Every byte, no structure, no metadata, no compression.
Universally readable, and the largest possible file.

**E01 (EnCase Expert Witness).** Compressed, carries case metadata, and — the
part that matters — stores checksums **per block**. Corruption is localised
and detectable rather than silently poisoning the whole image.

**AFF4.** Open, modern, handles sparse data and very large devices well.

Prefer a format with embedded integrity checking. A raw image with a single
hash tells you *that* something changed, never *where*, and one flipped bit on
a 2 TB image invalidates the entire hash.

## Imaging, with verification built in

```
# raw, with logging and a hash computed during acquisition
dcfldd if=/dev/sdb of=/evidence/case31.dd hash=sha256 \
       hashlog=/evidence/case31.hashes bs=4M conv=noerror,sync \
       statusinterval=256

# E01, with case metadata and per-block checksums
ewfacquire -t /evidence/case31 -C 31 -D "Latitude 5420 internal" \
           -E "R. Almazan" -e "Palestrix IR" -f encase6 -d sha256 /dev/sdb
```

`conv=noerror,sync` matters on a failing drive: continue past read errors, and
pad the unreadable sectors with zeros so **every subsequent offset stays
correct**. Without `sync` a bad sector shifts everything after it and the
image is quietly misaligned.

Plain `dd` with no hashing, no log and no error handling is the tool people
reach for and the one least suited to the job.

## Verify, and record the verification

```
sha256sum /dev/sdb                    # source, through the write blocker
sha256sum /evidence/case31.dd         # image
```

They must match. Note both in the custody log with the time, and hash the
working copy too so you can prove the copy is faithful.

If they do not match, do not proceed and do not "try again and see". Establish
why: a failing drive, a loose cable, or a write that got through the blocker
are all different problems with different consequences for the case.

## The cases where a clean image is not available

**Full-disk encryption.** An image of an encrypted volume is an image of
ciphertext. If the machine is running and unlocked, the key is in memory —
which is an argument for acquiring memory first, and sometimes for imaging the
*mounted, decrypted* volume live, documented as such.

**Hardware failure.** A drive that will not read cleanly needs a specialist.
Repeated read attempts can finish off a marginal drive; stop and escalate
rather than trying once more.

**SSDs and TRIM.** The one that undermines a core assumption. On an SSD, the
controller may have already erased deleted blocks in the background, and it
does so independently of the operating system. Deleted-file recovery is far
less reliable than on spinning media, and simply powering the drive on can
allow garbage collection to proceed. Image promptly and expect less.

**Devices you cannot remove.** Soldered storage, RAID sets, cloud volumes. A
RAID must be imaged as a set with its configuration recorded, or reassembled
from member images; imaging one member alone yields stripes of nothing.

**Scale.** A 16 TB array cannot always be fully imaged in the available
window. Targeted acquisition of specific artefacts is a legitimate answer —
provided you document the scope decision and what you therefore did not
collect.

> "We imaged the whole disk" is the ideal. "We collected these artefacts for
> these reasons and did not collect the rest" is acceptable. "We collected
> some things" is not.

## Check yourself

- Why is copying files off a drive not an acceptable substitute for imaging
  it?
- What does `conv=noerror,sync` protect against, and what goes wrong if you
  omit `sync`?
- Why is deleted-data recovery less reliable on an SSD than on a spinning
  disk, and what should you do differently?

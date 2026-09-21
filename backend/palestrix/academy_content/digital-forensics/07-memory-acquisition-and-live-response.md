---
summary: Memory holds what the disk never will — keys, injected code, live connections. Capturing it is a decision with a deadline.
---

# Memory acquisition and live response

RAM contains things that exist nowhere else: encryption keys, decrypted
content, code that was never written to disk, the actual network connections,
and command lines of processes that have since exited.

It is also gone the moment the power is. Every other decision at the scene is
secondary to this one.

## Capture memory before anything else

The order of volatility says memory outranks disk. In practice this means: if
the machine is on, capture RAM first, then decide about powering off.

Acquisition writes the image to external media and unavoidably perturbs the
system — your tool occupies memory and the page file may change. That is
accepted practice. Document the tool, version, time and destination.

```
# Windows
winpmem_mini.exe C:\...no.  ->  E:\case31-mem.raw          # external volume
DumpIt.exe /OUTPUT E:\case31-mem.raw

# Linux
insmod lime.ko "path=/mnt/ext/case31-mem.lime format=lime"

# a VM: the cleanest capture of all
qm suspend <vmid>          # the hypervisor writes a consistent memory file
virsh dump --memory-only <domain> /evidence/case31.dump
```

The virtual-machine case is worth noting: a snapshot taken by the hypervisor
is atomic and involves running nothing inside the guest. When the subject is a
VM, that is strictly the best option available.

## Never write to the subject's disk

Output goes to external media or across the network. Writing a multi-gigabyte
memory image onto the evidence drive overwrites unallocated space — which is
exactly where deleted files live — and you will have destroyed disk evidence
to collect memory evidence.

Run your tools from your own trusted media too. The subject's binaries may
have been replaced, and a compromised `tasklist` reporting no malicious
process is a result you would believe.

## Live triage, when imaging everything is not possible

Sometimes you cannot take the machine. Collect volatile state in order,
logging each command with a timestamp:

```
date -u                              # establish the clock and its offset
netstat -anob                        # connections with owning process
tasklist /v   |  ps auxww            # processes
net session   |  w                   # who is connected
arp -a ; route print                 # network state
schtasks /query /fo LIST /v          # scheduled tasks
dir /a /s C:\Users\...               # timestamps before anything changes them
```

Each command changes the system slightly. That is acceptable and documented;
what is not acceptable is running them without a record.

## Encryption makes this urgent rather than optional

If the disk is encrypted and the machine is unlocked, **the key is in memory
and nowhere else you can reach**. Powering off converts a recoverable case
into a ciphertext blob.

The rule at the scene: encrypted and running means capture memory now, before
any discussion about whether to pull the plug. Tools can extract BitLocker,
LUKS and FileVault keys from an image, but only from an image you took while
it was unlocked.

## What you get out of it

- **Processes**, including those hidden from the live API by a rootkit.
- **Network connections**, including closed ones still in kernel structures.
- **Command lines and environment**, often the whole story.
- **Injected code** — the entire fileless-malware class lives here.
- **Encryption keys and passwords**, frequently in cleartext.
- **Decrypted content**: documents open, messages read, pages visited in
  incognito.
- **Registry hives**, which are partly memory-resident.
- **Deleted files** still held open by a process.

## When memory is not available

The page file and hibernation file are memory that landed on disk:

```
C:\pagefile.sys       C:\swapfile.sys       C:\hiberfil.sys
/swapfile  or  the swap partition
```

`hiberfil.sys` is a compressed snapshot of RAM from the last hibernation and
can be converted into something a memory analysis tool will read. It is
historical rather than current, which is sometimes better — it may predate the
attacker's clean-up.

> If you take one rule from this module: **encrypted, running, and about to be
> touched means capture memory first.** Everything else can be reconsidered
> later; that window cannot be reopened.

## Check yourself

- Why does full-disk encryption make memory acquisition urgent rather than
  merely useful?
- Why must the memory image never be written to the subject's own disk?
- Give three things recoverable from memory that will never appear on disk.

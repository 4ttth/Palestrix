---
summary: journalctl, auditd, and knowing which one answers the question you actually have.
---

# Linux audit trails and journald

`auth.log` tells you who got in. It does not tell you what they did once they
were there. For that you need the systemd journal, and sometimes `auditd`, and
knowing which is which saves a lot of wasted time.

## The journal is not a file

`systemd-journald` stores structured records, not lines of text. Every entry
carries fields — the unit that produced it, the PID, the UID, the boot it
belongs to — and `journalctl` queries them. Treating it like a text file and
reaching for `grep` throws away everything that makes it useful.

```
# everything sshd said this boot
journalctl -u ssh -b

# since a moment, in a parseable form
journalctl --since "2026-09-20 02:00" --until "2026-09-20 03:00" -o short-iso

# just one process
journalctl _PID=20512
```

`_PID=` is a field match, not a search. That distinction is the whole point:
you are asking the journal a question, and it answers from an index.

## Fields worth knowing

- `_SYSTEMD_UNIT` — which service. The honest way to scope a query.
- `_UID` / `_AUDIT_LOGINUID` — who. The second survives `su` and `sudo`,
  which is exactly what you want when tracking a session across identity
  changes.
- `_BOOT_ID` — which boot. `journalctl -b -1` is the previous one, which is
  where you look when a box was rebooted to clear something up.
- `PRIORITY` — syslog severity, so `-p err` narrows hard.

## Persistence is not the default everywhere

On many images the journal is volatile: it lives in `/run/log/journal` and
**dies with the reboot**. If `/var/log/journal` does not exist, you get the
current boot and nothing else.

```
journalctl --list-boots     # if this shows only 0, history is not kept
```

This is the single most common reason an investigation stalls on a Linux
host, and it is worth checking *first*, before you build a timeline you
cannot finish. Making it persistent is one directory:

```
mkdir -p /var/log/journal && systemd-tmpfiles --create --prefix /var/log/journal
```

## auditd answers different questions

The journal records what services chose to say. `auditd` records what the
kernel saw, whether the process wanted it logged or not. That makes it the
right tool for a narrow set of questions:

- Who executed this binary?
- Who read or changed this specific file?
- What syscalls did this process make?

A rule watching a sensitive file looks like this:

```
auditctl -w /etc/shadow -p wa -k shadow-access
ausearch -k shadow-access -i
```

`-w` watches a path, `-p wa` cares about writes and attribute changes, `-k`
tags the rule so you can find its records later. The `-k` key is not
decoration; without it you are searching raw records by hand.

## Why not just audit everything

Because you will drown, and so will the disk. Broad syscall auditing on a busy
host produces enormous volume and measurable slowdown, and the records are
detailed enough that nobody reads them. Audit rules are a scalpel: a handful
of paths that matter, each with a key, reviewed when something else points you
at them.

> The journal is your default. `auditd` is what you turn on when you have a
> specific question about a specific file or binary, and you accept the cost
> of answering it.

## Reading a `sudo` chain

Putting it together. A session that came in over SSH and escalated:

```
journalctl _AUDIT_LOGINUID=1001 --since "02:19" -o short-iso
```

`_AUDIT_LOGINUID` is set at login and does not change when the user becomes
someone else, so this follows `deploy` through `sudo` into a root shell and
shows everything that shell's children logged. That is the query that turns
"someone escalated" into "here is what they ran".

## Check yourself

- Why is `journalctl _PID=20512` different in kind from piping the journal
  into `grep`?
- What should you check before building a timeline from a Linux host's
  journal, and why?
- Give one question `auditd` answers that the journal cannot, and say why
  auditing broadly is still a bad default.

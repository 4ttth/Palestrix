---
summary: Access is temporary until an intruder makes it permanent. The places they do that are few, well-known, and checkable.
---

# Detecting persistence on a compromised host

An intruder who loses their shell when the machine reboots has not really
taken it. Persistence is the step that converts access into ownership, and it
is the single most valuable thing to hunt for, because unlike the intrusion
itself it is still **there**, on disk, waiting to be found.

## Why this is the hunt with the best odds

Most attacker activity is transient. A process runs, a connection closes, a
credential is used. If you were not watching at the time, it is gone.

Persistence is different. It has to survive a reboot, which means it has to be
written down somewhere the operating system will read later. That somewhere is
a finite list, and you can go and look at it today for an intrusion that
happened in March.

> The asymmetry is yours for once: the attacker must leave something behind,
> and you get unlimited time to find it.

## Where it lives on Linux

**Cron.** The first place anyone looks, and still productive. Check every
crontab, not just root's:

```
for u in $(cut -d: -f1 /etc/passwd); do crontab -l -u "$u" 2>/dev/null; done
ls -la /etc/cron.d/ /etc/cron.daily/ /etc/cron.hourly/
```

**systemd units and timers.** More common now than cron, and quieter, because
fewer people audit them:

```
systemctl list-timers --all
systemctl list-unit-files --state=enabled
```

A unit in `/etc/systemd/system/` with a recent mtime and an `ExecStart` that
points at `/tmp`, `/dev/shm`, or a user's home directory is the finding.

**`authorized_keys`.** The quietest of the lot and the one most often missed,
because a new line in a file nobody reads changes nothing visible:

```
find /home /root -name authorized_keys -exec ls -la {} \; -exec cat {} \;
```

**Shell profiles.** `~/.bashrc`, `~/.profile`, `/etc/profile.d/*.sh`. Executed
on every login, edited by almost nobody.

**Web shells.** If the box runs a web server, the document root is a
persistence location. A `.php` file whose mtime differs from every other file
in the directory is worth opening.

## Where it lives on Windows

**Run keys.** `HKLM\Software\Microsoft\Windows\CurrentVersion\Run` and the
`HKCU` equivalent. Ancient, still used, because it still works.

**Scheduled tasks.** `schtasks /query /fo LIST /v`, or read
`C:\Windows\System32\Tasks\` directly — the tasks are XML files, and their
timestamps are evidence.

**Services.** Event `7045` at install time, and afterwards a service whose
binary path is unquoted, lives outside `Program Files`, or has a display name
that mimics a real one (`Windcws Update`).

**WMI event subscriptions.** The advanced option, and the one most estates
have never audited. A permanent subscription is three objects — a filter, a
consumer, and a binding — and it fires without any file on disk being executed
directly:

```
Get-WmiObject -Namespace root\subscription -Class __EventConsumer
Get-WmiObject -Namespace root\subscription -Class __FilterToConsumerBinding
```

If you find one of those on a workstation, you are not looking at a
commodity infection.

## The timestamp is the shortcut

You rarely have to read every file. You have to find the ones that changed
when the intrusion did. Once you know roughly when the host was touched:

```
find /etc /usr/local -newermt '2026-03-14' -type f -ls
```

Everything legitimate that changed that day will be explainable by a package
update, and package updates come in batches with matching timestamps. The file
that changed alone is the one to read.

## What looks like persistence and is not

- **Vendor agents.** EDR, backup, inventory and monitoring tools all install
  services, tasks and cron jobs that look exactly like the thing you are
  hunting. Learn your estate's normal set once and you stop rediscovering it.
- **Package post-install hooks.** `/etc/cron.daily/` is full of them.
- **Developer convenience.** A engineer's `authorized_keys` on a box they
  administer is a policy problem, not an incident.

Confirm the boring explanation before you escalate, and write it down so the
next person does not redo the work.

## Finding one means finding the rest

Competent intruders install more than one, deliberately, and stagger them: a
loud one to be found and removed, a quiet one to survive the clean-up.

So the question after a hit is never "is it gone" but **"what else was written
in the same window"**. Take the timestamp of what you found and sweep every
other persistence location for changes near it, on that host and on every host
that account touched.

## Check yourself

- Why does persistence give a hunter better odds than hunting the intrusion
  itself?
- Name three persistence locations that involve no new executable file.
- You find a malicious cron job. Why is removing it the wrong thing to do
  first, and what do you do instead?

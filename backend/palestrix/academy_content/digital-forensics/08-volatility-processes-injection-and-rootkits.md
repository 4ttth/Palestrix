---
summary: Turning a memory image into findings — the plugin order that works, and what each one actually proves.
---

# Volatility: processes, injection, and rootkits

A memory image is a few gigabytes of undifferentiated bytes until something
imposes structure on it. Volatility walks the kernel's own data structures and
reconstructs processes, connections, loaded modules and injected regions.

This module is about the order to run things in, and how to read the output
sceptically.

## Start with the process tree

```
vol3 -f case31-mem.raw windows.pstree
vol3 -f case31-mem.raw windows.pslist
vol3 -f case31-mem.raw windows.psscan
```

The three are deliberately different, and the differences are the finding:

- **`pslist`** walks the kernel's active process list. Fast, and a rootkit
  that unlinks itself will not appear.
- **`psscan`** scans raw memory for process structures. Slower; finds
  unlinked processes **and** terminated ones whose structures survive.
- **`pstree`** shows parentage, which is where anomalies stand out.

> A process in `psscan` that is absent from `pslist` is either exited or
> hidden. Both are worth knowing about, and telling them apart is the next
> hour of work.

**Parentage is the fastest anomaly detector available.** Learn what is normal:

- `services.exe` parents most service processes.
- `svchost.exe` is parented by `services.exe`, always.
- `lsass.exe`, `csrss.exe` and `wininit.exe` have exactly one instance each
  (per session for `csrss`).
- `explorer.exe` parents user-launched applications.

So: `winword.exe` parenting `powershell.exe` is the macro chain. `svchost.exe`
parented by anything other than `services.exe` is masquerading. A second
`lsass.exe` is a credential-theft tool wearing a costume.

Check spelling too — `scvhost.exe`, `lsaas.exe`, `csrsss.exe` — and check the
path: the real ones live in `System32`, not in `%TEMP%` or a user profile.

## Then the command lines

```
vol3 -f case31-mem.raw windows.cmdline
```

Often the entire investigation. Encoded PowerShell, `rundll32` with an unusual
export, `certutil -urlcache -f`, an archive utility pointed at a staging
directory. The command line survives in memory long after the process exits.

## Then the network

```
vol3 -f case31-mem.raw windows.netscan
```

Connections with the owning process, including closed ones whose structures
remain. This is where the beacon destination from the network path gets
attributed to a specific binary.

## Injection: code with no file behind it

```
vol3 -f case31-mem.raw windows.malfind
```

`malfind` looks for memory regions that are private, executable, and not
backed by any file on disk — the signature of injected code. It prints a hex
dump and disassembly; an `MZ` header at the start of such a region is a PE
injected into another process.

False positives exist — JIT compilers, .NET, browsers and anti-virus all
produce legitimate private executable memory — so read the content rather
than counting hits.

Related plugins worth knowing:

- **`ldrmodules`** compares three kernel lists of loaded modules. A DLL
  missing from one is unlinked, which is deliberate hiding.
- **`hollowfind`** and `malfind` together catch process hollowing, where a
  legitimate process is started suspended and its image replaced.
- **`svcscan`** enumerates services from memory, catching ones hidden from the
  service manager.
- **`modscan`** and **`ssdt`** cover kernel modules and syscall-table hooks.

## Credentials and keys

```
vol3 -f case31-mem.raw windows.hashdump
vol3 -f case31-mem.raw windows.lsadump
vol3 -f case31-mem.raw windows.cachedump
```

Which tells you what the attacker could have taken with the same access. If
`lsass` was touched, assume every credential used on that host is compromised
and scope accordingly.

## Linux, briefly

```
vol3 -f mem.lime linux.pslist
vol3 -f mem.lime linux.bash            # shell history from memory
vol3 -f mem.lime linux.check_syscall   # hooked syscalls
vol3 -f mem.lime linux.malfind
```

`linux.bash` is the standout: shell history recovered from memory, including
commands from a session where `HISTFILE` was unset — one of the most common
anti-forensic steps, defeated entirely.

Linux analysis needs a **symbol table matching the exact kernel**. Record the
kernel version at acquisition or the image may be unreadable later.

## Read the output like an analyst, not a scanner

Every plugin produces false positives. A finding is a *lead*:

- Confirm with a second artefact. Injected code plus an outbound connection
  plus a persistence entry is a conclusion; any one alone is a hypothesis.
- Compare against a clean image of the same build where you can.
- Remember your own tools are in the image, and EDR looks a great deal like
  malware from memory's point of view.

## Check yourself

- What does it mean when a process appears in `psscan` but not `pslist`?
- Why is `malfind` prone to false positives, and how do you triage its output?
- Why is `linux.bash` valuable even when the shell history file is empty?

---
summary: A short list of Windows event IDs worth memorising, and what each one actually proves.
---

# Windows event IDs that actually matter

Windows logs far too much. Published "top 100 event IDs" lists are how new
analysts end up staring at Security logs with no idea what they are looking
for. In practice a small set carries most of the value, and each one answers a
specific question.

## Logons: 4624 and 4625

`4624` is a successful logon, `4625` a failed one. Neither is useful without
the **logon type**, which is the field that says *how* the session was
created:

- **Type 2 — Interactive.** Someone at the keyboard, or a console session.
- **Type 3 — Network.** File shares, and most lateral movement.
- **Type 10 — RemoteInteractive.** RDP.
- **Type 5 — Service.** A service starting under an account.
- **Type 4 — Batch.** Scheduled tasks.

Type 3 logons by an account that normally only does type 2 is one of the
cleanest lateral-movement signals Windows gives you for free.

Also read the **Logon ID** on 4624. It ties the session to everything that
happens inside it, including the matching `4634` logoff. That is how you turn
a pile of events into a session timeline.

## 4648: explicit credentials

*A logon was attempted using explicit credentials.* This fires when a process
authenticates as someone other than the logged-on user — `runas`, a scheduled
task with stored credentials, or a tool passing a stolen hash.

4648 is underrated. On a normal workstation it is rare, which makes it a
high-signal, low-volume event, which is exactly what you want in a detection.

## 4672: special privileges

*Special privileges assigned to new logon.* Administrator-equivalent rights
were granted to a session. Pair it with the 4624 that shares its Logon ID and
you have "this account logged on **and** it was privileged", which is a far
better alert than either alone.

## 4688: process creation

Process creation with the parent process name — off by default, and worth
turning on everywhere, along with the command-line auditing policy that makes
it useful.

Parentage is the point. `winword.exe` spawning `powershell.exe` is not a
PowerShell problem, it is a phishing problem, and you can only see that
because 4688 records who the parent was.

```
Process:        C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe
Parent process: C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE
Command line:   powershell -nop -w hidden -enc JABjAGwAaQBlAG4A...
```

Every part of that third line is a finding on its own: no profile, hidden
window, encoded command. Together with that parent, it is an incident.

## 7045 and 4697: service installed

A new service was installed. Attackers install services for persistence and
for running as SYSTEM. Legitimate service installation happens during software
deployment, which means it is predictable and therefore easy to baseline.

## 1102: the audit log was cleared

Someone cleared the Security log. There is almost no benign reason for this on
a server. Treat it as an incident until proven otherwise, and note that it
tells you the attacker had administrative rights and knew to cover their
tracks.

## What to do with this list

Do not memorise all of it at once. Learn 4624 with its logon types first,
because it underpins everything else, then 4688 with parent process, because
it is where behaviour becomes visible. The rest will attach themselves to
investigations you actually run.

> Events prove *what the system did*. They do not prove intent. 4672 on a
> domain admin account at 09:00 on a Tuesday is an administrator doing their
> job. The same event at 03:00 from a workstation that has never seen that
> account is the beginning of a bad week.

## Check yourself

- Why is 4624 nearly useless without the logon type?
- What does 4648 capture that 4624 does not?
- Why does 4688 need a policy change before it earns its place, and what does
  the parent process field let you conclude that the process name alone does not?

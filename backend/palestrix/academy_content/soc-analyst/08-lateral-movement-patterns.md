---
summary: How an intruder turns one host into many, and the handful of events that give it away.
---

# Lateral movement patterns

One compromised laptop is an incident. One compromised laptop that became the
domain is a catastrophe, and the distance between them is lateral movement.
This is the phase where an intruder is most visible, because moving between
hosts means authenticating, and authentication leaves records.

## The shape of it

Movement is always the same three beats, whatever the tooling:

- **Collect** a credential, a hash, a ticket or a token.
- **Choose** a target, usually from something enumerated on the current host.
- **Authenticate** to it, and get execution.

Detection lives in the third beat, because that is the one that has to touch
something that logs.

## What it looks like on Windows

**Remote service creation.** The classic: copy a binary to `ADMIN$`, create a
service pointing at it, start it. You see `7045` (service installed) on the
target, with a service name that is often random, and a binary path in
`C:\Windows\` rather than under `Program Files`.

**WMI and WinRM execution.** Process creation on the target whose parent is
`WmiPrvSE.exe` or `wsmprovhost.exe`. Neither normally parents a shell. A
`cmd.exe` or `powershell.exe` under either is worth a look every time.

**Scheduled tasks on a remote host.** A task registered from a different
machine than the one it runs on.

**Pass-the-hash and pass-the-ticket.** Harder, because the authentication
itself looks legitimate — that is the point. The tells are contextual: a
`4624` type 3 for an account that never uses network logons, an NTLM
authentication in an environment that is otherwise Kerberos, or a ticket with
a lifetime nothing in your estate issues.

## What it looks like on Linux

Quieter, and mostly SSH. The pattern to learn is **key reuse**: one key
accepted on host A, then the same key fingerprint accepted on B and C within
minutes. `sshd` logs the fingerprint on success, which makes this greppable:

```
grep 'Accepted publickey' /var/log/auth.log | awk '{print $NF}' | sort | uniq -c | sort -rn
```

A fingerprint appearing across hosts that share no administrator is the same
signal as a service creation burst on Windows: one credential, many targets.

## The three signals that matter most

If you learn nothing else from this module:

- **First-time pairs.** This account has never authenticated to this host
  before. Cheap to compute if you keep a baseline, and it catches movement
  regardless of technique.
- **Fan-out.** One source, many destinations, in a short window. Humans
  administering things do not usually touch fifteen hosts in four minutes;
  automation does, and so do attackers.
- **Direction.** Workstation to workstation is nearly always wrong. Normal
  traffic is workstation to server. A peer-to-peer SMB session between two
  user laptops has almost no legitimate explanation.

## Enumeration comes first, and it is loud

Before moving, an intruder has to find somewhere to go. That means
`net group "Domain Admins" /domain`, BloodHound-style LDAP sweeps, `nltest`,
or a burst of SMB connections to enumerate shares.

This is the cheapest thing to detect in the whole chain, because legitimate
users essentially never enumerate the directory. An LDAP query returning every
domain object, from a workstation, is not an administrator's afternoon.

> If you catch enumeration you get to act **before** the credential is used.
> That is the difference between containing one host and rebuilding a domain.

## Containment changes the game

The moment you act, the intruder learns you are there. Disabling one account
while a second one is still live tells them to switch and go quiet.

So the order matters: scope first, then contain everything at once. Which
means the investigative question is never "is this host compromised" but
**"which hosts and which accounts"**, and you keep asking it until the answer
stops growing.

## Check yourself

- Why is the authentication step the best place to detect movement, rather
  than the credential theft that precedes it?
- What makes a workstation-to-workstation SMB session more suspicious than
  workstation-to-server?
- Why is detecting enumeration more valuable than detecting the movement that
  follows it, and what does that imply about containment timing?

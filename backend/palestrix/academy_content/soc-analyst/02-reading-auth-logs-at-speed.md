---
summary: Authentication logs are where intrusions become visible. Learn to read them fast enough to matter.
lab: log-triage
pass: 80
---

# Reading auth logs at speed

Almost every intrusion touches authentication. Something logs in that should
not, or something that should logs in from somewhere new, at a strange hour,
or far too many times. Auth logs are the highest-yield place a new analyst can
learn to read quickly.

## The shape of a Linux auth line

On a Debian-family host, `/var/log/auth.log` carries `sshd`, `sudo`, `su` and
PAM. The fields never move, which is what makes speed possible:

```
Sep 20 02:14:07 web-01 sshd[20481]: Failed password for invalid user admin from 203.0.113.45 port 51224 ssh2
Sep 20 02:14:09 web-01 sshd[20483]: Failed password for root from 203.0.113.45 port 51230 ssh2
Sep 20 02:19:51 web-01 sshd[20512]: Accepted publickey for deploy from 203.0.113.45 port 51884 ssh2: RSA SHA256:9j2v...
Sep 20 02:20:02 web-01 sudo:   deploy : TTY=pts/0 ; PWD=/home/deploy ; USER=root ; COMMAND=/bin/bash
```

Read it right to left. The source address is the pivot; the username tells you
what they were guessing; the method (`password` versus `publickey`) tells you
what they had.

That four-line sequence is the story of a breach: two guesses, then a
**successful key-based login from the same address**, then an immediate
escalation to root. The failures are noise. Line three is the incident.

## `invalid user` is the cheapest signal you have

`Failed password for invalid user admin` means the account does not exist.
`Failed password for root` means it does. The distinction matters:

- A flood of `invalid user` across many names is untargeted scanning. Boring,
  constant, rarely worth a ticket.
- Failures against accounts that **actually exist** mean someone enumerated
  first. That is a step of attacker decision-making.

## Speed comes from asking for less

Do not read the file. Ask it questions.

```
# who is failing, and how often
grep 'Failed password' /var/log/auth.log | awk '{print $(NF-3)}' | sort | uniq -c | sort -rn | head

# did any of those addresses ever succeed
grep 'Accepted' /var/log/auth.log | awk '{print $(NF-3)}' | sort -u
```

Intersect the two lists. An address in both columns is the single most
important thing in the file, and you found it in two commands.

## The four questions

For any suspicious authentication, in this order:

- **Did it succeed?** Failures are weather; successes are events.
- **By what method?** A password success after failures suggests guessing. A
  key success with no failures suggests the key was stolen, which is worse and
  quieter.
- **What happened next?** Login without follow-on activity may be a legitimate
  user. Login followed within seconds by `sudo`, a package install, or a new
  authorized key is an intrusion.
- **Has this source been here before?** First-seen addresses deserve more
  suspicion than regulars.

## Things that look bad and usually are not

- **Thousands of failures from one address.** Internet background radiation.
  Note it, tune it, move on.
- **`sudo` by a service account at 03:00.** Check for a cron job before
  reaching for the incident channel.
- **Logins from a cloud provider range.** Your own CI probably lives there.

The discipline is the same in each case: find the boring explanation *first*,
and write it down so nobody re-investigates it next week.

## Things that look mild and are not

- A **new `authorized_keys` entry**. Persistence, installed quietly.
- A successful login for an account that has not been used in months.
- `sudo` succeeding for a user who has never used it before.

## Check yourself

- Why is a `publickey` success more alarming than a `password` success that
  followed twenty failures?
- What does intersecting failed-source addresses with successful-source
  addresses tell you, and why is it a first move rather than a last one?
- Name two log events that indicate persistence rather than access.

## Lab: work the incident

The four lines at the top of this lesson are the whole incident. Launch the
**Log Triage** lab and record your answers on the box — the automated checker
reads them back and grades this module. You need 80% to complete it.

Answer in lower case, one value per file, exactly as the command shows:

```
mkdir -p /root/answers

# 1. The address the intrusion came from
echo '198.51.100.7' > /root/answers/source-ip.txt

# 2. The account that successfully logged in
echo 'someuser' > /root/answers/account.txt

# 3. The authentication method that succeeded
echo 'password' > /root/answers/method.txt

# 4. The account it escalated to seconds later
echo 'nobody' > /root/answers/escalated-to.txt
```

The values above are **placeholders** — replace each with what the log
actually shows. Use `echo` as written so the file ends with a single newline;
the checker compares exact contents.

When you are done, hand in from the lab page. The grader reads the four files
over the guest agent and scores 25% each.

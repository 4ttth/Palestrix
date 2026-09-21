---
summary: A ruleset nobody can diff is a ruleset nobody can review. Put it in git and the whole discipline follows.
---

# Firewall policy as code

Firewall rules accumulate. Somebody opens a port for a migration, the
migration finishes, the rule stays. Five years later the ruleset is four
hundred lines, nobody knows which forty matter, and everyone is afraid to
delete anything.

The fix is not a better firewall. It is treating the policy as source code.

## What changes when it is a file

- **Review.** A change is a diff, and a diff can be read by someone who is not
  the person making it.
- **History.** `git log` answers "who opened 3389 to the internet, when, and
  why" — a question that is otherwise unanswerable.
- **Rebuild.** The device is reproducible. Hardware failure becomes an
  inconvenience instead of an archaeology project.
- **Testing.** The policy can be linted and simulated before it reaches
  production.
- **Deletion becomes safe.** Reverting is one command, so removing a rule
  stops being frightening, and rules actually get removed.

That last one is the real prize. The reason rulesets grow forever is that
deletion is scary. Version control makes it cheap.

## Structure the file like a policy, not a pile

```
#!/usr/sbin/nft -f
flush ruleset

table inet filter {
  set management_hosts { type ipv4_addr; elements = { 10.0.10.5, 10.0.10.6 } }

  chain inbound {
    type filter hook input priority 0; policy drop;

    ct state established,related accept
    ct state invalid drop
    iif lo accept

    # SSH from management only  -- ticket OPS-1184
    ip saddr @management_hosts tcp dport 22 accept

    # Web, public  -- service: storefront
    tcp dport { 80, 443 } accept

    limit rate 5/minute log prefix "nft-drop-in "
  }

  chain forward {
    type filter hook forward hook priority 0; policy drop;

    ct state established,related accept

    # workstations -> app tier
    ip saddr 10.24.1.0/24 ip daddr 10.24.9.0/24 tcp dport 443 accept

    limit rate 5/minute log prefix "nft-drop-fwd "
  }
}
```

Four habits visible there, and all four matter more than the syntax:

- **`policy drop`** at the top of the chain. Default deny, stated once.
- **Named sets** instead of repeated addresses. One place to edit.
- **A comment per rule naming the ticket or the service.** This is what makes
  a rule reviewable in two years. A rule with no reason attached can never be
  safely removed, so it never will be.
- **Logging the drops, rate-limited.** Unlimited drop logging is a
  self-inflicted denial of service on your own disk.

## Order is the bug you will actually hit

Both `nftables` and `iptables` evaluate in order and stop at the first match.
A broad accept above a specific deny silently disables the deny.

Read the ruleset top to bottom asking "what does this let through that the
rule below was meant to stop?" That single pass catches most misconfiguration,
and it is the review you should insist on for every change.

## Deploy it like code

- One repository, one file per device or role.
- Changes by merge request. The reviewer checks ordering, direction, and
  whether the comment names something real.
- A CI job that at minimum parses the file (`nft -c -f policy.nft`), and
  ideally runs a reachability test against a staging device.
- Apply from the repository. If someone edits the running device by hand, the
  next deploy erases it — which is the behaviour you want, as long as everyone
  knows it.

**Keep a rollback path.** Applying a bad rule to a remote firewall locks you
out of the firewall. The standard trick:

```
nft -f policy.nft && sleep 60 && nft -f last-known-good.nft
```

Cancel it if you can still type. If you cannot, the network heals itself in
sixty seconds.

## Review the whole thing periodically

Policy as code makes the annual review possible instead of theoretical. Go
rule by rule:

- Does the service in the comment still exist?
- Is the source still that narrow?
- Has the drop log fired for this rule's shape recently? A rule nothing
  matches is either dead or protecting against something that stopped.

> A rule with no comment and no matches is the strongest deletion candidate in
> any ruleset. Version control is what makes deleting it a five-second
> decision.

## Check yourself

- Why does version control make rulesets shrink rather than grow?
- What breaks when a broad `accept` sits above a specific `deny`, and how do
  you review for it?
- Why is unrestricted logging of dropped packets a bad idea, and what is the
  usual compromise?

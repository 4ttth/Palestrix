---
summary: One intrusion, start to finish, across every skill in this path. Work the evidence and hand in your findings.
lab: soc-capstone
pass: 80
---

# Capstone: 48-hour incident

Everything in this path converges here. Below is the evidence from a real
shape of intrusion: initial access, execution, beaconing, lateral movement,
persistence, and a detection that arrived far too late.

Your job is the analyst's job. Read the artifacts, build the timeline, and
answer five questions on the lab box.

## The evidence

**Proxy log.** `WS-0442` is a workstation in Finance.

```
2026-03-12T09:14:02Z WS-0442 10.12.4.42 GET
  https://cdn.delivery-net.io/dl/invoice_q1.xlsm  200  84213  "Mozilla/5.0"
2026-03-12T09:14:44Z WS-0442 10.12.4.42 GET
  https://cdn.delivery-net.io/favicon.ico  404  0  "Mozilla/5.0"
```

**EDR process telemetry, `WS-0442`.**

```
2026-03-12T09:16:31Z  parent=EXCEL.EXE  child=powershell.exe
  cmdline: powershell -nop -w hidden -enc SQBFAFgAIAAoAE4AZQB3AC0ATwBi...
2026-03-12T09:16:33Z  parent=powershell.exe  child=rundll32.exe
  cmdline: rundll32.exe C:\Users\r.santos\AppData\Roaming\mso\upd.dll,Start
```

**NetFlow, `WS-0442` outbound, summarised.**

```
dst 45.83.201.14:443   first 2026-03-12T09:18:07Z   last 2026-03-14T09:02:14Z
  connections 287   mean interval 600.4s   stddev 41.2s
  bytes out 214,880   bytes in 198,340
```

No DNS query preceded any of these connections.

**Domain authentication, filtered to `WS-0442` as source.**

```
2026-03-13T22:41:09Z  4624  type 3  account=svc_backup
  src=WS-0442  dst=FILE-03   auth=NTLM
2026-03-13T22:41:12Z  4672  special privileges assigned  account=svc_backup
  dst=FILE-03
```

`svc_backup` is a domain service account. It has never before authenticated
from a workstation; its normal source is `BKP-01`.

**Windows System log, `FILE-03`.**

```
2026-03-13T22:44:50Z  7045  Service installed
  name=WinDefendUpd
  image=C:\Windows\WinDefendUpd.exe
  start=auto  account=LocalSystem
```

**Detection.** The SOC's beacon rule fired on the `45.83.201.14` interval at
`2026-03-14T09:14:02Z`. That alert is how this incident began, from the
defender's side.

## Work it

Before you write anything down, answer these for yourself:

- Which artifact is the *earliest* evidence of compromise, and which is merely
  the earliest evidence you happen to have?
- The beacon ran for two days at a 600-second interval with 41 seconds of
  jitter. Why did that not defeat the detection?
- `svc_backup` authenticated over NTLM from a workstation it has never used.
  Which of those three facts is the anomaly, and which are merely context?
- The service on `FILE-03` is named `WinDefendUpd` and lives in
  `C:\Windows\`. What is wrong with both of those, specifically?
- Between first compromise and detection, how long did the intruder have?

## Hand in

Launch the **SOC Capstone** lab and record your answers. The checker reads the
files back over the guest agent and scores 20% each; you need 80% to complete
the module.

Answer in lower case, one value per file, exactly as the command shows:

```
mkdir -p /root/answers

# 1. The hostname of patient zero
echo 'ws-0000' > /root/answers/patient-zero.txt

# 2. The filename that delivered the initial access
echo 'something.xlsm' > /root/answers/initial-access.txt

# 3. The account used to move to the second host
echo 'svc_example' > /root/answers/service-account.txt

# 4. The name of the service installed for persistence
echo 'someservice' > /root/answers/persistence.txt

# 5. Hours between first compromise and detection, digits only
echo '0' > /root/answers/dwell-hours.txt
```

The values above are **placeholders** — replace each with what the evidence
shows. Use `echo` as written so each file ends with a single newline; the
checker compares exact contents.

For question 5, measure from the **first execution of attacker code** on
patient zero to the moment the alert fired, and round to whole hours.

## What this is really testing

Not whether you can find five strings. Whether you can order events across
five different log sources into one sequence, and then say which of them is
the incident and which is context. That is the job.

The dwell number is the one to sit with. Every artifact above existed in the
logs the whole time. The detection that eventually fired was looking at
traffic from the first hour.

## Check yourself

- Which single additional log source would have cut the dwell time most, and
  why?
- The intruder waited 37 hours between execution and lateral movement. What
  does that delay suggest about who they are?
- If you had only the `7045` event and nothing else, how would you work
  backwards to `WS-0442`?

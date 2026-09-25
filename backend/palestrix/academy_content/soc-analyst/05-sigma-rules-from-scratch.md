---
summary: Write a detection once in a portable format, and stop hand-porting logic between SIEM query languages.
lab: sigma-authoring
---

# Sigma rules from scratch

Every SIEM has its own query language, and every one of them expresses "this
process spawned that process" differently. Sigma is a YAML format for writing
the *logic* once and converting it into whichever dialect your platform
speaks. Its real value is not portability, though — it is that writing one
forces you to say precisely what you mean.

## The shape of a rule

```
title: PowerShell spawned by an Office application
id: 7f2a1c4e-0f5b-4a9e-9a1a-2b6d9e3f0c11
status: experimental
description: Office applications do not normally launch shells. This is the
  classic macro-to-payload transition.
logsource:
  product: windows
  category: process_creation
detection:
  selection:
    ParentImage|endswith:
      - '\WINWORD.EXE'
      - '\EXCEL.EXE'
      - '\POWERPNT.EXE'
    Image|endswith:
      - '\powershell.exe'
      - '\pwsh.exe'
  condition: selection
falsepositives:
  - Office add-ins that shell out during install
level: high
```

Three parts carry the meaning: **logsource** says what data this applies to,
**detection** holds one or more named selections, and **condition** combines
them. Everything else is metadata for humans.

## Conditions are where the thinking lives

A selection is a set of field matches ANDed together. The condition combines
selections, and that is where you encode intent:

```
detection:
  selection:
    Image|endswith: '\powershell.exe'
  encoded:
    CommandLine|contains:
      - ' -enc '
      - ' -EncodedCommand '
  known_good:
    ParentImage|endswith: '\SCCM\ccmexec.exe'
  condition: selection and encoded and not known_good
```

`and not known_good` is the difference between a rule that ships and a rule
that gets muted in a week. Write the exclusion into the rule where a reviewer
can see it, rather than leaving it to whoever tunes the SIEM later.

## Modifiers do the work

- `|contains` — substring. Cheap and blunt; the first reach, and often too broad.
- `|endswith` — the right default for image paths, because the directory
  varies and the binary name does not.
- `|startswith` — useful for command-line prefixes.
- `|re` — regular expression. Correct when nothing else fits, expensive at
  scale, and a common cause of a rule nobody will run.
- `|base64offset|contains` — matches a string that was base64-encoded at any
  of the three alignments. This is how you catch an encoded command without
  decoding every command line.

## Writing one that survives contact

Start from an observation, not from a technique name. "Someone ran an encoded
PowerShell command from Word" is a rule. "T1059.001" is a category.

Then, before you ship it, ask the two questions that decide whether it is
worth having:

- **What legitimate thing looks exactly like this?** If you cannot name one,
  you have not looked hard enough. Write it in `falsepositives`.
- **What does an analyst do when it fires?** If the answer is "look at it and
  close it", the rule is telemetry, not a detection. Either sharpen it or set
  `level: low` and stop paging people.

## Levels mean something

`level` drives whether a human is interrupted. Treat it as a promise:

- `critical` — wake someone up.
- `high` — a person looks today.
- `medium` — a person looks this week.
- `low` / `informational` — context for other investigations, not an alert.

A rule set where everything is `high` is a rule set nobody reads.

## Converting

`sigma convert` (the `sigma-cli` tool) renders a rule into a backend's query
language. The conversion is mechanical; what does not convert is the part you
should be suspicious of. A rule that will not express cleanly in your SIEM is
usually a rule relying on a field your pipeline does not actually collect,
which is worth finding out before an incident rather than during one.

## Check yourself

- What does `condition` let you express that a single selection cannot?
- Why is `|endswith` usually the right modifier for a process image path?
- A rule fires forty times a day and is closed as benign every time. Name two
  different correct responses, and say what decides between them.

## Lab: turn one detection into a portable rule

The **Sigma From Scratch** lab gives you a single confirmed detection — a
process-creation event from a real intrusion — and asks you to make the four
decisions that turn it into a portable Sigma rule. You record the decisions on
the box and the checker reads them back; 80% completes the module.

The evidence is one file, `/root/case/event.txt`, a Windows process-creation
record:

- It is a **windows** log, so the `logsource` product is windows.
- The record is a Security **4688** ("a new process has been created") — the
  event id your `logsource`/`detection` keys on.
- The malicious thing about it is *what launched it*: `winword.exe` spawning
  `cmd.exe`. The field that expresses "who is the parent" is **parentimage**,
  and that is the field your `detection` selects on.
- Word spawning a shell is a reliable intrusion signal, not a maybe, so the
  rule's `level` is **high**.

Answer in lower case, one value per file:

```
mkdir -p /home/student/answers

echo 'windows'     > /home/student/answers/logsource-product.txt
echo '4688'        > /home/student/answers/event-id.txt
echo 'parentimage' > /home/student/answers/detection-field.txt
echo 'high'        > /home/student/answers/rule-level.txt
```

Use `echo` as written; the grader compares exact contents, 25% each.

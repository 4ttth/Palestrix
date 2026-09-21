---
summary: One disk image, one memory capture, one case. Build the timeline, find what was taken, and report what you cannot prove.
lab: forensics-capstone
pass: 80
---

# Capstone: a full case from image to report

`WS-0442` has been imaged. Below are the artefact extracts an examiner would
produce in the first few hours. Your job is to assemble them into a single
account, identify what left the building, and be precise about the boundary
between what the evidence shows and what it merely suggests.

Every module in this path appears somewhere in the exhibits.

## Acquisition record

```
Item:      EV-2026-0031  Dell Latitude 5420, S/N 7JX2M93
Acquired:  2026-03-14 08:12 UTC by R. Almazan, hardware write blocker
Image:     case31.E01   sha256 4f1c...9ab2   verified against source
Memory:    case31-mem.raw  captured 2026-03-14 07:58 UTC, machine running
System TZ: Asia/Manila (UTC+8).  All times below normalised to UTC.
```

## Exhibit A — browser history and downloads

```
visited              url                                            transition
2026-03-12 09:13:41  https://mail.example.edu/inbox                 link
2026-03-12 09:14:02  https://cdn.delivery-net.io/dl/invoice_q1.xlsm typed

downloads
  target      C:\Users\r.santos\Downloads\invoice_q1.xlsm
  referrer    https://cdn.delivery-net.io/dl/
  bytes       84213
  started     2026-03-12 09:14:02   finished  2026-03-12 09:14:04
```

The downloaded file carries a `Zone.Identifier` stream naming the same host.

## Exhibit B — prefetch

```
EXCEL.EXE-4A21C8F1.pf        run count 14   last run 2026-03-12 09:16:31
RUNDLL32.EXE-77B1E902.pf     run count  3   last run 2026-03-13 22:38:04
SDELETE.EXE-0C93A5DD.pf      run count  1   last run 2026-03-13 23:02:17
```

`sdelete.exe` is not part of the corporate build and no installer for it
appears in the image.

## Exhibit C — filesystem, `$MFT` and `$UsnJrnl`

```
path                                                    SI_created           FN_created
C:\Users\r.santos\AppData\Roaming\mso\upd.dll           2019-07-14 01:12:00  2026-03-12 09:16:33
C:\Users\r.santos\Downloads\invoice_q1.xlsm             2026-03-12 09:14:04  2026-03-12 09:14:04

$UsnJrnl (extract)
2026-03-12 09:16:33  FILE_CREATE   upd.dll
2026-03-13 22:51:08  FILE_CREATE   payroll_export.csv
2026-03-13 23:02:19  FILE_DELETE   payroll_export.csv
```

Note the `upd.dll` row carefully. Its `SI` creation time is 2019; the machine
was imaged from a build deployed in 2024.

## Exhibit D — registry

```
NTUSER.DAT\Software\Microsoft\Windows\CurrentVersion\Run
  last written  2026-03-12 09:16:34
  values:
    OneDriveSetup  "C:\Program Files\Microsoft OneDrive\OneDrive.exe" /background
    MsoUpdate      rundll32.exe C:\Users\r.santos\AppData\Roaming\mso\upd.dll,Start

SYSTEM\CurrentControlSet\Enum\USBSTOR
  Disk&Ven_SanDisk&Prod_Ultra&Rev_1.00\AA76B2C10F39
    first connected  2026-03-13 22:47:55
    last  connected  2026-03-13 23:05:40
```

## Exhibit E — memory

```
windows.pstree
  explorer.exe(3120)
    rundll32.exe(6644)   cmdline: rundll32.exe ...\mso\upd.dll,Start

windows.netscan
  6644  rundll32.exe  10.24.1.42:51203 -> 45.83.201.14:443  ESTABLISHED

windows.malfind
  PID 6644  private, executable, not file-backed, MZ header at 0x1f0000
```

## Work it

- Exhibit C shows a 2019 creation date on a file the journal says was created
  in 2026. Which timestamp do you believe, and what does the disagreement
  itself establish?
- `payroll_export.csv` was created at 22:51 and deleted at 23:02. A USB device
  was connected from 22:47 to 23:05, and `sdelete.exe` ran at 23:02:17. State
  what that sequence shows — and then state precisely what it does **not**
  show.
- Exhibit A records the download as `typed`, not `link`. What does that change
  about the account of how this started?
- The `Run` key was last written at 09:16:34 and holds two values. What can
  you legitimately say about when `MsoUpdate` was created?
- What single additional source would most improve this case, and what
  question would it answer?

## Hand in

Launch the **Forensics Capstone** lab and record your answers. The checker
reads the files back over the guest agent and scores 20% each; you need 80% to
complete the module.

Answer in lower case, one value per file, exactly as the command shows:

```
mkdir -p /root/answers

# 1. The filename that was downloaded and opened
echo 'something.xlsx' > /root/answers/entry-file.txt

# 2. The filename of the dropped library
echo 'thing.dll' > /root/answers/dropped-dll.txt

# 3. The Run value name used for persistence
echo 'somename' > /root/answers/persistence-value.txt

# 4. The serial number of the USB device
echo '000000000000' > /root/answers/usb-serial.txt

# 5. The filename of the tool used to destroy evidence
echo 'tool.exe' > /root/answers/wipe-tool.txt
```

The values above are **placeholders** — replace each with what the exhibits
show. Use `echo` as written so each file ends with a single newline; the
checker compares exact contents.

Give filenames only, never full paths, and the USB serial exactly as it
appears in the registry key, lower case.

## The part that is actually being graded

Not the five strings. This:

> `payroll_export.csv` was created while a USB device was attached and deleted
> by a wiping tool eighteen minutes later. **We cannot prove the file was
> copied to the USB device.** No `LNK` file, shellbag or journal entry places
> it on the removable volume, and the device is not in evidence.

That is the honest finding, and it is the one a competent opponent would test.
An examiner who writes "the file was exfiltrated via USB" has stated an
inference as a fact — and if the device is later produced and does not contain
the file, everything else in the report becomes suspect too.

Write the inference. Label it as one. Say what would confirm it: seizing the
device, or finding the `LNK` and shellbag entries that would place the file on
`E:\`.

## Check yourself

- Which exhibit proves execution, and which merely proves presence?
- Why does the `$FILE_NAME` timestamp beat `$STANDARD_INFORMATION` here, and
  what would you write in the report about it?
- State the USB finding as a fact, an inference, and an unknown — three
  sentences, clearly separated.

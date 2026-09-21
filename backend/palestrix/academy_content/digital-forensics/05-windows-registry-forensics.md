---
summary: A timestamped database recording what ran, what was plugged in, and what the user did. Learn six keys and you can reconstruct a session.
---

# Windows registry forensics

The registry is not configuration. It is a hierarchical database that Windows
updates constantly as a side effect of normal use, and almost every key
carries a last-written timestamp. That makes it one of the richest
behavioural records on the system.

## The hives and where they live

```
C:\Windows\System32\config\SYSTEM       devices, services, mounted volumes
C:\Windows\System32\config\SOFTWARE     installed software, OS configuration
C:\Windows\System32\config\SAM          local accounts
C:\Windows\System32\config\SECURITY     policy, cached secrets
C:\Users\<user>\NTUSER.DAT              per-user: HKCU
C:\Users\<user>\AppData\Local\Microsoft\Windows\UsrClass.dat   shellbags
```

Always take the **transaction logs** alongside each hive — `.LOG1` and
`.LOG2`. A hive copied from a live or improperly shut down system is missing
its most recent writes until those are replayed, and the most recent writes
are usually the ones you care about.

## The keys that answer real questions

**What did the user run?**

```
NTUSER.DAT\Software\Microsoft\Windows\CurrentVersion\Explorer\UserAssist
```

GUI-launched programs, with run counts and last execution time. The value
names are ROT13-encoded, which is a quirk rather than a protection.

**What executed at all, ever?**

```
SYSTEM\CurrentControlSet\Control\Session Manager\AppCompatCache   (ShimCache)
SOFTWARE\Microsoft\Amcache.hve  ->  actually a separate hive file
```

ShimCache records path, size and file-modification time for binaries the
system encountered — including ones that were *never executed*, which is a
subtlety to state carefully in a report. AmCache adds SHA-1 hashes, which lets
you identify a binary that has since been deleted.

**What persists?**

```
...\CurrentVersion\Run  and  RunOnce      (both HKLM and HKCU)
SYSTEM\CurrentControlSet\Services         service definitions
...\Winlogon\Shell  and  Userinit         classic hijack points
...\Image File Execution Options\<exe>    debugger hijack
```

**What was plugged in?**

```
SYSTEM\CurrentControlSet\Enum\USBSTOR
SOFTWARE\Microsoft\Windows Portable Devices\Devices
SYSTEM\MountedDevices
```

Vendor, product, serial number, and first and last connection times. This is
the artefact that answers "was a USB device used to take the data", and it
survives the device being long gone.

**Where did the user browse?**

```
UsrClass.dat\Local Settings\Software\Microsoft\Windows\Shell\BagMRU  (shellbags)
NTUSER.DAT\...\Explorer\RecentDocs
NTUSER.DAT\...\Explorer\TypedPaths
NTUSER.DAT\...\Explorer\RunMRU
```

Shellbags are the standout: they record folders that were *opened in Explorer*,
including network shares, removable drives and encrypted containers that are
no longer attached. A shellbag for `E:\exfil` proves a folder existed and was
browsed, even with no `E:` drive in evidence.

**What networks did it join?**

```
SOFTWARE\Microsoft\Windows NT\CurrentVersion\NetworkList\Profiles
```

SSIDs, gateway MACs, and first and last connection times — a location history
by another name.

## Working with the hives

```
# parse everything with known plugins
RegRipper/rip.pl -r NTUSER.DAT -f ntuser > ntuser.txt

# targeted, scriptable
reglookup -p '/Software/Microsoft/Windows/CurrentVersion/Run' SOFTWARE
```

Offline, on your working copy, with the transaction logs present. Never mount
and browse the subject's registry on a live system.

## The timestamp caveat everyone gets wrong

A registry **key** has a last-written time. A **value** does not.

So a `Run` key whose last-written time is 02:44 tells you *the key* changed
then — not which of its five values changed, and not when the other four were
created. If a key holds several values, the timestamp bounds only the most
recent modification.

State this precisely in reports. "The persistence value was created at 02:44"
is a claim the artefact does not support; "the Run key was last written at
02:44, at which point this value was present" is.

## Check yourself

- Why must you collect `.LOG1` and `.LOG2` along with a hive?
- What does a ShimCache entry prove, and what does it specifically *not*
  prove?
- A `Run` key with four values has a last-written time of 02:44. What can you
  say, and what would be overclaiming?

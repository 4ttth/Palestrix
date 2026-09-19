"""Sample delivery.

The detonation VM is air-gapped and has no guest agent, so the sample is
handed over the only channel that survives an air gap: a freshly built
ISO attached as a CD-ROM. The template runs D:\run.bat at logon (see README).

Two submission kinds share the channel. A file is copied out of the ISO and
started. A PowerShell command is written to the ISO *as a file* and handed to
powershell.exe with -File.

That distinction is the security boundary, not a style choice. The submitted
command is attacker-controlled text, and it is never interpolated into run.bat
-- if it were, a submission containing a quote and an ampersand would execute
on the coordinator host at ISO-build time, turning an analysis request into
remote code execution against the hypervisor. The command travels as inert
bytes and is only ever interpreted inside the throwaway guest.
"""

from __future__ import annotations

import os
import shutil
import subprocess


SAFE = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"

PS_PAYLOAD_NAME = "payload.ps1"


def safe_name(filename: str) -> str:
    base = os.path.basename(filename or "sample.bin")
    cleaned = "".join(c if c in SAFE else "_" for c in base)
    return cleaned[:96] or "sample.bin"


RUN_BAT = r"""@echo off
rem PalestrIX sandbox runner. Executed by the template's logon task.
set SRC=%~dp0sample\{name}
set DST=%TEMP%\{name}
copy /y "%SRC%" "%DST%" >nul 2>&1
cd /d "%TEMP%"
start "" "%DST%"
"""

# The command itself is not here -- only the fixed name of the file carrying
# it. Nothing attacker-controlled is ever expanded by this batch file.
RUN_BAT_PS = r"""@echo off
rem PalestrIX sandbox runner (PowerShell command submission).
set SRC=%~dp0sample\{name}
set DST=%TEMP%\{name}
copy /y "%SRC%" "%DST%" >nul 2>&1
cd /d "%TEMP%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%DST%"
""".replace("{name}", PS_PAYLOAD_NAME)


def build_payload_iso(
    sample_bytes: bytes,
    filename: str,
    workdir: str,
    iso_dir: str,
    run_id: str,
    kind: str = "file",
) -> tuple[str, str]:
    """Write <run_id>.iso into the Proxmox ISO store. Returns (iso_name, path).

    ``kind`` is "file" or "powershell"; for the latter ``sample_bytes`` is the
    command text and ``filename`` is ignored.
    """
    stage = os.path.join(workdir, "iso")
    os.makedirs(os.path.join(stage, "sample"), exist_ok=True)

    if kind == "powershell":
        name = PS_PAYLOAD_NAME
        runner = RUN_BAT_PS
        # BOM + CRLF so powershell.exe reads the encoding unambiguously; an
        # obfuscated one-liner often carries non-ASCII that a bare read would
        # mangle into a different script than the analyst submitted.
        text = sample_bytes.decode("utf-8", "replace").replace("\r\n", "\n")
        blob = b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8")
    else:
        name = safe_name(filename)
        runner = RUN_BAT.format(name=name)
        blob = sample_bytes

    with open(os.path.join(stage, "sample", name), "wb") as fh:
        fh.write(blob)
    with open(os.path.join(stage, "run.bat"), "w", newline="\r\n") as fh:
        fh.write(runner)

    iso_name = f"sbx-{run_id}.iso"
    iso_path = os.path.join(iso_dir, iso_name)
    proc = subprocess.run(
        ["genisoimage", "-quiet", "-J", "-r", "-V", "SBXPAYLOAD", "-o", iso_path, stage],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"genisoimage failed: {proc.stderr.strip()}")
    shutil.rmtree(stage, ignore_errors=True)
    return iso_name, iso_path

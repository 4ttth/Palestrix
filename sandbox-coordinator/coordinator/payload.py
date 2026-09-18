"""Sample delivery.

The detonation VM is air-gapped and has no guest agent, so the sample is
handed over the only channel that survives an air gap: a freshly built
ISO attached as a CD-ROM. The template runs D:\run.bat at logon (see README).
"""

from __future__ import annotations

import os
import shutil
import subprocess


SAFE = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"


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


def build_payload_iso(
    sample_bytes: bytes, filename: str, workdir: str, iso_dir: str, run_id: str
) -> tuple[str, str]:
    """Write <run_id>.iso into the Proxmox ISO store. Returns (iso_name, path)."""
    name = safe_name(filename)
    stage = os.path.join(workdir, "iso")
    os.makedirs(os.path.join(stage, "sample"), exist_ok=True)

    with open(os.path.join(stage, "sample", name), "wb") as fh:
        fh.write(sample_bytes)
    with open(os.path.join(stage, "run.bat"), "w", newline="\r\n") as fh:
        fh.write(RUN_BAT.format(name=name))

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

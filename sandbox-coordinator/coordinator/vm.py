"""Proxmox VM lifecycle for one detonation.

Every run gets a throwaway clone of the Windows template. The clone is
destroyed in a finally block: a leaked clone is a live malware host, so the
teardown path must not depend on the happy path.
"""

from __future__ import annotations

import subprocess
import time

from .config import get_settings


class VmError(RuntimeError):
    pass


def _qm(*args: str, timeout: int = 300) -> str:
    proc = subprocess.run(
        ["qm", *args], capture_output=True, text=True, timeout=timeout
    )
    if proc.returncode != 0:
        raise VmError(f"qm {' '.join(args)} -> {proc.returncode}: {proc.stderr.strip()}")
    return proc.stdout


def existing_vmids() -> set[int]:
    out = subprocess.run(
        ["qm", "list"], capture_output=True, text=True, timeout=60
    ).stdout
    ids: set[int] = set()
    for line in out.splitlines()[1:]:
        parts = line.split()
        if parts and parts[0].isdigit():
            ids.add(int(parts[0]))
    return ids


def allocate_vmid() -> int:
    s = get_settings()
    taken = existing_vmids()
    for vmid in range(s.clone_vmid_min, s.clone_vmid_max + 1):
        if vmid not in taken:
            return vmid
    raise VmError("no free vmid in the sandbox clone range")


def clone_template(vmid: int, name: str) -> None:
    s = get_settings()
    _qm("clone", str(s.template_vmid), str(vmid), "--name", name)


def attach_payload(vmid: int, iso_name: str) -> None:
    s = get_settings()
    _qm("set", str(vmid), "--ide0", f"{s.iso_storage}:iso/{iso_name},media=cdrom")


def pin_to_sandbox_bridge(vmid: int) -> None:
    """Re-assert the air-gapped bridge on the clone.

    The template should already carry it, but a clone that silently landed on
    a routed bridge would put live malware on the LAN, so this is checked
    rather than assumed.
    """
    s = get_settings()
    _qm("set", str(vmid), "--net0", f"e1000,bridge={s.bridge}")


def start(vmid: int) -> None:
    _qm("start", str(vmid))


def stop(vmid: int) -> None:
    """Hard stop -- a sample must never get a clean shutdown hook."""
    try:
        _qm("stop", str(vmid), timeout=120)
    except VmError:
        pass


def destroy(vmid: int) -> None:
    for attempt in range(3):
        try:
            _qm("destroy", str(vmid), "--purge", "--destroy-unreferenced-disks", "1")
            return
        except VmError:
            time.sleep(2 + attempt * 3)
    raise VmError(f"could not destroy sandbox clone {vmid}")


def tap_interface(vmid: int) -> str:
    """The host-side tap for net0 of this VM."""
    return f"tap{vmid}i0"


def screenshot(vmid: int, out_path: str) -> bool:
    """Grab the console via the QEMU monitor. Best effort: a missing
    screenshot must never fail a run."""
    try:
        subprocess.run(
            ["qm", "monitor", str(vmid)],
            input=f"screendump {out_path}\nquit\n",
            capture_output=True,
            text=True,
            timeout=60,
        )
        return True
    except Exception:
        return False

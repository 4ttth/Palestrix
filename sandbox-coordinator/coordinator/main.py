"""The detonation service.

One request == one throwaway Windows VM. The contract is defined by
``CoordinatorDetonator`` in the core API: multipart POST /detonate, answered
with the verdict/score/mitre/iocs/events/artifacts the sandbox UI renders.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import shutil
import subprocess
import time

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile, status

from . import archive, psanalyse, vm
from .capture import Capture
from .config import get_settings
from .payload import build_payload_iso
from .pcapparse import parse as parse_pcap
from .staticcheck import analyse, static_events
from .verdict import assess

app = FastAPI(title="PalestrIX sandbox coordinator", docs_url=None, redoc_url=None)


def _authorise(authorization: str | None) -> None:
    settings = get_settings()
    if not settings.auth_token:
        # Refuse rather than run open: an unauthenticated detonation endpoint
        # is a remote code execution service.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "coordinator has no auth token set"
        )
    presented = ""
    if authorization and authorization.lower().startswith("bearer "):
        presented = authorization.split(" ", 1)[1].strip()
    if not hmac.compare_digest(presented, settings.auth_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad coordinator token")


def detonation_sleep(settings, elapsed: float) -> float:
    """Seconds to hold the VM open, given ``elapsed`` already spent this run.

    boot_grace + detonation is what an analyst asked for; wall_clock is what
    the deployment allows. The smaller wins, and time already burnt on the ISO
    build and the clone counts against the ceiling -- otherwise a slow clone
    would quietly extend the window the security doc promises to cap.
    """
    window = float(settings.boot_grace_seconds + settings.detonation_seconds)
    return max(0.0, min(window, settings.wall_clock_seconds - elapsed))


@app.get("/healthz")
def healthz():
    s = get_settings()
    return {
        "ok": True,
        "template_vmid": s.template_vmid,
        "bridge": s.bridge,
        "detonation_seconds": s.detonation_seconds,
        "wall_clock_seconds": s.wall_clock_seconds,
    }


@app.post("/detonate")
def detonate(
    sample: UploadFile = File(...),
    sha256: str = Form(""),
    filename: str = Form(""),
    kind: str = Form("file"),
    authorization: str | None = Header(default=None),
):
    _authorise(authorization)
    settings = get_settings()

    data = sample.file.read()
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "empty sample")
    if len(data) > settings.max_sample_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "sample too large")

    digest = hashlib.sha256(data).hexdigest()
    if sha256 and not hmac.compare_digest(sha256.lower(), digest):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "sha256 mismatch")

    name = filename or sample.filename or "sample.bin"
    run_id = secrets.token_hex(8)
    workdir = os.path.join(settings.work_dir, run_id)
    os.makedirs(workdir, exist_ok=True)

    events: list[dict] = []

    def sys_event(level: str, msg: str, **data_):
        events.append(
            {"category": "system", "level": level, "msg": msg, "data": data_}
        )

    # What actually gets written to the ISO. An archive is an envelope, so
    # the thing worth detonating -- and worth scoring -- is what is inside it.
    payload_bytes, payload_name = data, name
    ps = None
    extra_score, extra_mitre, extra_reasons = 0, (), ()

    if kind == "powershell":
        command = data.decode("utf-8", "replace")
        ps = psanalyse.analyse(command)
        static = psanalyse.to_static(command, ps)
        static_iocs = ps.iocs
        events.extend(psanalyse.events(ps))
        extra_score = ps.score
        extra_mitre = tuple(ps.mitre)
        extra_reasons = tuple(ps.techniques[:6])
    else:
        unwrapped = archive.extract(data)
        chosen = None
        if unwrapped is not None:
            chosen = archive.pick_payload(unwrapped.entries)
            events.extend(archive.events(unwrapped, chosen))
            if chosen is not None:
                payload_bytes, payload_name = chosen.data, chosen.name

        static, static_iocs = analyse(payload_name, payload_bytes)
        if unwrapped is not None:
            # Keep the envelope visible: the analyst submitted the archive and
            # the report has to say what was opened and what was picked.
            static["archive"] = {
                "kind": unwrapped.kind,
                "container": name,
                "entries": [e.name for e in unwrapped.entries[:50]],
                "encrypted": unwrapped.encrypted,
                "password": unwrapped.password,
                "truncated": unwrapped.truncated,
                "error": unwrapped.error,
                "detonated": chosen.name if chosen else None,
            }
        events.extend(static_events(static))

    vmid: int | None = None
    iso_name: str | None = None
    iso_path: str | None = None
    pcap_path = os.path.join(workdir, "capture.pcap")
    shot_path = os.path.join(workdir, "console.ppm")
    capture: Capture | None = None
    ran = False

    # The wall clock starts here, not at vm.start: a slow clone is still time
    # the run is burning, and the ceiling is a promise about the whole run.
    t0 = time.time()

    try:
        iso_name, iso_path = build_payload_iso(
            payload_bytes, payload_name, workdir,
            settings.iso_storage_path, run_id, kind=kind,
        )
        sys_event("info", "payload ISO built", iso=iso_name)

        vmid = vm.allocate_vmid()
        vm.clone_template(vmid, f"sbx-{run_id}")
        vm.pin_to_sandbox_bridge(vmid)
        vm.attach_payload(vmid, iso_name)
        sys_event(
            "info",
            f"cloned template {settings.template_vmid} to throwaway VM {vmid}",
            vmid=vmid,
            bridge=settings.bridge,
        )

        if settings.capture_enabled:
            capture = Capture(vm.tap_interface(vmid), pcap_path)

        vm.start(vmid)
        ran = True
        started = time.time()
        # The tap only exists once the VM is running.
        if capture is not None:
            for _ in range(20):
                if capture.start():
                    sys_event("ok", "network capture started", iface=capture.iface)
                    break
                time.sleep(0.5)
            else:
                sys_event("warn", "network capture could not be started")

        window = settings.boot_grace_seconds + settings.detonation_seconds
        sleep_for = detonation_sleep(settings, time.time() - t0)
        if sleep_for < window:
            sys_event(
                "warn",
                f"detonation window cut to {int(sleep_for)}s by the "
                f"{settings.wall_clock_seconds}s wall clock",
                window=window,
                wall_clock=settings.wall_clock_seconds,
            )
        else:
            sys_event(
                "info",
                f"detonating for {settings.detonation_seconds}s "
                f"(after {settings.boot_grace_seconds}s boot grace)",
            )
        time.sleep(sleep_for)

        if settings.screenshot_enabled:
            vm.screenshot(vmid, shot_path)

        vm.stop(vmid)
        sys_event(
            "ok",
            f"detonation window closed after {int(time.time() - started)}s",
        )
    except Exception as exc:  # noqa: BLE001 - surfaced to the analyst
        sys_event("alert", f"detonation aborted: {exc}")
    finally:
        if capture is not None:
            capture.stop()
        if vmid is not None:
            try:
                vm.destroy(vmid)
                sys_event("ok", f"throwaway VM {vmid} destroyed")
            except Exception as exc:  # noqa: BLE001
                sys_event("alert", f"VM {vmid} could NOT be destroyed: {exc}")
        if iso_path and os.path.exists(iso_path):
            os.remove(iso_path)

    net, net_events = parse_pcap(pcap_path) if os.path.exists(pcap_path) else (None, [])
    if net is None:
        from .pcapparse import NetFacts

        net = NetFacts()
    events.extend(net_events)

    scored = assess(
        static, net, ran,
        extra_score=extra_score,
        extra_mitre=extra_mitre,
        extra_reasons=extra_reasons,
    )

    iocs = {
        "urls": sorted(set(static_iocs["urls"]) | set(net.urls))[:200],
        "ips": sorted(set(static_iocs["ips"]) | set(net.ips))[:200],
        "domains": sorted(set(static_iocs["domains"]) | set(net.domains))[:200],
    }

    artifacts = []
    if os.path.exists(pcap_path) and os.path.getsize(pcap_path) > 0:
        with open(pcap_path, "rb") as fh:
            artifacts.append(
                {
                    "name": "capture.pcap",
                    "kind": "pcap",
                    "media_type": "application/vnd.tcpdump.pcap",
                    "b64": base64.b64encode(fh.read()).decode(),
                }
            )
    png = _to_png(shot_path)
    if png:
        artifacts.append(
            {
                "name": "console.png",
                "kind": "screenshot",
                "media_type": "image/png",
                "b64": base64.b64encode(png).decode(),
            }
        )

    shutil.rmtree(workdir, ignore_errors=True)

    return {
        "static": static,
        "verdict": scored["verdict"],
        "score": scored["score"],
        "family": scored["family"],
        "mitre": scored["mitre"],
        "iocs": iocs,
        "summary": scored["summary"],
        "events": events,
        "artifacts": artifacts,
    }


def _to_png(ppm_path: str) -> bytes | None:
    """Console grabs come out as PPM; convert if a converter exists."""
    if not os.path.exists(ppm_path):
        return None
    png_path = ppm_path.replace(".ppm", ".png")
    for cmd in (["convert", ppm_path, png_path], ["pnmtopng", ppm_path]):
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=60)
            if proc.returncode == 0:
                if cmd[0] == "pnmtopng":
                    return proc.stdout or None
                with open(png_path, "rb") as fh:
                    return fh.read()
        except FileNotFoundError:
            continue
        except Exception:
            return None
    return None

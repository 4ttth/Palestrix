"""Static analysis and behavior synthesis for the sandbox module.

Two very different jobs live here, kept apart on purpose:

- ``static_precheck`` and its helpers perform *real* analysis on the bytes a
  student submits — magic-byte typing, Shannon entropy, string and IOC
  extraction, EICAR detection. None of this executes the sample; it is the
  "deep static analysis pre-check" from docs/sandbox-security.md and is safe
  to run anywhere, including the API process.

- ``synthesize_behavior`` produces the *demo* detonator's dynamic trace. Real
  detonation happens only on the isolated host (palestrix/sandbox/coordinator.py);
  when that host is not configured the demo detonator narrates a deterministic,
  clearly-labelled synthetic run so the UI panels (process tree, file diff,
  network flows) have shape without anything actually running. Every synthetic
  line says so.

Determinism: the synthetic trace is seeded from the sample SHA-256, so the
same bytes always yield the same report — the tests and the dedup story both
rely on that.
"""

from __future__ import annotations

import hashlib
import math
import random
import re
from dataclasses import dataclass, field

# The EICAR anti-malware test file: a harmless, industry-standard string that
# every scanner flags as a positive. Perfect for exercising the pipeline
# without a real sample (docs/sandbox-security.md). Split so this source file
# is not itself flagged by scanners.
EICAR = (
    "X5O!P%@AP[4\\PZX54(P^)7CC)7}$"
    + "EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
)


@dataclass
class Static:
    """Result of the static pre-check. Serialized straight onto the run's
    ``static`` JSON column and returned in the report."""

    file_type: str
    media_type: str
    size: int
    entropy: float
    packed: bool
    is_eicar: bool
    strings_sample: list[str] = field(default_factory=list)
    iocs: dict = field(default_factory=lambda: {"urls": [], "ips": [], "domains": []})
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "file_type": self.file_type,
            "media_type": self.media_type,
            "size": self.size,
            "entropy": round(self.entropy, 3),
            "packed": self.packed,
            "is_eicar": self.is_eicar,
            "strings_sample": self.strings_sample,
            "notes": self.notes,
        }


# -- real static analysis ------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def shannon_entropy(data: bytes) -> float:
    """Bits per byte, 0..8. High entropy across the whole file suggests
    compression or packing — a classic evasion tell."""
    if not data:
        return 0.0
    counts = [0] * 256
    for byte in data:
        counts[byte] += 1
    n = len(data)
    entropy = 0.0
    for c in counts:
        if c:
            p = c / n
            entropy -= p * math.log2(p)
    return entropy


def sniff_magic(data: bytes) -> tuple[str, str]:
    """Return (human file type, media type) from leading magic bytes. A small
    table on purpose — the point is honest typing of the common classroom
    samples, not a full libmagic."""
    if data[:2] == b"MZ":
        return "PE executable (Windows)", "application/vnd.microsoft.portable-executable"
    if data[:4] == b"\x7fELF":
        return "ELF executable (Linux)", "application/x-elf"
    if data[:4] in (b"\xca\xfe\xba\xbe", b"\xcf\xfa\xed\xfe"):
        return "Mach-O executable (macOS)", "application/x-mach-binary"
    if data[:4] == b"%PDF":
        return "PDF document", "application/pdf"
    if data[:2] == b"PK":
        # OOXML (docx/xlsx/pptx), jar, apk and plain zips all start PK.
        return "ZIP / OOXML archive", "application/zip"
    if data[:4] == b"Rar!":
        return "RAR archive", "application/vnd.rar"
    if data[:2] == b"\x1f\x8b":
        return "gzip archive", "application/gzip"
    if data[:6] in (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"[:6],):
        return "OLE2 / legacy Office", "application/x-ole-storage"
    if data[:4] == b"{\\rt":
        return "RTF document", "application/rtf"
    if data[:2] == b"#!":
        return "script (shebang)", "text/x-shellscript"
    if b"<script" in data[:512].lower() or b"<html" in data[:512].lower():
        return "HTML / script", "text/html"
    if _looks_text(data):
        return "text", "text/plain"
    return "unknown binary", "application/octet-stream"


def _looks_text(data: bytes) -> bool:
    sample = data[:1024]
    if not sample:
        return True
    printable = sum(1 for b in sample if b in (9, 10, 13) or 32 <= b < 127)
    return printable / len(sample) > 0.9


_ASCII_RE = re.compile(rb"[\x20-\x7e]{5,}")
_URL_RE = re.compile(r"\bhttps?://[^\s\"'<>)\]]{4,}", re.IGNORECASE)
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_DOMAIN_RE = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}\b", re.IGNORECASE
)


def extract_strings(data: bytes, limit: int = 400) -> list[str]:
    """ASCII plus naive UTF-16LE (every other byte a printable) — enough to
    surface embedded URLs and config in packed Windows samples."""
    out: list[str] = [m.decode("ascii", "ignore") for m in _ASCII_RE.findall(data)]
    # UTF-16LE: drop the NUL bytes and re-scan.
    if b"\x00" in data[:4096]:
        collapsed = bytes(b for b in data if b != 0)
        out.extend(m.decode("ascii", "ignore") for m in _ASCII_RE.findall(collapsed))
    # De-dup preserving order, cap the count.
    seen: set[str] = set()
    unique: list[str] = []
    for s in out:
        if s not in seen:
            seen.add(s)
            unique.append(s)
        if len(unique) >= limit:
            break
    return unique


def extract_iocs(strings: list[str]) -> dict:
    urls, ips, domains = [], [], []
    for s in strings:
        for m in _URL_RE.findall(s):
            if m not in urls:
                urls.append(m)
        for m in _IPV4_RE.findall(s):
            if _valid_ipv4(m) and m not in ips:
                ips.append(m)
    # Domains from URLs plus bare domains in strings, minus obvious file names.
    for u in urls:
        host = re.sub(r"^https?://", "", u).split("/", 1)[0].split(":", 1)[0]
        if _DOMAIN_RE.fullmatch(host) and host not in domains:
            domains.append(host)
    for s in strings:
        for m in _DOMAIN_RE.findall(s):
            if m.lower().rsplit(".", 1)[-1] in _FILE_EXTS:
                continue
            if m not in domains:
                domains.append(m)
    return {"urls": urls[:64], "ips": ips[:64], "domains": domains[:64]}


_FILE_EXTS = {
    "dll", "exe", "sys", "png", "jpg", "gif", "txt", "log", "dat", "tmp",
    "bin", "com", "bat", "ps1", "vbs", "js", "json", "xml", "html",
}


def _valid_ipv4(s: str) -> bool:
    parts = s.split(".")
    return len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)


def static_precheck(filename: str, data: bytes, packed_threshold: float) -> Static:
    file_type, media_type = sniff_magic(data)
    entropy = shannon_entropy(data)
    strings = extract_strings(data)
    iocs = extract_iocs(strings)
    is_eicar = EICAR.encode() in data
    packed = entropy >= packed_threshold and len(data) > 512

    notes: list[str] = []
    if is_eicar:
        notes.append("EICAR anti-malware test signature present")
    if packed:
        notes.append(f"high whole-file entropy ({entropy:.2f} bits/byte): likely packed or encrypted")
    if iocs["urls"] or iocs["ips"]:
        notes.append(
            f"{len(iocs['urls'])} embedded URL(s), {len(iocs['ips'])} IPv4 literal(s)"
        )
    if file_type.startswith("PE") and b".vmp" in data[:65536]:
        notes.append("VMProtect section name observed")
    if not notes:
        notes.append("no static red flags in the pre-check")

    return Static(
        file_type=file_type,
        media_type=media_type,
        size=len(data),
        entropy=entropy,
        packed=packed,
        is_eicar=is_eicar,
        strings_sample=strings[:60],
        iocs=iocs,
        notes=notes,
    )


# -- verdict scoring -----------------------------------------------------------


@dataclass
class Verdict:
    verdict: str  # unknown|clean|suspicious|malicious
    score: int  # 0-100
    family: str | None
    mitre: list[str]
    summary: str


def derive_verdict(static: Static) -> Verdict:
    """Combine the real static signals into a verdict. Deliberately
    conservative: only EICAR (a known test positive) reaches a definitive
    'malicious'. Everything else lands at 'suspicious' or 'clean' with the
    reasoning spelled out, because static-only analysis cannot confirm intent."""
    score = 0
    mitre: list[str] = []
    reasons: list[str] = []
    family: str | None = None

    if static.is_eicar:
        # The standard test file: treat as a confirmed (benign) positive so the
        # whole pipeline — verdict, MITRE, summary — is exercised end to end.
        return Verdict(
            verdict="malicious",
            score=100,
            family="EICAR-Test-File",
            mitre=["T1204.002"],  # user execution: malicious file
            summary=(
                "EICAR anti-malware test file. This is the industry-standard "
                "benign test artifact, not real malware — it exists to prove a "
                "scanner or sandbox flags what it should. Verdict is malicious "
                "by design; blast radius is zero."
            ),
        )

    if static.packed:
        score += 45
        mitre.append("T1027.002")  # obfuscated files: software packing
        reasons.append("packed/encrypted payload (high entropy)")
    if static.iocs["urls"] or static.iocs["ips"]:
        score += 25
        mitre.append("T1071.001")  # application layer protocol: web
        reasons.append("embedded network indicators")
    if static.file_type.startswith(("PE", "ELF", "Mach-O")):
        score += 15
        reasons.append(f"native executable ({static.file_type})")
    if static.file_type.startswith(("PDF", "RTF", "OLE2")):
        score += 10
        mitre.append("T1204.002")
        reasons.append("document format with a history of embedded exploits")

    score = min(score, 95)
    if score >= 50:
        verdict = "suspicious"
    elif score >= 20:
        verdict = "suspicious"
    elif static.size == 0:
        verdict = "unknown"
    else:
        verdict = "clean"

    if verdict == "clean":
        summary = (
            "No static red flags. The pre-check found no packing, no embedded "
            "network indicators, and no known test signatures. Dynamic analysis "
            "would confirm behavior at runtime."
        )
    elif verdict == "unknown":
        summary = "Empty or unreadable submission; nothing to analyze."
    else:
        summary = (
            "Static pre-check raised "
            + str(len(reasons))
            + " signal(s): "
            + "; ".join(reasons)
            + ". No definitive family match from static data alone — a full "
            "detonation on the isolated host would settle intent."
        )
    # dedupe mitre, preserve order
    mitre = list(dict.fromkeys(mitre))
    return Verdict(verdict=verdict, score=score, family=family, mitre=mitre, summary=summary)


# -- synthetic behavior trace (demo detonator only) ----------------------------


def synthesize_behavior(static: Static, sha256: str) -> list[dict]:
    """A deterministic, clearly-labelled synthetic dynamic trace for the demo
    detonator. Returns event dicts (category/level/msg/data) in order. The
    first line states plainly that this run did not execute the sample."""
    rng = random.Random(int(sha256[:8], 16))
    events: list[dict] = []

    def add(category: str, level: str, msg: str, **data):
        events.append({"category": category, "level": level, "msg": msg, "data": data})

    add(
        "system",
        "info",
        "demo detonator: no isolated host configured — dynamic analysis is "
        "SIMULATED. Static findings above are real; the trace below is "
        "illustrative (deploy sandbox_coordinator_url for live detonation).",
    )

    root_pid = 1000 + rng.randrange(1000)
    sample_name = f"sample_{sha256[:8]}"
    exe = f"{sample_name}.exe" if static.file_type.startswith("PE") else sample_name
    add(
        "process",
        "info",
        f"process created: {exe} (pid {root_pid})",
        pid=root_pid,
        ppid=0,
        name=exe,
        cmdline=exe,
    )

    if static.packed:
        child = root_pid + 1
        add(
            "process",
            "warn",
            f"self-unpack: {exe} spawned {exe} (pid {child}) from an RWX region",
            pid=child,
            ppid=root_pid,
            name=exe,
            cmdline=f"{exe} --unpacked",
        )

    # File-system: a couple of writes to the tmpfs work dir.
    for name in (f"{sample_name}.tmp", "config.bin"):
        add(
            "file",
            "info",
            f"file write: /work/{name}",
            path=f"/work/{name}",
            op="write",
            bytes=rng.randrange(512, 65536),
        )

    # Network: everything lands on the fake-internet responder, never egresses.
    for domain in static.iocs["domains"][:3] or ["update.example-c2.test"]:
        add(
            "network",
            "alert" if static.iocs["domains"] else "info",
            f"DNS query: {domain} -> answered by INetSim (10.200.0.2)",
            proto="dns",
            query=domain,
            answer="10.200.0.2",
        )
        add(
            "network",
            "alert" if static.iocs["urls"] else "info",
            f"HTTP GET http://{domain}/gate.php (captured, no egress)",
            proto="http",
            host=domain,
            method="GET",
            path="/gate.php",
        )
    for ip in static.iocs["ips"][:2]:
        add(
            "network",
            "alert",
            f"TCP connect {ip}:443 -> sinkholed at the detonation bridge",
            proto="tcp",
            dest=ip,
            port=443,
        )

    # Memory: the demo "config extraction" just echoes the real strings.
    if static.strings_sample:
        add(
            "memory",
            "info",
            "memory scan: recovered "
            f"{len(static.strings_sample)} printable string(s) from the image",
            sample=static.strings_sample[:8],
        )

    add(
        "system",
        "ok",
        "detonation window closed (simulated 5-minute wall clock); container "
        "and tmpfs discarded",
    )
    return events

"""Static pre-check run before the sample is ever executed."""

from __future__ import annotations

import hashlib
import math
import re

MAGIC = [
    (b"MZ", "pe", "Windows executable (PE/MZ)"),
    (b"\x7fELF", "elf", "Linux executable (ELF)"),
    (b"%PDF", "pdf", "PDF document"),
    (b"PK\x03\x04", "zip", "ZIP archive or OOXML document"),
    (b"\xd0\xcf\x11\xe0", "ole", "Legacy Office (OLE compound file)"),
    (b"#!", "script", "Script with shebang"),
    (b"\x1f\x8b", "gzip", "gzip archive"),
    (b"Rar!", "rar", "RAR archive"),
    (b"7z\xbc\xaf", "7z", "7-Zip archive"),
]

URL_RE = re.compile(rb"https?://[\w\-\.:/%\?#\[\]@!\$&'\(\)\*\+,;=~]{4,200}")
IP_RE = re.compile(rb"\b(?:\d{1,3}\.){3}\d{1,3}\b")
DOMAIN_RE = re.compile(rb"\b(?:[a-zA-Z0-9\-]{1,63}\.)+(?:[a-zA-Z]{2,24})\b")

# Built at runtime so this source file does not itself trip host AV.
_EICAR = (
    rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$"
    + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!"
    + b"$H+H*"
)


def shannon(data: bytes) -> float:
    if not data:
        return 0.0
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in counts if c)


def _strings(data: bytes, minimum: int = 5) -> list[bytes]:
    out = re.findall(rb"[\x20-\x7e]{%d,}" % minimum, data)
    # UTF-16LE ASCII runs
    out += [
        s.replace(b"\x00", b"")
        for s in re.findall(rb"(?:[\x20-\x7e]\x00){%d,}" % minimum, data)
    ]
    return out


def analyse(filename: str, data: bytes) -> tuple[dict, dict]:
    """Returns (static_dict, iocs_dict)."""
    kind, label = "unknown", "Unrecognised file type"
    for sig, k, desc in MAGIC:
        if data.startswith(sig):
            kind, label = k, desc
            break

    entropy = shannon(data[: 1024 * 1024])
    packed = entropy > 7.2 and kind in {"pe", "elf", "unknown"}

    blob = b"\n".join(_strings(data))
    urls = sorted({u.decode("utf-8", "ignore") for u in URL_RE.findall(blob)})[:100]
    ips = sorted({i.decode() for i in IP_RE.findall(blob)})[:100]
    domains = sorted(
        {
            d.decode("utf-8", "ignore").lower()
            for d in DOMAIN_RE.findall(blob)
            if b"." in d and not d.replace(b".", b"").isdigit()
        }
    )[:100]

    static = {
        "filename": filename,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "md5": hashlib.md5(data).hexdigest(),
        "type": kind,
        "type_label": label,
        "entropy": round(entropy, 3),
        "packed": packed,
        "eicar": _EICAR in data,
    }
    return static, {"urls": urls, "ips": ips, "domains": domains}


def static_events(static: dict) -> list[dict]:
    ev = [
        {
            "category": "static",
            "level": "info",
            "msg": f"{static['type_label']}, {static['size']} bytes, "
            f"entropy {static['entropy']}",
            "data": {
                "sha256": static["sha256"],
                "type": static["type"],
                "entropy": static["entropy"],
            },
        }
    ]
    if static["packed"]:
        ev.append(
            {
                "category": "static",
                "level": "warn",
                "msg": "high entropy: sample looks packed or encrypted",
                "data": {"entropy": static["entropy"]},
            }
        )
    if static["eicar"]:
        ev.append(
            {
                "category": "static",
                "level": "alert",
                "msg": "EICAR anti-malware test file detected",
                "data": {},
            }
        )
    return ev

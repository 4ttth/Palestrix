"""Static analysis of a PowerShell command line.

A submitted command is usually obfuscated, because that is the whole point of
the delivery stage: a base64 blob inside a base64 blob inside an IEX. Running
it tells you what it did; peeling it tells you what it *is*, and the two
answers are both worth having. Peeling also survives the cases detonation does
not cover -- a cradle whose C2 is unreachable does nothing observable at all,
but its URL is right there in layer two.

So this unwraps encoding layers until they stop yielding text, then reads
every layer for behaviour. Nothing here executes anything: decoding base64 is
not running it, and the output is only ever treated as bytes to scan.
"""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass, field

MAX_LAYERS = 8
MIN_B64_RUN = 24

B64_RUN = re.compile(r"[A-Za-z0-9+/]{%d,}={0,2}" % MIN_B64_RUN)
URL_RE = re.compile(r"\bhttps?://[^\s\"'<>)\]\},]{4,300}", re.IGNORECASE)
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
DOMAIN_RE = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}\b", re.IGNORECASE
)

# (regex, label, mitre ids, weight). Matched against every decoded layer, so
# a technique hidden two base64 layers down still scores.
SIGNALS: tuple[tuple[str, str, tuple[str, ...], int], ...] = (
    (r"-e(nc(odedcommand)?)?\s+[A-Za-z0-9+/=]{%d,}" % MIN_B64_RUN,
     "-EncodedCommand base64 payload", ("T1027.010", "T1140"), 20),
    (r"frombase64string",
     "runtime base64 decode (FromBase64String)", ("T1140",), 15),
    (r"\b(iex|invoke-expression)\b",
     "Invoke-Expression: executes a constructed string", ("T1059.001",), 20),
    (r"(gzipstream|deflatestream)",
     "compressed payload unpacked in memory", ("T1027",), 15),
    (r"(net\.webclient|downloadstring|downloadfile|invoke-webrequest|\biwr\b|start-bitstransfer)",
     "download cradle: fetches a remote payload", ("T1105",), 25),
    (r"(amsiutils|amsiinitfailed|amsiscanbuffer)",
     "AMSI tamper: disables in-memory scanning", ("T1562.001",), 30),
    (r"(-w(indowstyle)?\s+hidden|-nop\b|-noprofile|-ep\s+bypass|-executionpolicy\s+bypass|-noni)",
     "stealth/bypass launch flags", ("T1564.003",), 10),
    (r"(schtasks|new-scheduledtask|register-scheduledtask)",
     "scheduled task persistence", ("T1053.005",), 20),
    (r"(currentversion\\\\run|currentversion/run|hklm:.*\\\\run|hkcu:.*\\\\run)",
     "Run key persistence", ("T1547.001",), 20),
    (r"(virtualalloc|writeprocessmemory|createremotethread|ntmapviewofsection)",
     "process injection primitives", ("T1055",), 30),
    (r"(\[reflection\.assembly\]::load|add-type\s|\[appdomain\])",
     "in-memory assembly loading", ("T1620",), 20),
    (r"(mimikatz|sekurlsa|lsass|invoke-mimikatz)",
     "credential dumping tooling", ("T1003.001",), 30),
    (r"(-join\s*\(|\[char\[\]\]|\[char\]\s*0x|\[convert\]::tochar)",
     "character-array string rebuilding", ("T1027.010",), 10),
    (r"\[array\]::reverse|\.\.\s*-1\]",
     "reversed string obfuscation", ("T1027.010",), 10),
    (r"`",
     "backtick token splitting", ("T1027.010",), 5),
    (r"\{\d+\}.*-f\s",
     "format-operator string assembly", ("T1027.010",), 10),
    (r"(set-mppreference|add-mppreference|-exclusionpath|windefend)",
     "Defender tampering", ("T1562.001",), 30),
    (r"(bitsadmin|certutil\s+-urlcache|certutil\s+-decode)",
     "living-off-the-land transfer/decode utility", ("T1105", "T1140"), 20),
)

_COMPILED = tuple((re.compile(p, re.IGNORECASE), lbl, m, w) for p, lbl, m, w in SIGNALS)


@dataclass
class PsResult:
    layers: list[str] = field(default_factory=list)
    techniques: list[str] = field(default_factory=list)
    mitre: list[str] = field(default_factory=list)
    score: int = 0
    iocs: dict = field(default_factory=lambda: {"urls": [], "ips": [], "domains": []})
    deobfuscated: bool = False


def _printable_ratio(s: str) -> float:
    if not s:
        return 0.0
    good = sum(1 for c in s if c in "\t\r\n" or 32 <= ord(c) < 127)
    return good / len(s)


def _try_b64(run: str) -> str | None:
    """Decode a base64 run if it yields text.

    UTF-16LE first: that is what PowerShell's own -EncodedCommand uses, and a
    UTF-8 attempt on UTF-16 data succeeds while producing NUL-riddled noise.
    """
    padded = run + "=" * (-len(run) % 4)
    try:
        raw = base64.b64decode(padded, validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(raw) < 4:
        return None
    for enc in ("utf-16-le", "utf-8"):
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        if _printable_ratio(text) > 0.85:
            return text
    return None


def peel(command: str) -> list[str]:
    """Return every decoding layer, starting with the original command."""
    layers = [command]
    seen = {command}
    current = command

    for _ in range(MAX_LAYERS):
        decoded: list[str] = []
        for run in B64_RUN.findall(current):
            text = _try_b64(run)
            if text and text not in seen:
                seen.add(text)
                decoded.append(text)
        if not decoded:
            break
        current = "\n".join(decoded)
        layers.append(current)
    return layers


def _iocs(text: str) -> dict:
    urls = sorted(set(URL_RE.findall(text)))[:100]
    ips = sorted({
        i for i in IP_RE.findall(text)
        if all(p.isdigit() and int(p) <= 255 for p in i.split("."))
    })[:100]
    domains = sorted({
        d.lower() for d in DOMAIN_RE.findall(text)
        if not d.replace(".", "").isdigit()
    })[:100]
    return {"urls": urls, "ips": ips, "domains": domains}


def analyse(command: str) -> PsResult:
    res = PsResult()
    res.layers = peel(command)
    res.deobfuscated = len(res.layers) > 1

    haystack = "\n".join(res.layers)
    mitre: set[str] = {"T1059.001"}   # it is, definitionally, PowerShell
    score = 0

    for rx, label, ids, weight in _COMPILED:
        if rx.search(haystack):
            res.techniques.append(label)
            mitre.update(ids)
            score += weight

    if res.deobfuscated:
        res.techniques.insert(
            0, f"layered encoding: {len(res.layers) - 1} decode layer(s) peeled"
        )
        mitre.add("T1140")
        score += 10 * (len(res.layers) - 1)

    res.iocs = _iocs(haystack)
    if res.iocs["urls"] or res.iocs["ips"]:
        score += 10

    res.score = max(0, min(100, score))
    res.mitre = sorted(mitre)
    return res


def to_static(command: str, res: PsResult) -> dict:
    """Shape the result like staticcheck.analyse() so the report renders it
    through the panels that already exist."""
    return {
        "filename": "command.ps1",
        "size": len(command.encode("utf-8", "replace")),
        "type": "powershell",
        "type_label": "PowerShell command line",
        "entropy": 0.0,
        "packed": False,
        "eicar": False,
        "command": command,
        "ps_layers": res.layers[1:][:MAX_LAYERS],
        "ps_techniques": res.techniques,
        "ps_deobfuscated": res.deobfuscated,
    }


def events(res: PsResult) -> list[dict]:
    ev: list[dict] = [{
        "category": "static",
        "level": "info",
        "msg": "PowerShell command submitted for detonation",
        "data": {"layers": len(res.layers)},
    }]
    for i, layer in enumerate(res.layers[1:], start=1):
        preview = layer.strip().replace("\n", " ")[:240]
        ev.append({
            "category": "static",
            "level": "alert",
            "msg": f"decode layer {i}: {preview}",
            "data": {"layer": i, "length": len(layer)},
        })
    for t in res.techniques:
        ev.append({
            "category": "static",
            "level": "warn",
            "msg": t,
            "data": {},
        })
    return ev

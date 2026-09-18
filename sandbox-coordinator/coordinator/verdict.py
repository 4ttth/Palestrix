"""Scoring.

Deliberately conservative: an air-gapped detonation cannot prove a sample is
harmless, only that it did nothing observable in the time allowed. So the
absence of behaviour never yields "clean" on its own -- it yields "unknown".
"""

from __future__ import annotations

from .pcapparse import NetFacts

WELL_KNOWN = {80, 443, 53, 8080, 8443}


def assess(static: dict, net: NetFacts, ran: bool) -> dict:
    score = 0
    mitre: list[str] = []
    reasons: list[str] = []

    if static.get("eicar"):
        return {
            "verdict": "malicious",
            "score": 100,
            "family": "EICAR-Test-File",
            "mitre": [],
            "summary": "EICAR anti-malware test file. Not real malware; "
            "confirms the detonation path end to end.",
        }

    if static.get("packed"):
        score += 15
        mitre.append("T1027")
        reasons.append("high-entropy sections suggest packing or encryption")

    if net.dns_queries:
        score += 20
        mitre.append("T1071.004")
        reasons.append(f"resolved {net.dns_queries} domain(s)")

    if net.http_requests:
        score += 25
        mitre.append("T1071.001")
        reasons.append(f"issued {net.http_requests} HTTP request(s)")

    if net.sni:
        score += 20
        mitre.append("T1573")
        reasons.append(f"opened TLS to {len(net.sni)} host(s)")

    odd_ports = sorted({p for p in net.ports if p not in WELL_KNOWN})
    if odd_ports:
        score += 20
        mitre.append("T1571")
        reasons.append(
            "contacted non-standard port(s): "
            + ", ".join(str(p) for p in odd_ports[:6])
        )

    distinct_ips = len(set(net.ips))
    if distinct_ips >= 10:
        score += 15
        mitre.append("T1046")
        reasons.append(f"touched {distinct_ips} distinct hosts (scan-like)")
    elif net.syn_attempts:
        score += 10
        reasons.append(f"{net.syn_attempts} outbound connection attempt(s)")

    score = max(0, min(100, score))

    if score >= 60:
        verdict = "malicious"
    elif score >= 25:
        verdict = "suspicious"
    elif not ran:
        verdict = "unknown"
    elif net.packets == 0:
        # Ran, but silent. Could be benign, could be sandbox-aware.
        verdict = "unknown"
        reasons.append(
            "no observable behaviour in the detonation window -- may be benign, "
            "may be sandbox-aware or waiting on a live network"
        )
    else:
        verdict = "unknown"

    summary = (
        "; ".join(reasons)
        if reasons
        else "No network or static indicators observed during detonation."
    )
    return {
        "verdict": verdict,
        "score": score,
        "family": None,
        "mitre": sorted(set(mitre)),
        "summary": summary,
    }

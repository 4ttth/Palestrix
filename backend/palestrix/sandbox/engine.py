"""The detonator abstraction and its registry.

A ``Detonator`` turns sample bytes into an ``AnalysisResult`` — the verdict,
the static findings, the behavior trace, and any artifacts to archive. It does
*not* touch the database or object storage; the ``sandbox.detonate`` job
(palestrix/sandbox/jobs.py) owns persistence, so a detonator is a pure,
testable unit exactly like the analysis functions it calls.

Configuration decides what is real, mirroring the Phase 4 provider registry:
the built-in ``DemoDetonator`` runs the real static pre-check and a labelled
synthetic dynamic trace (safe anywhere, the dev/test default); setting
PALESTRIX_SANDBOX_COORDINATOR_URL swaps in the ``CoordinatorDetonator``
(palestrix/sandbox/coordinator.py), which drives the isolated detonation host
over its single permitted port. The HTTP contract the frontend sees is
identical either way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..config import get_settings
from . import analysis


@dataclass
class Artifact:
    """A file to archive under sandbox-reports/<run>/ after analysis. Raw
    dropped samples stay inside the module; downloads are gated in the API."""

    name: str
    kind: str  # report | pcap | memdump | dropped | screenshot
    data: bytes
    media_type: str = "application/octet-stream"


@dataclass
class AnalysisResult:
    static: dict
    verdict: str
    score: int
    family: str | None
    mitre: list[str]
    iocs: dict
    summary: str
    events: list[dict] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)


@runtime_checkable
class Detonator(Protocol):
    name: str
    live: bool  # True only for a detonator backed by a real isolated host

    def analyze(
        self, filename: str, sha256: str, data: bytes, kind: str = "file"
    ) -> AnalysisResult: ...


class DetonatorUnavailable(RuntimeError):
    """Raised by a real detonator when its isolated host is not reachable or
    not configured. The job turns this into a failed run with an honest line,
    never a fabricated report."""


class DemoDetonator:
    """The default. Real static analysis on the actual bytes; a deterministic,
    explicitly-simulated dynamic trace. Never executes the sample."""

    name = "demo"
    live = False

    def analyze(
        self, filename: str, sha256: str, data: bytes, kind: str = "file"
    ) -> AnalysisResult:
        settings = get_settings()
        static = analysis.static_precheck(
            filename, data, settings.sandbox_entropy_packed_threshold
        )
        verdict = analysis.derive_verdict(static)
        events = analysis.synthesize_behavior(static, sha256)

        import json

        report_blob = json.dumps(
            {
                "sha256": sha256,
                "filename": filename,
                "detonator": self.name,
                "verdict": verdict.verdict,
                "score": verdict.score,
                "family": verdict.family,
                "mitre": verdict.mitre,
                "static": static.as_dict(),
                "iocs": static.iocs,
                "summary": verdict.summary,
            },
            indent=2,
        ).encode()

        artifacts = [
            Artifact("report.json", "report", report_blob, "application/json"),
            # A stand-in pcap so the "pull the capture" affordance is real; the
            # coordinator detonator replaces this with a genuine tcpdump capture.
            Artifact(
                "capture.txt",
                "pcap",
                _fake_capture(static).encode(),
                "text/plain",
            ),
        ]
        return AnalysisResult(
            static=static.as_dict(),
            verdict=verdict.verdict,
            score=verdict.score,
            family=verdict.family,
            mitre=verdict.mitre,
            iocs=static.iocs,
            summary=verdict.summary,
            events=events,
            artifacts=artifacts,
        )


def _fake_capture(static: analysis.Static) -> str:
    lines = ["# simulated capture (demo detonator; no live traffic)"]
    for d in static.iocs["domains"][:5]:
        lines.append(f"DNS  A? {d}  -> 10.200.0.2 (INetSim)")
        lines.append(f"HTTP GET http://{d}/gate.php  200 (sinkholed)")
    for ip in static.iocs["ips"][:5]:
        lines.append(f"TCP  connect {ip}:443  (no egress)")
    if len(lines) == 1:
        lines.append("# no network indicators observed statically")
    return "\n".join(lines) + "\n"


# -- registry ------------------------------------------------------------------

_detonator: Detonator = DemoDetonator()


def register_detonator(detonator: Detonator) -> None:
    global _detonator
    _detonator = detonator


def get_detonator() -> Detonator:
    return _detonator

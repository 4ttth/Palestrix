"""The real detonator: a thin client to the isolated sandbox host's
coordinator.

This is the adapter that talks to ``sandbox-01`` (docs/sandbox-security.md).
The coordinator is the *only* thing the core API may reach on the sandbox
VLAN/subnet — a single TCP port through the switch ACL / security group. The
core process never sees the detonation container, the fake-internet bridge, or
the raw pcap; it submits bytes and receives a structured result.

Wire contract (the coordinator implements the other half on the isolated
host; that half is deployment code, not part of this repository):

    POST {url}/detonate
      headers: Authorization: Bearer <coordinator token>
      body:    multipart {sha256, filename, sample}
      200 ->   {verdict, score, family, mitre[], iocs{}, static{},
                summary, events[], artifacts[{name,kind,media_type,b64}]}

Until PALESTRIX_SANDBOX_COORDINATOR_URL is set this adapter is not registered;
``activate_configured_detonator`` leaves the demo detonator in place. If it is
set but unreachable, ``analyze`` raises ``DetonatorUnavailable`` and the job
records an honest failure — the platform never fabricates a report.
"""

from __future__ import annotations

import base64

from ..config import get_settings
from .engine import AnalysisResult, Artifact, DetonatorUnavailable


class CoordinatorDetonator:
    name = "coordinator"
    live = True

    def __init__(self, client=None) -> None:
        self._client = client  # injectable for tests (httpx.Client / MockTransport)

    def _http(self):
        if self._client is not None:
            return self._client
        import httpx

        settings = get_settings()
        if not settings.sandbox_coordinator_url:
            raise DetonatorUnavailable("no sandbox coordinator configured")
        return httpx.Client(
            base_url=settings.sandbox_coordinator_url.rstrip("/"),
            headers={"Authorization": f"Bearer {settings.sandbox_coordinator_token}"},
            verify=settings.sandbox_coordinator_verify_tls,
            timeout=settings.sandbox_coordinator_timeout_seconds,
        )

    def analyze(self, filename: str, sha256: str, data: bytes) -> AnalysisResult:
        import httpx

        client = self._http()
        try:
            resp = client.post(
                "/detonate",
                data={"sha256": sha256, "filename": filename},
                files={"sample": (filename, data)},
            )
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPError as exc:  # network, TLS, timeout, 5xx
            raise DetonatorUnavailable(f"sandbox coordinator unreachable: {exc}") from exc

        artifacts = [
            Artifact(
                name=a["name"],
                kind=a.get("kind", "dropped"),
                data=base64.b64decode(a["b64"]),
                media_type=a.get("media_type", "application/octet-stream"),
            )
            for a in body.get("artifacts", [])
        ]
        return AnalysisResult(
            static=body.get("static", {}),
            verdict=body.get("verdict", "unknown"),
            score=int(body.get("score", 0)),
            family=body.get("family"),
            mitre=list(body.get("mitre", [])),
            iocs=body.get("iocs", {"urls": [], "ips": [], "domains": []}),
            summary=body.get("summary", ""),
            events=list(body.get("events", [])),
            artifacts=artifacts,
        )

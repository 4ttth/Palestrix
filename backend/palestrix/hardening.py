"""Phase 7 deployment hardening: the production boot guard and the security
headers every response carries.

The runbooks (docs/usecase-a-baremetal.md, docs/usecase-b-cloud-aws.md) tell
a site what a hardened deployment looks like; this module is the part the
app can verify itself. Setting PALESTRIX_ENVIRONMENT=production arms the
guard: the API refuses to start while ``production_readiness`` reports
failures, so a misconfigured deployment dies loudly at boot instead of
serving traffic on a dev secret. In development the same findings are
logged as warnings and nothing is blocked.
"""

from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from .config import Settings
from .tls import TrustConfigError, trust_context

logger = logging.getLogger("palestrix.hardening")

DEV_SECRET = "dev-only-secret-change-me"


def production_readiness(settings: Settings) -> list[str]:
    """Everything that must not survive into production, one finding per
    item. Empty list == ready. Checks are deliberately static (configuration
    only, no network probes) so the guard cannot flake."""
    findings: list[str] = []
    if settings.secret_key == DEV_SECRET:
        findings.append(
            "PALESTRIX_SECRET_KEY is the development default; generate a "
            "unique secret (the runbooks keep it in sops/Vault or a cloud "
            "secrets manager, never in the unit file)"
        )
    elif len(settings.secret_key) < 32:
        findings.append("PALESTRIX_SECRET_KEY is shorter than 32 characters")
    if settings.database_url.startswith("sqlite"):
        findings.append(
            "PALESTRIX_DATABASE_URL is SQLite; production runs PostgreSQL"
        )
    if not settings.origin.startswith("https://"):
        findings.append(
            "PALESTRIX_ORIGIN is not https; passkeys (WebAuthn) require a "
            "secure origin outside localhost"
        )
    for origin in settings.cors_origins.split(","):
        origin = origin.strip()
        if origin == "*":
            findings.append("PALESTRIX_CORS_ORIGINS allows every origin (*)")
        elif origin.startswith("http://") and "localhost" not in origin:
            findings.append(f"PALESTRIX_CORS_ORIGINS contains plaintext origin {origin}")
    if settings.proxmox_host and not settings.proxmox_verify_tls:
        findings.append("PALESTRIX_PROXMOX_VERIFY_TLS is off")
    if settings.sandbox_coordinator_url and not settings.sandbox_coordinator_verify_tls:
        findings.append("PALESTRIX_SANDBOX_COORDINATOR_VERIFY_TLS is off")
    if settings.cloudstack_endpoint and not settings.cloudstack_verify_tls:
        findings.append("PALESTRIX_CLOUDSTACK_VERIFY_TLS is off")
    if settings.canvas_issuer and not settings.canvas_verify_tls:
        findings.append("PALESTRIX_CANVAS_VERIFY_TLS is off")
    if settings.canvas_issuer and not settings.canvas_tool_private_key:
        findings.append(
            "PALESTRIX_CANVAS_TOOL_PRIVATE_KEY is empty; the tool signing key "
            "would rotate on every restart and Canvas, which pins the "
            "published JWKS, would reject launches"
        )
    # A pinned CA that cannot be read fails every outbound call at the first
    # request instead of at boot, which is exactly what this guard exists to
    # prevent. Reading the file is local, so the checks still cannot flake.
    for name, bundle in (
        ("PROXMOX", settings.proxmox_ca_bundle),
        ("SANDBOX_COORDINATOR", settings.sandbox_coordinator_ca_bundle),
        ("CLOUDSTACK", settings.cloudstack_ca_bundle),
        ("CANVAS", settings.canvas_ca_bundle),
    ):
        if not bundle:
            continue
        try:
            trust_context(bundle)
        except TrustConfigError as exc:
            findings.append(f"PALESTRIX_{name}_CA_BUNDLE is unusable: {exc}")
    if settings.webauthn_challenge_backend != "redis":
        findings.append(
            "PALESTRIX_WEBAUTHN_CHALLENGE_BACKEND is in-process memory; the "
            "API runs several uvicorn workers, so the verify request lands on "
            "a different worker than the options request and every passkey is "
            'rejected as "challenge expired or missing" — set it to "redis"'
        )
    if settings.allow_private_webhooks:
        findings.append(
            "PALESTRIX_ALLOW_PRIVATE_WEBHOOKS is on; webhooks:manage is "
            "granted to every role, so any student's subscription becomes an "
            "SSRF probe of the lab network and the hypervisor API"
        )
    if settings.queue_backend == "inline":
        findings.append(
            "PALESTRIX_QUEUE_BACKEND is inline; production provisions through "
            "Redis workers so a slow adapter cannot stall API requests"
        )
    if not settings.reaper_enabled:
        findings.append(
            "PALESTRIX_REAPER_ENABLED is off; expired instances would live forever"
        )
    if settings.storage_backend == "local":
        findings.append(
            "PALESTRIX_STORAGE_BACKEND is the local folder; production uses MinIO/S3"
        )
    return findings


def enforce_readiness(settings: Settings) -> None:
    """Boot guard, called from the app lifespan. Raises in production,
    warns in development."""
    findings = production_readiness(settings)
    if not findings:
        return
    if settings.environment == "production":
        raise RuntimeError(
            "refusing to start: production readiness failed\n- "
            + "\n- ".join(findings)
        )
    for finding in findings:
        logger.warning("not production-ready: %s", finding)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline response hardening. The edge proxy sets these too (belt and
    suspenders, per the runbooks) — the API does not rely on it. HSTS is
    production-only so plain-HTTP dev setups don't get pinned to TLS."""

    def __init__(self, app, *, production: bool) -> None:
        super().__init__(app)
        self._production = production

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        if self._production:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )
        return response

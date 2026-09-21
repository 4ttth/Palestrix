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
    if not settings.rate_limit_enabled:
        findings.append(
            "PALESTRIX_RATE_LIMIT_ENABLED is off; docs/public-api.md "
            "publishes rate limits and the login endpoint would take "
            "unlimited password guesses"
        )
    if settings.allow_private_webhooks:
        findings.append(
            "PALESTRIX_ALLOW_PRIVATE_WEBHOOKS is on; any user's webhook "
            "subscription can then reach the lab networks and the cloud "
            "metadata service (SSRF). Leave it off unless this site really "
            "posts to an internal collector"
        )
    if settings.sandbox_coordinator_url and not settings.sandbox_coordinator_token:
        findings.append(
            "PALESTRIX_SANDBOX_COORDINATOR_URL is set without "
            "PALESTRIX_SANDBOX_COORDINATOR_TOKEN; the coordinator refuses "
            "unauthenticated calls, so every detonation would fail"
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


# The LTI wire endpoints are the one surface that is *supposed* to be
# framed: a Canvas launch renders the picker and the status pages inside the
# platform's iframe. A blanket X-Frame-Options: DENY makes those pages blank
# in Canvas, so they are exempted here and pinned to the configured issuer
# instead of being opened up.
LTI_FRAMED_PREFIX = "/api/v1/integrations/canvas/"


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
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )

        framed_by = self._lti_frame_ancestor(request)
        if framed_by is None:
            response.headers.setdefault("X-Frame-Options", "DENY")
            frame_ancestors = "'none'"
        else:
            # X-Frame-Options has no allow-list form that browsers still
            # honour, so framing is expressed only through CSP here.
            frame_ancestors = framed_by

        # The API serves JSON and a handful of self-contained LTI pages; it
        # never needs to pull a script, frame, or stylesheet from anywhere.
        # Saying so bounds what an injected string in an error body or an
        # LTI page could do. 'unsafe-inline' covers the inline <style> and
        # the one-line auto-submit script the deep-link handoff needs.
        response.headers.setdefault(
            "Content-Security-Policy",
            f"default-src 'none'; frame-ancestors {frame_ancestors}; "
            "base-uri 'none'; form-action 'self' https:; "
            "style-src 'unsafe-inline'; script-src 'unsafe-inline'",
        )
        if self._production:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )
        return response

    def _lti_frame_ancestor(self, request: Request) -> str | None:
        """The platform origin allowed to frame this response, or None when
        the path is not an LTI page."""
        if not request.url.path.startswith(LTI_FRAMED_PREFIX):
            return None
        from .config import get_settings

        issuer = get_settings().canvas_issuer.rstrip("/")
        return issuer or None

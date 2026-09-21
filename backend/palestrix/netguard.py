"""Outbound-request guard for operator-supplied URLs.

Webhook subscriptions are the one place where an ordinary user hands the
platform a URL and the platform then makes a request to it. Without a check
that is a server-side request forgery primitive: a student registers
``http://169.254.169.254/latest/meta-data/`` or ``http://127.0.0.1:8000/…``
and the API reaches into the cloud metadata service or its own private
network on their behalf, reporting reachability back through the delivery
log.

So a destination is validated twice, and both times against the *resolved
address*, not the hostname — DNS is attacker-controlled, and a name that
resolves publicly at subscribe time can resolve to 127.0.0.1 at delivery
time (DNS rebinding):

- ``validate_webhook_url`` at subscribe time, so the person gets a 422 they
  can act on rather than a delivery that silently fails forever;
- ``resolve_public_target`` immediately before the request, which is the
  check that actually holds.

PALESTRIX_ALLOW_PRIVATE_WEBHOOKS re-opens private ranges for a site that
genuinely posts to an internal collector; it is off by default and the
production boot guard reports it when it is on.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

ALLOWED_SCHEMES = ("http", "https")
ALLOWED_PORTS = (80, 443, 8080, 8443)


class UnsafeWebhookTarget(ValueError):
    """The URL names an address the platform will not send to."""


def _address_is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Everything the internet cannot route to is off limits: loopback, the
    RFC1918 and CGNAT ranges, link-local (which covers the 169.254.169.254
    metadata endpoint and its IPv6 twin), multicast, and the reserved
    blocks. IPv4-mapped IPv6 is unwrapped first so ::ffff:127.0.0.1 cannot
    smuggle a loopback address past the check.
    """
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _allow_private() -> bool:
    from .config import get_settings

    return get_settings().allow_private_webhooks


def resolve_public_target(url: str) -> list[str]:
    """Every address ``url``'s host resolves to, or raise.

    Returns the full address list rather than one entry: a host with both a
    public and a private record must be refused outright, since which one
    the HTTP client picks is not ours to decide.
    """
    parts = urlsplit(url)
    if parts.scheme not in ALLOWED_SCHEMES:
        raise UnsafeWebhookTarget(f"scheme '{parts.scheme}' is not deliverable")
    host = parts.hostname
    if not host:
        raise UnsafeWebhookTarget("no host in the webhook URL")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        raise UnsafeWebhookTarget(
            f"port {port} is not a webhook port (allowed: {list(ALLOWED_PORTS)})"
        )

    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeWebhookTarget(f"host '{host}' does not resolve: {exc}") from exc

    addresses = sorted({info[4][0] for info in infos})
    if _allow_private():
        return addresses
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%", 1)[0])  # strip zone id
        if not _address_is_public(ip):
            raise UnsafeWebhookTarget(
                f"host '{host}' resolves to the non-public address {address}; "
                "webhooks may only target routable internet addresses "
                "(set PALESTRIX_ALLOW_PRIVATE_WEBHOOKS=1 to permit an "
                "internal collector)"
            )
    return addresses


def validate_webhook_url(url: str) -> None:
    """Subscribe-time check. Same rules as delivery, raised early so the
    person sees why their URL was refused."""
    resolve_public_target(url)

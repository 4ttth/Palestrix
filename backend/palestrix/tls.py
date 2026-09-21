"""Outbound TLS trust for the adapters that leave the platform.

Every client that talks to another host (Proxmox, the sandbox coordinator,
CloudStack, Canvas) builds its ``verify=`` through :func:`client_verify`
rather than passing a bare bool, so that a site can pin the CA that actually
signed its internal hosts and so that one OpenSSL quirk has a single home.

The quirk: Proxmox generates its cluster root CA (``/etc/pve/pve-root-ca.pem``)
without a keyUsage extension. Python 3.13 turned on ``ssl.VERIFY_X509_STRICT``
in ``ssl.create_default_context()``, and OpenSSL's strict mode rejects a CA
that omits keyUsage -- so on a 3.13+ runtime every call to the Proxmox API
dies with::

    [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed:
    CA cert does not include key usage extension

even though the chain is exactly the one the operator pinned. Strict mode is
an RFC 5280 conformance check, not a trust decision: clearing that one flag
restores the pre-3.13 behaviour while signature, chain, expiry and hostname
are all still verified. We clear it only for a pinned private CA -- against
the public web PKI, where conformance is the norm, strict mode stays on.
"""

from __future__ import annotations

import ssl
from functools import lru_cache


class TrustConfigError(RuntimeError):
    """The configured CA bundle cannot be loaded."""


@lru_cache
def trust_context(ca_bundle: str) -> ssl.SSLContext:
    """Verify against `ca_bundle` alone, tolerating a CA that predates
    OpenSSL's strict conformance checks (see the module docstring).

    Cached because a client is often rebuilt per request and this reads and
    parses a PEM; a rotated bundle therefore needs a restart, the same deal
    as ``get_settings()``."""
    try:
        context = ssl.create_default_context(cafile=ca_bundle)
    except OSError as exc:  # missing, unreadable, or not a PEM
        raise TrustConfigError(f"cannot load CA bundle {ca_bundle!r}: {exc}") from exc
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return context


def client_verify(verify: bool, ca_bundle: str = "") -> ssl.SSLContext | bool:
    """The ``verify=`` argument for an outbound httpx client.

    ``verify`` off short-circuits to ``False`` (no verification -- the
    production boot guard in hardening.py refuses that). Otherwise a
    configured `ca_bundle` is pinned as the only trust anchor, and an empty
    one keeps the system trust store with stock defaults.
    """
    if not verify:
        return False
    if not ca_bundle:
        return True
    return trust_context(ca_bundle)

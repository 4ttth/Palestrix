"""At-rest sealing for stored samples.

docs/sandbox-security.md requires samples be stored encrypted-at-rest. That is
not only a confidentiality control: a raw malware sample (or even the EICAR
test file) sitting on disk is quarantined on sight by any host antivirus,
which would corrupt the very artifact the analyst needs. Sealing the bytes
before they touch the object store keeps a signature scanner from matching
them, so the sample survives until the detonator asks for it.

The dev/local transform here is a keyed XOR stream derived from the platform
secret — enough to defeat signature scanning and keep samples opaque at rest.
A production MinIO/S3 deployment layers real server-side encryption (SSE-KMS)
on top; this stays valuable there as defense in depth and as the thing that
stops the storage node's own AV from eating samples.
"""

from __future__ import annotations

import hashlib

from ..config import get_settings

_DOMAIN = b"palestrix.sandbox.sample.v1"


def _keystream(length: int, key: bytes) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        out += hashlib.sha256(key + _DOMAIN + counter.to_bytes(8, "big")).digest()
        counter += 1
    return bytes(out[:length])


def seal(data: bytes) -> bytes:
    """Reversible transform applied before a sample hits object storage. XOR
    is symmetric, so ``unseal`` is the same operation."""
    key = get_settings().secret_key.encode()
    ks = _keystream(len(data), key)
    return bytes(a ^ b for a, b in zip(data, ks))


def unseal(data: bytes) -> bytes:
    return seal(data)

"""A software WebAuthn authenticator, enough to exercise a real ceremony.

The passkey tests used to stop at "options come back" and "garbage is
rejected", which let a broken success path ship: nothing ever asserted that
an enrolled passkey could actually sign in. This builds the authenticator
side for real -- ES256 over genuine authenticator data, CBOR attestation,
the clientDataJSON the browser would send -- so verify_registration and
verify_authentication are tested against valid input as well as invalid.

Deliberately minimal: "none" attestation, no user handle, no extensions.
It is a test double for the browser, not a second implementation of WebAuthn.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import struct

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)

AAGUID = b"\x00" * 16
# Flags: UP (0x01) | UV (0x04) | AT (0x40) -- user present, user verified,
# attested credential data included. The AT bit is registration-only.
FLAGS_REGISTER = 0x01 | 0x04 | 0x40
FLAGS_AUTHENTICATE = 0x01 | 0x04


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def from_b64url(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


class SoftAuthenticator:
    """One credential on one virtual security key."""

    def __init__(self) -> None:
        self._key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)
        self.sign_count = 0

    # -- COSE ----------------------------------------------------------------

    def _cose_public_key(self) -> bytes:
        numbers = self._key.public_key().public_numbers()
        return cbor2.dumps(
            {
                1: 2,  # kty: EC2
                3: -7,  # alg: ES256
                -1: 1,  # crv: P-256
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )

    # -- authenticator data ---------------------------------------------------

    def _auth_data(self, rp_id: str, flags: int, *, attested: bool) -> bytes:
        data = hashlib.sha256(rp_id.encode()).digest()
        data += struct.pack(">BI", flags, self.sign_count)
        if attested:
            key = self._cose_public_key()
            data += AAGUID
            data += struct.pack(">H", len(self.credential_id))
            data += self.credential_id
            data += key
        return data

    def _client_data(self, kind: str, challenge: str, origin: str) -> bytes:
        # `challenge` arrives already b64url-encoded, exactly as the options
        # JSON carries it, so it round-trips without re-encoding.
        return json.dumps(
            {"type": kind, "challenge": challenge, "origin": origin},
            separators=(",", ":"),
        ).encode()

    # -- ceremonies -----------------------------------------------------------

    def register(self, options: dict, origin: str) -> str:
        """The JSON SimpleWebAuthn would post to register/verify."""
        rp_id = options["rp"]["id"]
        client_data = self._client_data(
            "webauthn.create", options["challenge"], origin
        )
        auth_data = self._auth_data(rp_id, FLAGS_REGISTER, attested=True)
        attestation = cbor2.dumps(
            {"fmt": "none", "attStmt": {}, "authData": auth_data}
        )
        return json.dumps(
            {
                "id": b64url(self.credential_id),
                "rawId": b64url(self.credential_id),
                "type": "public-key",
                "response": {
                    "clientDataJSON": b64url(client_data),
                    "attestationObject": b64url(attestation),
                },
                "clientExtensionResults": {},
            }
        )

    def authenticate(self, options: dict, origin: str) -> str:
        """The JSON SimpleWebAuthn would post to login/verify."""
        rp_id = options["rpId"]
        self.sign_count += 1
        client_data = self._client_data("webauthn.get", options["challenge"], origin)
        auth_data = self._auth_data(rp_id, FLAGS_AUTHENTICATE, attested=False)
        signature = self._key.sign(
            auth_data + hashlib.sha256(client_data).digest(),
            ec.ECDSA(hashes.SHA256()),
        )
        return json.dumps(
            {
                "id": b64url(self.credential_id),
                "rawId": b64url(self.credential_id),
                "type": "public-key",
                "response": {
                    "clientDataJSON": b64url(client_data),
                    "authenticatorData": b64url(auth_data),
                    "signature": b64url(signature),
                    "userHandle": None,
                },
                "clientExtensionResults": {},
            }
        )

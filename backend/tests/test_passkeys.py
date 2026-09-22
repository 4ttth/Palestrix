"""Passkey ceremonies end to end, with a software authenticator.

These cover the success path (the old tests did not, which is how a broken
one shipped) and the two things that actually broke it: a challenge store
that is not shared between uvicorn workers, and picking which enrolled
credential an assertion belongs to.
"""

import json

from palestrix import webauthn_flow
from palestrix.config import get_settings
from palestrix.hardening import production_readiness
from softauthn import SoftAuthenticator, b64url

ORIGIN = "http://localhost:3000"


def _enroll(client, headers) -> SoftAuthenticator:
    opts = client.post("/api/v1/auth/webauthn/register/options", headers=headers)
    assert opts.status_code == 200, opts.text
    authenticator = SoftAuthenticator()
    resp = client.post(
        "/api/v1/auth/webauthn/register/verify",
        json={"credential": authenticator.register(
            json.loads(opts.json()["options"]), ORIGIN
        )},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return authenticator


def _passkey_login(client, email: str, authenticator: SoftAuthenticator):
    opts = client.post(
        "/api/v1/auth/webauthn/login/options", json={"email": email}
    )
    assert opts.status_code == 200, opts.text
    return client.post(
        f"/api/v1/auth/webauthn/login/verify?email={email}",
        json={"credential": authenticator.authenticate(
            json.loads(opts.json()["options"]), ORIGIN
        )},
    )


def test_enroll_then_sign_in(client, student2):
    """The whole point: an enrolled passkey signs in and yields a session."""
    authenticator = _enroll(client, student2)

    resp = _passkey_login(client, "stud2@example.edu", authenticator)
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]

    me = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == "stud2@example.edu"


def test_second_passkey_on_the_same_account_also_works(client, teacher):
    """Two enrolled passkeys, and the second one signs in.

    The verify endpoint used to try each credential in turn. The challenge is
    single-use, so the first mismatch consumed it and the real credential then
    failed on a missing challenge -- every account with more than one passkey
    was locked out of passkey login.
    """
    first = _enroll(client, teacher)
    second = _enroll(client, teacher)
    assert first.credential_id != second.credential_id

    for authenticator in (second, first):
        resp = _passkey_login(client, "teach1@example.edu", authenticator)
        assert resp.status_code == 200, resp.text


def test_challenge_is_single_use(client, admin):
    """A replayed assertion is rejected: the challenge is consumed on read."""
    authenticator = _enroll(client, admin)

    opts = client.post(
        "/api/v1/auth/webauthn/login/options",
        json={"email": "admin1@example.edu"},
    )
    assertion = authenticator.authenticate(json.loads(opts.json()["options"]), ORIGIN)
    body = {"credential": assertion}
    url = "/api/v1/auth/webauthn/login/verify?email=admin1@example.edu"

    assert client.post(url, json=body).status_code == 200
    assert client.post(url, json=body).status_code == 401


def test_unknown_credential_is_rejected(client, superadmin):
    """An assertion from a key that was never enrolled gets nowhere."""
    _enroll(client, superadmin)

    stranger = SoftAuthenticator()
    resp = _passkey_login(client, "super1@example.edu", stranger)
    assert resp.status_code == 401


def test_assertion_credential_id_normalises_and_survives_junk():
    authenticator = SoftAuthenticator()
    assertion = json.loads(authenticator.authenticate(
        {"rpId": "localhost", "challenge": b64url(b"x" * 32)}, ORIGIN
    ))
    assert (
        webauthn_flow.assertion_credential_id(json.dumps(assertion))
        == b64url(authenticator.credential_id)
    )
    # Padded input still resolves to the stored (unpadded) form.
    padded = dict(assertion, id=b64url(authenticator.credential_id) + "==")
    assert (
        webauthn_flow.assertion_credential_id(json.dumps(padded))
        == b64url(authenticator.credential_id)
    )
    for junk in ["", "not json", "[]", '{"id": 7}', '{"id": ""}', "{}"]:
        assert webauthn_flow.assertion_credential_id(junk) is None


def test_memory_challenge_store_does_not_cross_workers():
    """Why passkeys failed in production, pinned down.

    The deployment runs `uvicorn --workers 4`. The in-process store makes the
    challenge visible only inside the worker that issued it, so the verify
    request -- which usually lands elsewhere -- finds nothing. A fresh store
    stands in for that other worker.
    """
    settings = get_settings()
    assert settings.webauthn_challenge_backend == "memory"  # the test default

    webauthn_flow._remember("reg:someone", b"challenge-bytes")
    saved = dict(webauthn_flow._challenges)
    webauthn_flow._challenges.clear()  # the request lands on another worker
    try:
        assert webauthn_flow._recall("reg:someone") is None
    finally:
        webauthn_flow._challenges.update(saved)


def test_production_guard_rejects_the_memory_store():
    """The boot guard is what stops this being latent again."""
    settings = get_settings()
    findings = production_readiness(settings)
    assert any("WEBAUTHN_CHALLENGE_BACKEND" in f for f in findings)

    shared = settings.model_copy(update={"webauthn_challenge_backend": "redis"})
    assert not any(
        "WEBAUTHN_CHALLENGE_BACKEND" in f for f in production_readiness(shared)
    )

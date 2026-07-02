"""Registration, login, identity, API keys, OAuth2 client credentials,
and WebAuthn ceremony option endpoints."""


def test_register_login_me(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "name": "New Person",
            "handle": "newbie01",
            "email": "newbie01@example.edu",
            "password": "a-long-enough-passphrase",
        },
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    body = me.json()
    assert body["handle"] == "newbie01"
    assert body["role"] == "student"


def test_duplicate_handle_rejected(client):
    for _ in range(2):
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "name": "Dupe",
                "handle": "dupehandle",
                "email": "dupe@example.edu",
                "password": "a-long-enough-passphrase",
            },
        )
    assert resp.status_code == 409


def test_wrong_password_rejected(client):
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "stud1@example.edu", "password": "wrong-wrong-wrong"},
    )
    assert resp.status_code == 401


def test_no_credentials_is_401(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_api_key_roundtrip_and_scope_limits(client, student):
    # A student may not grant courses:write to a machine.
    resp = client.post(
        "/api/v1/auth/api-keys",
        json={"name": "bad", "scopes": ["courses:write"]},
        headers=student,
    )
    assert resp.status_code == 403

    resp = client.post(
        "/api/v1/auth/api-keys",
        json={"name": "ok", "scopes": ["instances:read", "ledger:read"]},
        headers=student,
    )
    assert resp.status_code == 201
    full_key = resp.json()["key"]
    assert full_key.startswith("plx_")

    # The key authenticates and is ownership-scoped.
    bal = client.get("/api/v1/gamification/balance", headers={"X-Api-Key": full_key})
    assert bal.status_code == 200

    # Revocation kills it.
    key_id = resp.json()["id"]
    assert (
        client.delete(f"/api/v1/auth/api-keys/{key_id}", headers=student).status_code
        == 204
    )
    assert (
        client.get(
            "/api/v1/gamification/balance", headers={"X-Api-Key": full_key}
        ).status_code
        == 401
    )


def test_oauth_client_credentials(client, teacher):
    created = client.post(
        "/api/v1/auth/clients",
        json={"name": "grader-bot", "scopes": ["courses:read", "courses:write"]},
        headers=teacher,
    )
    assert created.status_code == 201
    creds = created.json()

    token = client.post(
        "/api/v1/auth/token",
        json={
            "grant_type": "client_credentials",
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
        },
    )
    assert token.status_code == 200
    bearer = {"Authorization": f"Bearer {token.json()['access_token']}"}

    # The machine token can act within its scopes...
    resp = client.post(
        "/api/v1/courses",
        json={"code": "CS 9999", "title": "Bot Course"},
        headers=bearer,
    )
    assert resp.status_code == 201

    # ...and bad secrets are rejected.
    bad = client.post(
        "/api/v1/auth/token",
        json={
            "grant_type": "client_credentials",
            "client_id": creds["client_id"],
            "client_secret": "nope",
        },
    )
    assert bad.status_code == 401


def test_webauthn_options_and_garbage_rejection(client, student):
    opts = client.post("/api/v1/auth/webauthn/register/options", headers=student)
    assert opts.status_code == 200
    assert "challenge" in opts.json()["options"]

    bad = client.post(
        "/api/v1/auth/webauthn/register/verify",
        json={"credential": "{\"id\": \"garbage\"}"},
        headers=student,
    )
    assert bad.status_code == 400

    # No passkey enrolled yet: login options must not be offered.
    resp = client.post(
        "/api/v1/auth/webauthn/login/options",
        json={"email": "stud1@example.edu"},
    )
    assert resp.status_code == 400

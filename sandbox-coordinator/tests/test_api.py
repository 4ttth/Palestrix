"""HTTP contract tests: auth must fail closed."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _client(token: str | None):
    for k in list(os.environ):
        if k.startswith("SBX_"):
            del os.environ[k]
    if token is not None:
        os.environ["SBX_AUTH_TOKEN"] = token
    from coordinator import config, main

    config.get_settings.cache_clear()
    return TestClient(main.app)


def test_healthz_reports_configuration():
    r = _client("t0ken").get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["template_vmid"] == 900


def test_detonate_refuses_when_no_token_configured():
    """No token set must fail closed, never run open."""
    r = _client(None).post(
        "/detonate", files={"sample": ("a.bin", b"data")}, data={"filename": "a.bin"}
    )
    assert r.status_code == 503


def test_detonate_rejects_wrong_bearer():
    r = _client("right-token").post(
        "/detonate",
        files={"sample": ("a.bin", b"data")},
        data={"filename": "a.bin"},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert r.status_code == 401


def test_detonate_rejects_missing_header():
    r = _client("right-token").post(
        "/detonate", files={"sample": ("a.bin", b"data")}, data={"filename": "a.bin"}
    )
    assert r.status_code == 401


def test_detonate_rejects_sha256_mismatch():
    r = _client("right-token").post(
        "/detonate",
        files={"sample": ("a.bin", b"data")},
        data={"filename": "a.bin", "sha256": "0" * 64},
        headers={"Authorization": "Bearer right-token"},
    )
    assert r.status_code == 422

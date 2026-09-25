"""The rate limiter, and the auth bucket that stops brute force."""

from palestrix import ratelimit
from palestrix.ratelimit import bucket_for


def test_bucket_classification():
    p = "/api/v1"
    assert bucket_for(p + "/auth/login", "POST", p) == "auth"
    assert bucket_for(p + "/auth/webauthn/login/verify", "POST", p) == "auth"
    assert bucket_for(p + "/instances", "POST", p) == "launch"
    assert bucket_for(p + "/instances/lab-1/extend", "POST", p) == "launch"
    assert bucket_for(p + "/compete/challenges/c1/submit", "POST", p) == "flag"
    assert bucket_for(p + "/academy/paths", "GET", p) == "general"


def test_auth_bucket_blocks_brute_force(client):
    """Wrong-password guesses are capped: after the auth limit (20/min) the
    endpoint answers 429 instead of taking unlimited attempts."""
    ratelimit.reset()
    seen_429 = False
    for _ in range(25):
        r = client.post(
            "/api/v1/auth/login",
            json={"email": "stud1@example.edu", "password": "wrong-guess"},
        )
        if r.status_code == 429:
            seen_429 = True
            assert r.json()["detail"]["bucket"] == "auth"
            assert "Retry-After" in r.headers
            break
        else:
            assert r.status_code in (400, 401, 403, 422)
    assert seen_429, "the login endpoint never rate-limited a guess flood"
    ratelimit.reset()


def test_limit_resets_after_reset(client):
    ratelimit.reset()
    # A fresh window lets a legitimate login straight through.
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "stud1@example.edu", "password": "correct horse"},
    )
    # Wrong password, but not rate-limited on the first try.
    assert r.status_code != 429

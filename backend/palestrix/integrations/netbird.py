"""A thin NetBird Cloud API client for the superadmin overlay console.

The overlay reaps its own peers — a student's device is registered with an
ephemeral setup key and NetBird deletes it an hour after it goes offline, so
the free plan's 100-peer cap is never reached by abandoned sessions. This
module is not that mechanism; it is the *window* onto it, plus a manual
override: a superadmin who wants a slot back now, rather than within the hour,
can reap the offline student peers by hand.

Only the token holder (this process) ever talks to NetBird. The token is a PAT
read from settings and never leaves the backend — the browser sees derived
status, never the credential.

Two invariants the reap must hold, because a wrong delete here disconnects a
live student or, worse, the router that carries every lab:

- Only peers in the ``students`` group are ever candidates. The router
  (``lab-routers``) and the admin devices (``infrastructure``) are off limits
  even if some future change also tags them a student.
- A connected peer is never reaped. "Active" means "currently connected",
  which NetBird reports directly, so the check does not depend on clock skew
  between here and their console.
"""

from __future__ import annotations

import httpx

# Peers in these groups are load-bearing and must never be reaped, whatever
# else they are tagged with. The router carries the only path to the labs.
PROTECTED_GROUPS = frozenset({"lab-routers", "infrastructure"})
STUDENT_GROUP = "students"


class NetBirdError(RuntimeError):
    """The NetBird API refused or could not be reached."""


class NetBirdClient:
    def __init__(self, api_url: str, token: str, timeout: float = 10.0) -> None:
        if not token:
            raise NetBirdError("no NetBird API token configured")
        self._base = api_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self._base,
            headers={
                "Authorization": f"Token {token}",
                "Accept": "application/json",
            },
            timeout=timeout,
        )

    def _req(self, method: str, path: str, body: dict | None = None):
        try:
            resp = self._client.request(method, path, json=body)
        except httpx.HTTPError as exc:
            raise NetBirdError(f"NetBird API unreachable: {exc}") from exc
        if resp.status_code >= 400:
            # The API returns {"message": "..."} on error; fall back to status.
            detail = ""
            try:
                detail = resp.json().get("message", "")
            except Exception:
                detail = resp.text[:200]
            raise NetBirdError(
                f"NetBird API {method} {path} -> {resp.status_code}: {detail}"
            )
        if resp.content:
            return resp.json()
        return None

    def peers(self) -> list[dict]:
        return self._req("GET", "/peers") or []

    def delete_peer(self, peer_id: str) -> None:
        self._req("DELETE", f"/peers/{peer_id}")

    def close(self) -> None:
        self._client.close()


def _group_names(peer: dict) -> set[str]:
    return {g.get("name", "") for g in peer.get("groups", [])}


def classify(peer: dict) -> dict:
    """The peer as the console renders it: identity, liveness, and the two
    flags the reap decision turns on."""
    groups = _group_names(peer)
    protected = bool(groups & PROTECTED_GROUPS)
    return {
        "id": peer.get("id", ""),
        "name": peer.get("name") or peer.get("hostname", ""),
        "ip": peer.get("ip", ""),
        "connected": bool(peer.get("connected")),
        "last_seen": peer.get("last_seen"),
        "os": peer.get("os", ""),
        "groups": sorted(groups),
        "is_student": STUDENT_GROUP in groups and not protected,
        "is_protected": protected,
    }


def reapable(peers: list[dict]) -> list[dict]:
    """The peers a reap may delete: student peers that are offline, and
    nothing protected, ever."""
    out = []
    for peer in peers:
        info = classify(peer)
        if info["is_student"] and not info["connected"]:
            out.append(info)
    return out

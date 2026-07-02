"""The plugin-facing contract: base class, context, events, and the scoped
API client.

Sandboxing model: a plugin never receives a database session, the settings
object, or the secret store. Everything it may do flows through:

- ctx.providers  : register extension-point implementations
- ctx.api        : an in-process HTTP client bound to the plugin's own
                   service principal, so RBAC and scopes are enforced by
                   the exact same code path the UI and external tools hit
- ctx.config     : this plugin's declared config (secrets decrypted)
- ctx.log        : a namespaced logger
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass(frozen=True)
class Event:
    """Internal bus event; same envelope as webhooks (docs/public-api.md)."""

    type: str
    at: str
    data: dict


class RateLimitExceeded(RuntimeError):
    pass


def _run_coro(coro):
    """Run a coroutine from sync plugin code. Hooks execute in worker
    threads (no loop), so asyncio.run works; if a loop is somehow running
    in this thread, fall back to a fresh thread."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    result: dict[str, Any] = {}

    def runner() -> None:
        result["value"] = asyncio.run(coro)

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    t.join()
    return result["value"]


class ScopedApi:
    """In-process client for /api/v1, authenticated as the plugin's service
    principal (an OAuth client provisioned at enable time). Calls traverse
    the full FastAPI stack, so capability and scope checks apply exactly as
    they would for any external caller."""

    def __init__(
        self,
        client_id: str,
        owner_id: str,
        scopes: list[str],
        rate_per_minute: int = 120,
    ) -> None:
        self._client_id = client_id
        self._owner_id = owner_id
        self._scopes = scopes
        self._rate = rate_per_minute
        self._calls: deque[float] = deque()

    def _check_rate(self) -> None:
        now = time.monotonic()
        while self._calls and now - self._calls[0] > 60:
            self._calls.popleft()
        if len(self._calls) >= self._rate:
            raise RateLimitExceeded(
                f"plugin exceeded {self._rate} API calls per minute"
            )
        self._calls.append(now)

    def _token(self) -> str:
        from ..security import create_client_token

        return create_client_token(self._client_id, self._owner_id, self._scopes)

    def request(
        self,
        method: str,
        path: str,
        json: dict | None = None,
        params: dict | None = None,
    ) -> httpx.Response:
        self._check_rate()

        async def _call() -> httpx.Response:
            from ..main import app

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://plugins.palestrix.internal"
            ) as client:
                return await client.request(
                    method,
                    path,
                    json=json,
                    params=params,
                    headers={"Authorization": f"Bearer {self._token()}"},
                )

        return _run_coro(_call())

    def get(self, path: str, params: dict | None = None) -> httpx.Response:
        return self.request("GET", path, params=params)

    def post(self, path: str, json: dict | None = None) -> httpx.Response:
        return self.request("POST", path, json=json)

    def delete(self, path: str) -> httpx.Response:
        return self.request("DELETE", path)


class ProviderFacade:
    """The one extension point exposed in Phase 2b. Registration is tagged
    with the owning plugin id so providers deactivate with the plugin."""

    def __init__(self, plugin_id: str) -> None:
        self._plugin_id = plugin_id

    def register_instance_provider(self, provider) -> None:
        from ..providers import register_provider

        register_provider(provider, owner_plugin=self._plugin_id)


@dataclass
class PluginContext:
    plugin_id: str
    scopes: frozenset[str]
    config: dict = field(default_factory=dict)
    providers: ProviderFacade | None = None
    log: logging.Logger = field(
        default_factory=lambda: logging.getLogger("palestrix.plugin")
    )
    api: ScopedApi | None = None  # set while the plugin is enabled


class Plugin:
    """Base class for server plugins. Override the hooks you need; every
    hook is called with exception isolation (a crash disables the plugin
    and is logged, it never takes the platform down)."""

    def on_register(self, ctx: PluginContext) -> None:
        """Discovery time. Declare extension points (providers) here."""

    def on_enable(self, ctx: PluginContext) -> None:
        """A superadmin enabled the plugin. Config and ctx.api are live."""

    def on_event(self, ctx: PluginContext, event: Event) -> None:
        """Internal event bus, same catalog as webhooks."""

    def on_disable(self, ctx: PluginContext) -> None:
        """Release resources; leave no background work running."""

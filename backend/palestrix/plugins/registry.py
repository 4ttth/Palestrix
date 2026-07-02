"""Plugin registry: discovery, enablement, and the safety rails.

Discovery paths:
1. Python entry points in the "palestrix.plugins" group (installed
   packages; the production mechanism).
2. Directories listed in PALESTRIX_PLUGIN_PATHS (development and tests):
   each directory holds plugin.toml plus the entry module as a .py file.

Safety rails implemented here:
- Contract version gate: unsupported [plugin].api is never activated.
- Scope validation: manifest scopes must be known platform scopes; on
  enable, the service principal gets exactly those scopes; scope
  escalation between versions requires explicit re-approval.
- Secret config values (manifest [config].secret) are Fernet-encrypted at
  rest and decrypted only into that plugin's context.
- Exception isolation: a crashing hook marks the plugin errored and
  disabled; it never propagates into the request that triggered it.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.metadata
import importlib.resources
import importlib.util
import logging
import secrets as pysecrets
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import providers
from ..config import get_settings
from ..models import OAuthClient, PluginRecord
from ..rbac import SCOPE_CAPABILITY
from ..security import sha256_hex
from .contract import Event, Plugin, PluginContext, ProviderFacade, ScopedApi
from .manifest import Manifest, ManifestError, parse_manifest

logger = logging.getLogger("palestrix.plugins")

_ENC_PREFIX = "enc:v1:"


class PluginError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code  # not_found | unsupported | config | scopes | hook


def _fernet() -> Fernet:
    key = hashlib.sha256(get_settings().secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_config(manifest: Manifest, config: dict) -> dict:
    out = dict(config)
    f = _fernet()
    for key in manifest.config_secret:
        if key in out and isinstance(out[key], str):
            out[key] = _ENC_PREFIX + f.encrypt(out[key].encode()).decode()
    return out


def decrypt_config(config: dict) -> dict:
    out = dict(config)
    f = _fernet()
    for key, value in out.items():
        if isinstance(value, str) and value.startswith(_ENC_PREFIX):
            try:
                out[key] = f.decrypt(value[len(_ENC_PREFIX):].encode()).decode()
            except InvalidToken:
                logger.warning("could not decrypt config key %s", key)
    return out


@dataclass
class LoadedPlugin:
    manifest: Manifest
    instance: Plugin
    ctx: PluginContext
    source: str  # "entry-point" | path
    state: str = "discovered"  # discovered | enabled | unsupported | error
    error: str | None = None

    @property
    def enabled(self) -> bool:
        return self.state == "enabled"


class PluginRegistry:
    def __init__(self) -> None:
        self.plugins: dict[str, LoadedPlugin] = {}

    # -- discovery -------------------------------------------------------------

    def discover(self) -> None:
        for ep in importlib.metadata.entry_points(group="palestrix.plugins"):
            try:
                cls = ep.load()
                package = cls.__module__.split(".")[0]
                text = (
                    importlib.resources.files(package)
                    .joinpath("plugin.toml")
                    .read_text(encoding="utf-8")
                )
                self._register(parse_manifest(text), cls(), source="entry-point")
            except Exception as exc:  # a broken package must not stop boot
                logger.warning("skipping entry point %s: %s", ep.name, exc)

        for raw in get_settings().plugin_paths.split(","):
            path = raw.strip()
            if path:
                try:
                    self.load_from_path(Path(path))
                except Exception as exc:
                    logger.warning("skipping plugin path %s: %s", path, exc)

    def load_from_path(self, path: Path) -> LoadedPlugin:
        manifest = parse_manifest((path / "plugin.toml").read_text(encoding="utf-8"))
        module_name, class_name = manifest.entry.split(":")
        module_file = path / f"{module_name}.py"
        if not module_file.exists():
            raise ManifestError(f"entry module {module_file} not found")
        spec = importlib.util.spec_from_file_location(
            f"palestrix_plugin_{manifest.id.replace('-', '_')}", module_file
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        cls = getattr(module, class_name)
        return self._register(manifest, cls(), source=str(path))

    def _register(
        self, manifest: Manifest, instance: Plugin, source: str
    ) -> LoadedPlugin:
        ctx = PluginContext(
            plugin_id=manifest.id,
            scopes=frozenset(manifest.scopes),
            providers=ProviderFacade(manifest.id),
            log=logging.getLogger(f"palestrix.plugin.{manifest.id}"),
        )
        loaded = LoadedPlugin(
            manifest=manifest, instance=instance, ctx=ctx, source=source
        )
        if not manifest.api_supported:
            loaded.state = "unsupported"
            loaded.error = f"plugin contract api {manifest.api} is not supported"
        else:
            try:
                instance.on_register(ctx)
            except Exception as exc:
                loaded.state = "error"
                loaded.error = f"on_register crashed: {exc}"
                logger.warning("plugin %s failed to register: %s", manifest.id, exc)
        self.plugins[manifest.id] = loaded
        return loaded

    # -- enablement ------------------------------------------------------------

    def _get_or_404(self, plugin_id: str) -> LoadedPlugin:
        loaded = self.plugins.get(plugin_id)
        if loaded is None:
            raise PluginError("not_found", f"no discovered plugin '{plugin_id}'")
        return loaded

    def enable(
        self,
        db: Session,
        plugin_id: str,
        config: dict,
        granted_by_user_id: str,
        approve_scopes: list[str] | None = None,
    ) -> LoadedPlugin:
        loaded = self._get_or_404(plugin_id)
        manifest = loaded.manifest

        if loaded.state == "unsupported":
            raise PluginError("unsupported", loaded.error or "unsupported contract")

        unknown_scopes = set(manifest.scopes) - set(SCOPE_CAPABILITY)
        if unknown_scopes:
            raise PluginError(
                "scopes", f"manifest requests unknown scopes: {sorted(unknown_scopes)}"
            )

        missing = [k for k in manifest.config_required if k not in config]
        if missing:
            raise PluginError("config", f"missing required config: {missing}")
        undeclared = set(config) - set(manifest.config_required) - set(
            manifest.config_optional
        )
        if undeclared:
            raise PluginError(
                "config", f"config keys not declared in the manifest: {sorted(undeclared)}"
            )

        record = db.get(PluginRecord, plugin_id)

        # Scope escalation between versions needs explicit re-approval.
        if record is not None:
            escalated = set(manifest.scopes) - set(record.granted_scopes or [])
            if escalated and set(approve_scopes or []) < escalated:
                raise PluginError(
                    "scopes",
                    "this version requests new scopes that need re-approval: "
                    f"{sorted(escalated)} (pass them in approve_scopes)",
                )

        client = None
        if record is not None and record.oauth_client_id:
            client = db.scalar(
                select(OAuthClient).where(
                    OAuthClient.client_id == record.oauth_client_id
                )
            )
        if client is None:
            client = OAuthClient(
                client_id=f"plugin-{plugin_id}",
                secret_hash=sha256_hex(pysecrets.token_urlsafe(32)),  # unusable
                owner_id=granted_by_user_id,
                name=f"plugin service principal: {manifest.name}",
                scopes=list(manifest.scopes),
            )
            db.add(client)
            db.flush()
        else:
            client.scopes = list(manifest.scopes)
            client.owner_id = granted_by_user_id

        if record is None:
            record = PluginRecord(plugin_id=plugin_id)
            db.add(record)
        record.version = manifest.version
        record.enabled = True
        record.granted_scopes = list(manifest.scopes)
        record.config = encrypt_config(manifest, config)
        record.oauth_client_id = client.client_id
        record.error = None
        db.flush()

        self._activate(loaded, record, client)
        db.commit()
        return loaded

    def _activate(
        self, loaded: LoadedPlugin, record: PluginRecord, client: OAuthClient
    ) -> None:
        loaded.ctx.config = decrypt_config(record.config or {})
        loaded.ctx.api = ScopedApi(
            client_id=client.client_id,
            owner_id=client.owner_id,
            scopes=list(record.granted_scopes or []),
        )
        try:
            loaded.instance.on_enable(loaded.ctx)
        except Exception as exc:
            loaded.state = "error"
            loaded.error = f"on_enable crashed: {exc}"
            loaded.ctx.api = None
            record.enabled = False
            record.error = loaded.error
            raise PluginError("hook", loaded.error) from exc
        loaded.state = "enabled"
        loaded.error = None

    def disable(self, db: Session, plugin_id: str) -> LoadedPlugin:
        loaded = self._get_or_404(plugin_id)
        record = db.get(PluginRecord, plugin_id)
        if record is not None:
            record.enabled = False
        try:
            loaded.instance.on_disable(loaded.ctx)
        except Exception as exc:
            logger.warning("plugin %s on_disable crashed: %s", plugin_id, exc)
        loaded.ctx.api = None
        loaded.state = "discovered"
        db.commit()
        return loaded

    def restore(self, db: Session) -> None:
        """At startup, re-activate plugins the database says are enabled."""
        records = db.scalars(
            select(PluginRecord).where(PluginRecord.enabled.is_(True))
        ).all()
        for record in records:
            loaded = self.plugins.get(record.plugin_id)
            if loaded is None or loaded.state == "unsupported":
                record.enabled = False
                record.error = "plugin not discovered at startup"
                continue
            client = db.scalar(
                select(OAuthClient).where(
                    OAuthClient.client_id == record.oauth_client_id
                )
            )
            if client is None:
                record.enabled = False
                record.error = "service principal missing"
                continue
            try:
                self._activate(loaded, record, client)
            except PluginError:
                pass  # recorded on the row by _activate
        db.commit()

    # -- events ----------------------------------------------------------------

    def notify(self, event: Event) -> None:
        """Fan an event out to enabled plugins with crash isolation."""
        for loaded in list(self.plugins.values()):
            if not loaded.enabled:
                continue
            try:
                loaded.instance.on_event(loaded.ctx, event)
            except Exception as exc:
                loaded.state = "error"
                loaded.error = f"on_event crashed: {exc}"
                loaded.ctx.api = None
                logger.warning(
                    "plugin %s disabled after on_event crash: %s",
                    loaded.manifest.id,
                    exc,
                )
                self._persist_error(loaded)

    def _persist_error(self, loaded: LoadedPlugin) -> None:
        from ..db import SessionLocal

        db = SessionLocal()
        try:
            record = db.get(PluginRecord, loaded.manifest.id)
            if record is not None:
                record.enabled = False
                record.error = loaded.error
                db.commit()
        finally:
            db.close()

    def is_enabled(self, plugin_id: str) -> bool:
        loaded = self.plugins.get(plugin_id)
        return bool(loaded and loaded.enabled)


registry = PluginRegistry()
providers.set_enablement_checker(registry.is_enabled)

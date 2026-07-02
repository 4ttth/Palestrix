"""plugin.toml parsing and validation. The manifest is the plugin's public
declaration: identity, contract version, entry point, requested scopes, and
declared configuration (with secret keys named explicitly)."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field

SUPPORTED_API_MAJORS = {"1"}

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
_ENTRY_RE = re.compile(r"^[A-Za-z_][\w.]*:[A-Za-z_]\w*$")


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class Manifest:
    id: str
    name: str
    version: str
    api: str
    entry: str  # "package.module:ClassName"
    scopes: tuple[str, ...] = ()
    config_required: tuple[str, ...] = ()
    config_optional: tuple[str, ...] = ()
    config_secret: tuple[str, ...] = ()

    @property
    def api_supported(self) -> bool:
        return self.api in SUPPORTED_API_MAJORS


def parse_manifest(text: str) -> Manifest:
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(f"plugin.toml is not valid TOML: {exc}") from exc

    plugin = raw.get("plugin")
    if not isinstance(plugin, dict):
        raise ManifestError("missing [plugin] table")
    for key in ("id", "name", "version", "api", "entry"):
        if not isinstance(plugin.get(key), str) or not plugin[key]:
            raise ManifestError(f"[plugin].{key} is required and must be a string")
    if not _ID_RE.match(plugin["id"]):
        raise ManifestError("[plugin].id must be kebab-case, 2-64 chars")
    if not _ENTRY_RE.match(plugin["entry"]):
        raise ManifestError('[plugin].entry must look like "package.module:ClassName"')

    permissions = raw.get("permissions", {})
    scopes = permissions.get("scopes", [])
    config = raw.get("config", {})
    required = config.get("required", [])
    optional = config.get("optional", [])
    secret = config.get("secret", [])
    for name, value in (
        ("permissions.scopes", scopes),
        ("config.required", required),
        ("config.optional", optional),
        ("config.secret", secret),
    ):
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ManifestError(f"[{name}] must be a list of strings")

    declared = set(required) | set(optional)
    unknown_secret = set(secret) - declared
    if unknown_secret:
        raise ManifestError(
            f"config.secret names undeclared keys: {sorted(unknown_secret)}"
        )

    return Manifest(
        id=plugin["id"],
        name=plugin["name"],
        version=plugin["version"],
        api=plugin["api"],
        entry=plugin["entry"],
        scopes=tuple(scopes),
        config_required=tuple(required),
        config_optional=tuple(optional),
        config_secret=tuple(secret),
    )

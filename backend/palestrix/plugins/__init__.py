"""PalestrIX plugin framework (Phase 2b).

Public contract for plugin authors:

    from palestrix.plugins import Plugin, PluginContext, Event

See docs/plugin-development.md for the authoring guide and
plugins/palestrix-provider-demo in the repository root for the worked
reference plugin.
"""

from .contract import Event, Plugin, PluginContext, RateLimitExceeded, ScopedApi
from .manifest import Manifest, ManifestError, parse_manifest

__all__ = [
    "Event",
    "Manifest",
    "ManifestError",
    "Plugin",
    "PluginContext",
    "RateLimitExceeded",
    "ScopedApi",
    "parse_manifest",
]

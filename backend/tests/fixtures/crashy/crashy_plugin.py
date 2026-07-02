"""Test fixture: a plugin whose on_event hook always crashes, used to prove
exception isolation (the platform survives; the plugin is disabled)."""

from palestrix.plugins import Plugin


class CrashyPlugin(Plugin):
    def on_event(self, ctx, event):
        raise RuntimeError("crashy plugin always crashes on events")

"""Test fixture: declares required config with a secret key, used to prove
config validation and encryption-at-rest."""

from palestrix.plugins import Plugin


class NeedyPlugin(Plugin):
    def on_enable(self, ctx):
        assert ctx.config["api_url"]
        assert ctx.config["api_token"]  # decrypted in the context

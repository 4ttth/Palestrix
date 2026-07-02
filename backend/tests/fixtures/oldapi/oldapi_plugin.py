"""Test fixture: declares an unsupported plugin contract version, used to
prove the registry's version gate."""

from palestrix.plugins import Plugin


class OldApiPlugin(Plugin):
    pass

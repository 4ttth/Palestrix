"""Reference PalestrIX plugin: the provider-authoring tutorial.

What it demonstrates:
- registering a new instance provider (lab kind "echo") in on_register
- reading declared config in on_enable
- calling the platform through the capability-scoped ctx.api client
- reacting to bus events in on_event

Everything a third-party provider plugin needs is shown here; a real one
would talk to its own backend (a cloud API, a badge farm, a device rack)
inside EchoProvider.provision/destroy.
"""

from palestrix.plugins import Event, Plugin, PluginContext


class EchoProvider:
    """Instant, in-registry-only provider. 'Provisioning' just echoes what a
    real adapter would do, which makes it ideal for CI and demos."""

    name = "echo"
    kinds = ("echo",)

    def provision(self, db, instance, template) -> None:
        from palestrix.models import InstanceState
        from palestrix.providers import add_log

        add_log(db, instance.id, f"echo: request accepted for {template.slug}")
        add_log(db, instance.id, "echo: no real resources are created by this provider")
        instance.node = "echo-plugin"
        instance.host = "127.0.0.1"
        instance.port = 7777
        instance.proto = "echo"
        instance.state = InstanceState.running
        add_log(db, instance.id, "echo: instance marked running", level="ok")

    def destroy(self, db, instance) -> None:
        from palestrix.providers import add_log

        add_log(db, instance.id, "echo: instance released", level="warn")


class ProviderDemoPlugin(Plugin):
    def on_register(self, ctx: PluginContext) -> None:
        ctx.providers.register_instance_provider(EchoProvider())

    def on_enable(self, ctx: PluginContext) -> None:
        banner = ctx.config.get("banner", "echo provider online")
        ctx.log.info("enabled: %s", banner)
        # Demonstrate the scoped client: this call is allowed by the
        # manifest's instances:read scope. Failure is non-fatal on purpose;
        # a plugin must stay enable-able when the API is briefly busy.
        try:
            resp = ctx.api.get("/api/v1/instances")
            ctx.log.info("scoped api check: %s instances visible", len(resp.json()))
        except Exception as exc:
            ctx.log.warning("scoped api check skipped: %s", exc)

    def on_event(self, ctx: PluginContext, event: Event) -> None:
        if event.type == "instance.expired":
            ctx.log.info(
                "echo provider noticed expiry of %s",
                event.data.get("instance_id"),
            )

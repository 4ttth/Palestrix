# Plugin Development Guide

PalestrIX has a modular plugin architecture so third-party developers can add
capabilities without forking core. Plugins extend the platform through
declared extension points and a stable, versioned contract; they never get
ambient access to core secrets or the database.

## What a plugin can add

| Extension point | Examples |
|---|---|
| Lab/challenge providers | A cloud-provider adapter, a hardware-badge lab type (implements the orchestration `InstanceProvider` interface) |
| Auth providers | An extra OIDC IdP, LDAP bridge |
| Gamification rules | Alternative earn curves, seasonal events, team scoring |
| Dashboard widgets | A "campus threat feed" tile, custom progress views |
| Community content types | Video walkthroughs, annotated pcaps |
| Scoring/grading strategies | Partial-credit flags, time-decayed points, rubric grading |

## Server plugins

Server plugins are Python packages discovered through the
`palestrix.plugins` entry-point group and loaded by the registry at startup
(and on enable, without restart, where the extension point allows it).

### Manifest

Every plugin ships `plugin.toml`:

```toml
[plugin]
id = "acme-badge-labs"            # unique, kebab-case
name = "Hardware Badge Labs"
version = "1.2.0"
api = "1"                          # plugin contract major version
entry = "acme_badge_labs.plugin:BadgeLabsPlugin"

[permissions]                      # capability scopes, least privilege
scopes = ["instances:launch", "instances:read", "webhooks:manage"]

[config]                           # declared config, rendered in admin UI
required = ["badge_gateway_url"]
optional = ["max_concurrent"]
```

### Lifecycle hooks

```python
from palestrix.plugins import Plugin, PluginContext

class BadgeLabsPlugin(Plugin):
    def on_register(self, ctx: PluginContext) -> None:
        """Called once at discovery. Declare extension points here."""
        ctx.providers.register_instance_provider("badge", BadgeProvider(ctx))

    def on_enable(self, ctx: PluginContext) -> None:
        """Called when a superadmin enables the plugin. Config is available."""
        self.gateway = ctx.config["badge_gateway_url"]

    def on_event(self, ctx: PluginContext, event: Event) -> None:
        """Internal event bus, same events as webhooks (public-api.md)."""
        if event.type == "instance.expired":
            ...

    def on_disable(self, ctx: PluginContext) -> None:
        """Release resources. Must leave no background work running."""
```

### Sandboxing and capability scoping

- A plugin's `PluginContext` exposes **only** the API client bound to its
  granted scopes; there is no ORM/session handle, no settings object, no
  secret store. If a plugin needs data, it calls the same `/api/v1` the UI
  calls, as its own service principal.
- Declared scopes are shown to the superadmin at enable time; scope
  escalation requires re-approval.
- Plugin config marked secret is stored encrypted and injected only into
  that plugin's context.
- Misbehavior containment: per-plugin exception isolation (a crashing hook
  is disabled and alarmed, never takes the API down), per-plugin rate limits
  on the internal client.

## UI plugins

UI plugins are lazy-loaded Next.js modules that mount into declared slots.
A UI plugin is a folder under `plugins/` whose `palestrix.ui-plugin.ts`
default-exports a manifest:

```ts
// palestrix.ui-plugin.ts
import type { UiPluginManifest } from "@palestrix/plugin-sdk";

export default {
  id: "acme-badge-labs",
  slots: {
    "dashboard.widgets": () => import("./widgets/BadgeStatus"),
    "lab.sidebar": () => import("./panels/BadgePinout"),
  },
} satisfies UiPluginManifest;
```

- Slots are the stable contract: `dashboard.widgets`, `lab.sidebar`,
  `community.content-renderers`, `admin.settings-panels` (list grows
  additively). Core pages render `<PluginSlot slot="…" />`
  (`components/plugins/PluginSlot.tsx`); every installed plugin registered
  for that slot mounts there.
- Installation mirrors server-side entry-point discovery: the manifest is
  listed in `lib/plugins/registry.ts`. Slot components stay behind the
  manifest's dynamic `import()`, so a plugin ships as lazy, code-split
  chunks fetched only when its slot actually renders.
- Slot components receive typed, read-only props and a scoped fetcher
  (`api.get`, GET-only over the same `/api/v1` contract; in the template
  phase it replays the sample data the core screens render). They cannot
  import core internals: `@palestrix/plugin-sdk` (`lib/plugins/sdk.ts`) is
  the module boundary, and it re-exports the theme-locked primitives
  (`Card`, `Badge`, `Avatar`, …) plugins may use.
- Crash isolation, mirrored from the server registry: a slot component
  that throws collapses to a small errored tile plus a console warning; it
  never takes the page down.
- Must follow the locked theme: tokens only, no custom accent colors.

## Versioning

The plugin contract carries a major version (`api = "1"`). Core supports the
current and previous major for one release cycle. The registry refuses to
enable a plugin whose contract major is unsupported, with a clear error.

## Reference plugins (shipped with Phase 2b)

1. **`plugins/palestrix-provider-demo`**: a fake instance provider that
   "provisions" instantly; used in CI and as the provider-authoring
   tutorial. Exercised end to end by `backend/tests/test_plugins.py`.
2. **`plugins/palestrix-widget-firstblood`**: a dashboard widget rendering
   the first-blood feed through the scoped fetcher; the UI-slot tutorial.
   Mounted on `/dashboard` via the `dashboard.widgets` slot. (Phase 5
   upgrades its one-shot fetch to the `flag.captured` SSE stream.)

Both live in the main repo under `plugins/` and double as contract tests.

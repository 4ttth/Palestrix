/*
 * Reference UI plugin: the UI-slot tutorial (docs/plugin-development.md).
 *
 * The manifest is the whole integration surface: declare an id and point
 * slots at lazy chunks. The host mounts them wherever a page renders
 * <PluginSlot slot="…" />; the plugin never touches core.
 */

import type { UiPluginManifest } from "@palestrix/plugin-sdk";

export default {
  id: "widget-firstblood",
  slots: {
    "dashboard.widgets": () => import("./widgets/FirstBloodFeed"),
  },
} satisfies UiPluginManifest;

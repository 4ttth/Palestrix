/*
 * UI plugin registry: which UI plugins are installed and what they mount.
 *
 * Manifests are imported statically — the UI equivalent of server-side
 * entry-point discovery; installing a UI plugin means adding its manifest
 * here. Slot components stay behind each manifest's dynamic import(), so
 * a plugin ships as lazy, code-split chunks that load only when a page
 * actually renders its slot.
 */

import firstblood from "@/plugins/palestrix-widget-firstblood/palestrix.ui-plugin";
import type { UiPluginManifest, UiSlotId } from "./sdk";

const installed: UiPluginManifest[] = [firstblood];

export type SlotEntry<S extends UiSlotId> = {
  pluginId: string;
  load: NonNullable<UiPluginManifest["slots"][S]>;
};

export function slotEntries<S extends UiSlotId>(slot: S): SlotEntry<S>[] {
  return installed.flatMap((plugin) => {
    const load = plugin.slots[slot];
    return load ? [{ pluginId: plugin.id, load }] : [];
  });
}

/*
 * The PalestrIX UI plugin SDK: the single import surface for UI plugins,
 * aliased as `@palestrix/plugin-sdk` in tsconfig. This module is the
 * boundary from docs/plugin-development.md — plugins compile against these
 * types and the re-exported theme-locked primitives, never core paths.
 */

import type * as React from "react";

/** Slots a UI plugin can mount into. The list only ever grows. */
export type UiSlotId =
  | "dashboard.widgets"
  | "lab.sidebar"
  | "community.content-renderers"
  | "admin.settings-panels";

/** The signed-in user as slots see them: read-only, no tokens, no email. */
export type SlotViewer = Readonly<{
  handle: string;
  name: string;
  role: "Student" | "Teacher" | "Admin" | "Superadmin";
}>;

/** Host-provided props per slot. All read-only. */
export type SlotProps = {
  "dashboard.widgets": { viewer: SlotViewer };
  "lab.sidebar": { viewer: SlotViewer; instanceId: string };
  "community.content-renderers": { viewer: SlotViewer; contentId: string };
  "admin.settings-panels": { viewer: SlotViewer };
};

/**
 * The scoped fetcher: GET-only over the public /api/v1 contract
 * (docs/public-api.md) — the UI mirror of the server-side capability-scoped
 * client. In the template phase it replays the same sample data the core
 * screens render; the live wiring phase points it at the real API without
 * changing this signature.
 */
export type ScopedApi = {
  get<T = unknown>(path: `/api/v1/${string}`): Promise<T>;
};

/** Every slot component gets its slot's props plus the scoped api client. */
export type UiSlotComponentProps<S extends UiSlotId> = Readonly<
  SlotProps[S]
> & {
  api: ScopedApi;
};

export type UiSlotModule<S extends UiSlotId> = {
  default: React.ComponentType<UiSlotComponentProps<S>>;
};

/**
 * The `palestrix.ui-plugin.ts` default export. Slot values are dynamic
 * `import()`s so every slot component stays a lazy, code-split chunk that
 * loads only when its slot renders.
 */
export type UiPluginManifest = {
  /** Same rules as the server manifest id: unique, kebab-case. */
  id: string;
  slots: { [S in UiSlotId]?: () => Promise<UiSlotModule<S>> };
};

/* Theme-locked primitives (tokens come from components/theme/tokens.css).
 * Re-exported so plugins never import core component paths directly. */
export {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
export { Badge } from "@/components/ui/badge";
export { Avatar } from "@/components/ui/avatar";

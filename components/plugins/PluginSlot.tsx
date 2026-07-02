"use client";

import * as React from "react";
import { createScopedApi } from "@/lib/plugins/api";
import { slotEntries } from "@/lib/plugins/registry";
import type { ScopedApi, SlotProps, UiSlotId } from "@/lib/plugins/sdk";

/*
 * <PluginSlot slot="…" …props /> renders every installed UI plugin that
 * registered for the slot. The safety rails mirror the server registry
 * (backend/palestrix/plugins/registry.py):
 *
 * - lazy loading: a plugin's chunk is fetched only when its slot renders;
 * - crash isolation: a throwing slot component collapses to a small
 *   errored tile plus a console warning — it never takes the page down;
 * - scoping: plugins receive read-only props and the scoped api client,
 *   nothing else.
 */

/* The cache is heterogenous (one entry per plugin×slot, each with its own
 * prop type), so entries are stored type-erased; PluginSlot's signature
 * keeps the outside statically typed. */
type AnySlotComponent = React.LazyExoticComponent<
  React.ComponentType<Record<string, unknown>>
>;
const lazyCache = new Map<string, AnySlotComponent>();
const apiCache = new Map<string, ScopedApi>();

class SlotErrorBoundary extends React.Component<
  { pluginId: string; children: React.ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    console.warn(
      `ui plugin ${this.props.pluginId} crashed and was isolated:`,
      error
    );
  }

  render() {
    if (this.state.failed) {
      return (
        <div className="rounded-(--radius-card) border border-dashed border-border px-4 py-3 text-xs text-muted">
          Widget <span className="font-mono">{this.props.pluginId}</span>{" "}
          failed to render and was disabled for this view.
        </div>
      );
    }
    return this.props.children;
  }
}

export function PluginSlot<S extends UiSlotId>({
  slot,
  ...props
}: { slot: S } & SlotProps[S]) {
  const entries = slotEntries(slot);
  if (entries.length === 0) return null;

  return (
    <>
      {entries.map(({ pluginId, load }) => {
        const key = `${pluginId}:${slot}`;
        let Widget = lazyCache.get(key);
        if (!Widget) {
          Widget = React.lazy(load) as unknown as AnySlotComponent;
          lazyCache.set(key, Widget);
        }
        let api = apiCache.get(pluginId);
        if (!api) {
          api = createScopedApi(pluginId);
          apiCache.set(pluginId, api);
        }
        const widgetProps = { ...props, api } as Record<string, unknown>;
        return (
          <SlotErrorBoundary key={key} pluginId={pluginId}>
            <React.Suspense
              fallback={
                <div
                  aria-hidden
                  className="h-24 animate-pulse rounded-(--radius-card) border border-border bg-surface-2/60"
                />
              }
            >
              <Widget {...widgetProps} />
            </React.Suspense>
          </SlotErrorBoundary>
        );
      })}
    </>
  );
}

/*
 * The scoped fetcher handed to UI plugin slots.
 *
 * Template phase: GETs resolve from the same sample data the core screens
 * render (lib/mock.ts), keyed by real /api/v1 routes with wire-format
 * shapes (backend/palestrix/schemas.py, snake_case), so plugins are
 * authored against the live contract from day one. The live wiring phase
 * swaps the table lookup for fetch() with session credentials; the
 * ScopedApi signature does not change.
 */

import { challenges } from "@/lib/mock";
import type { ScopedApi } from "./sdk";

/** Sample /api/v1 responses, keyed by exact GET path. */
const SAMPLE_ROUTES: Record<string, unknown> = {
  "/api/v1/compete/events": [
    {
      id: "clctf-2026",
      title: "CLCTF 2026 qualifiers",
      starts_at: "2026-06-23T09:00:00+08:00",
      ends_at: "2026-07-24T18:00:00+08:00",
      tenant_id: "clctf-open",
    },
  ],
  "/api/v1/compete/events/clctf-2026/challenges": challenges.map((c) => ({
    id: c.id,
    event_id: "clctf-2026",
    title: c.title,
    category: c.category,
    points: c.points,
    solves: c.solves,
    first_blood: c.firstBlood,
  })),
};

export function createScopedApi(pluginId: string): ScopedApi {
  return {
    get<T>(path: `/api/v1/${string}`): Promise<T> {
      const hit = SAMPLE_ROUTES[path];
      if (hit === undefined) {
        return Promise.reject(
          new Error(`scoped api (${pluginId}): no sample data for GET ${path}`)
        );
      }
      return Promise.resolve(hit as T);
    },
  };
}

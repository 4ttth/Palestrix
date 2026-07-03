/*
 * The scoped fetcher handed to UI plugin slots.
 *
 * Live wiring (Phase 5): GETs go to the real /api/v1 with the viewer's
 * session credentials, exactly as the template phase promised — the
 * ScopedApi signature is unchanged, so plugins authored against the sample
 * data work against the live API as-is. Still GET-only: UI plugins read
 * the public contract; they never mutate on the viewer's behalf.
 */

import { api } from "@/lib/api/client";
import type { ScopedApi } from "./sdk";

export function createScopedApi(pluginId: string): ScopedApi {
  return {
    get<T>(path: `/api/v1/${string}`): Promise<T> {
      return api.get<T>(path).catch((err) => {
        // Tag the failure so a crashing widget's console line names it.
        throw new Error(`scoped api (${pluginId}): GET ${path} failed: ${err}`);
      });
    },
  };
}

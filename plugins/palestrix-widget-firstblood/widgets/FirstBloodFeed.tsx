"use client";

/*
 * Reference dashboard widget: the first-blood feed, authored exactly the
 * way a third-party widget would be.
 *
 * What it demonstrates:
 * - importing only from @palestrix/plugin-sdk (slot prop types plus the
 *   theme-locked primitives); the widget has no path into core internals
 * - reading the platform through the scoped api client, against the real
 *   /api/v1/compete contract (docs/public-api.md)
 * - the locked theme: tokens only, no custom accent colors
 *
 * "Streaming": Phase 5 (live surfaces) upgrades the one-shot fetch to the
 * flag.captured SSE feed; the component contract stays the same.
 */

import * as React from "react";
import { Drop } from "@phosphor-icons/react";
import {
  Avatar,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  type UiSlotComponentProps,
} from "@palestrix/plugin-sdk";

/* Wire shapes from the public contract (snake_case, like the API). */
type CtfEvent = { id: string; title: string };
type Challenge = {
  id: string;
  title: string;
  category: string;
  points: number;
  solves: number;
  first_blood: string | null;
};
type Blooded = Challenge & { first_blood: string };

type Feed =
  | { state: "loading" }
  | { state: "unavailable" }
  | { state: "ready"; rows: Blooded[] };

export default function FirstBloodFeed({
  api,
}: UiSlotComponentProps<"dashboard.widgets">) {
  const [feed, setFeed] = React.useState<Feed>({ state: "loading" });

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      const events = await api.get<CtfEvent[]>("/api/v1/compete/events");
      const event = events[0];
      const challenges = event
        ? await api.get<Challenge[]>(
            `/api/v1/compete/events/${event.id}/challenges`
          )
        : [];
      const rows = challenges
        .filter((c): c is Blooded => Boolean(c.first_blood))
        // Rarest solves first: those first bloods were hardest won.
        .sort((a, b) => a.solves - b.solves)
        .slice(0, 4);
      if (!cancelled) setFeed({ state: "ready", rows });
    })().catch(() => {
      if (!cancelled) setFeed({ state: "unavailable" });
    });
    return () => {
      cancelled = true;
    };
  }, [api]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Drop size={15} weight="fill" className="text-expired" />
          First bloods
        </CardTitle>
      </CardHeader>
      <CardContent>
        {feed.state === "loading" && (
          <p className="text-xs text-muted">Loading the feed…</p>
        )}
        {feed.state === "unavailable" && (
          <p className="text-xs text-muted">The feed is unavailable.</p>
        )}
        {feed.state === "ready" &&
          (feed.rows.length === 0 ? (
            <p className="text-xs text-muted">
              No first bloods yet. Be the first.
            </p>
          ) : (
            <ul className="space-y-3">
              {feed.rows.map((c) => (
                <li key={c.id} className="flex items-center gap-3 text-sm">
                  <Avatar handle={c.first_blood} size="sm" />
                  <span className="min-w-0 flex-1 truncate">
                    <span className="font-mono text-[13px]">
                      {c.first_blood}
                    </span>{" "}
                    <span className="text-muted">on</span> {c.title}
                  </span>
                  <span className="font-mono text-xs tabular-nums text-muted">
                    {c.points}
                  </span>
                </li>
              ))}
            </ul>
          ))}
      </CardContent>
    </Card>
  );
}

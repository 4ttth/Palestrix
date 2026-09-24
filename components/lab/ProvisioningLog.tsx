"use client";

/*
 * Real provisioning progress, not a fake bar.
 *
 * Live mode (Phase 5): pass `instanceId` and the component follows the
 * orchestration worker's SSE endpoint
 * (GET /api/v1/instances/{id}/logs/stream) through lib/api/stream.ts —
 * fetch-based, because EventSource cannot carry the Authorization header.
 * The stream replays every line so far, follows while provisioning, and
 * closes with a state event once the instance settles (`onSettled`).
 *
 * Replay mode: pass `lines` (sample data) and the component replays them at
 * a readable cadence — kept for template/docs surfaces. Under
 * prefers-reduced-motion the full log renders at once.
 */

import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "motion/react";
import { streamInstanceLogs } from "@/lib/api/stream";
import type { InstanceState } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export type LogLine = {
  t: string;
  msg: string;
  level: "info" | "ok" | "warn";
};

const levelClass: Record<LogLine["level"], string> = {
  info: "text-muted",
  ok: "text-running",
  warn: "text-palestras",
};

/** "2026-07-03T09:14:02+00:00" -> local "09:14:02"; passthrough otherwise. */
function clockOf(t: string): string {
  const d = new Date(t);
  if (Number.isNaN(d.getTime())) return t;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

// Stable default. An inline `= []` default is a NEW array every render, and
// it sat in the effect dependencies below: every render restarted the effect,
// whose setVisible([]) caused the next render — an infinite loop that
// aborted/reopened the SSE stream nonstop, starving route navigation on
// /labs/* and hammering the API with connections.
const NO_LINES: LogLine[] = [];

export function ProvisioningLog({
  lines = NO_LINES,
  instanceId,
  onSettled,
  replay = true,
  className,
}: {
  lines?: LogLine[];
  instanceId?: string;
  /** Called once when the live stream closes with the settled state. */
  onSettled?: (state: InstanceState | "unknown") => void;
  replay?: boolean;
  className?: string;
}) {
  const reduce = useReducedMotion();
  const [visible, setVisible] = useState<LogLine[]>(
    replay && !reduce && !instanceId ? [] : lines
  );
  const [streamError, setStreamError] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const settledRef = useRef(onSettled);
  settledRef.current = onSettled;

  // Live mode: exactly one stream per instance. Nothing else may restart
  // this effect — re-running it aborts and reopens the SSE fetch.
  useEffect(() => {
    if (!instanceId) return;
    setVisible([]);
    setStreamError(false);
    return streamInstanceLogs(instanceId, {
      onLine: (line) => setVisible((v) => [...v, line as LogLine]),
      onState: (state) => settledRef.current?.(state),
      onError: () => setStreamError(true),
    });
  }, [instanceId]);

  // Replay mode: sample lines on template/docs surfaces.
  useEffect(() => {
    if (instanceId) return;

    if (!replay || reduce) {
      setVisible(lines);
      return;
    }

    let i = 0;
    setVisible([]);
    const id = setInterval(() => {
      i += 1;
      setVisible(lines.slice(0, i));
      if (i >= lines.length) clearInterval(id);
    }, 420);
    return () => clearInterval(id);
  }, [instanceId, replay, reduce, lines]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [visible]);

  return (
    <div
      ref={scrollRef}
      role="log"
      aria-live="polite"
      className={cn(
        "max-h-64 overflow-y-auto rounded-(--radius-input) border border-border bg-surface-2/60 p-3 font-mono text-xs leading-relaxed",
        className
      )}
    >
      {visible.length === 0 ? (
        <p className={cn("text-muted", !streamError && "plx-breathe")}>
          {streamError
            ? "log stream unavailable; reload to retry"
            : "waiting for orchestration worker..."}
        </p>
      ) : (
        <ol>
          {visible.map((line, i) => (
            /* Each line fades in as it arrives. Without this the log
               jumps by a row and the eye has to re-find its place; the
               entrance is what makes a new line read as new. */
            <li key={`${line.t}-${i}`} className="plx-fade flex gap-3">
              <span className="shrink-0 text-muted/70">{clockOf(line.t)}</span>
              <span className={levelClass[line.level] ?? "text-muted"}>
                {line.msg}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

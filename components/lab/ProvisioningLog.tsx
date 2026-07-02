"use client";

/*
 * Real provisioning progress, not a fake bar.
 *
 * Contract (Phase 4): pass `streamUrl` and the component subscribes to the
 * orchestration worker's Server-Sent Events endpoint
 * (GET /api/v1/instances/{id}/logs/stream) and appends real Proxmox/Docker
 * spin-up lines as they happen.
 *
 * Template mode (Phase 1): pass `lines` (sample data, marked mock in
 * lib/mock.ts) and the component replays them at a readable cadence.
 * Under prefers-reduced-motion the full log renders at once.
 */

import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "motion/react";
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

export function ProvisioningLog({
  lines = [],
  streamUrl,
  replay = true,
  className,
}: {
  lines?: LogLine[];
  streamUrl?: string;
  replay?: boolean;
  className?: string;
}) {
  const reduce = useReducedMotion();
  const [visible, setVisible] = useState<LogLine[]>(
    replay && !reduce && !streamUrl ? [] : lines
  );
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (streamUrl) {
      const es = new EventSource(streamUrl);
      es.onmessage = (e) => {
        try {
          const line = JSON.parse(e.data) as LogLine;
          setVisible((v) => [...v, line]);
        } catch {
          /* skip malformed frames */
        }
      };
      return () => es.close();
    }

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
  }, [streamUrl, replay, reduce, lines]);

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
        <p className="text-muted">waiting for orchestration worker...</p>
      ) : (
        <ol>
          {visible.map((line, i) => (
            <li key={`${line.t}-${i}`} className="flex gap-3">
              <span className="shrink-0 text-muted/70">{line.t}</span>
              <span className={levelClass[line.level]}>{line.msg}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

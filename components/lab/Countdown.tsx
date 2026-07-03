"use client";

/*
 * TTL countdown for ephemeral instances. Semantic state, not decoration:
 * it shows real remaining lifetime. Phase 5 feeds it the
 * server-authoritative expiry timestamp (`until`); the plain `seconds`
 * form remains for fixed spans. When `until` changes (an extend), the
 * clock re-syncs.
 */

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

function fmt(total: number) {
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return [h, m, s].map((n) => String(n).padStart(2, "0")).join(":");
}

function remaining(until: string): number {
  return Math.max(0, Math.floor((new Date(until).getTime() - Date.now()) / 1000));
}

export function Countdown({
  seconds,
  until,
  className,
}: {
  seconds?: number;
  /** ISO expiry timestamp; takes precedence over `seconds`. */
  until?: string;
  className?: string;
}) {
  const [left, setLeft] = useState(() =>
    until ? remaining(until) : (seconds ?? 0)
  );

  useEffect(() => {
    setLeft(until ? remaining(until) : (seconds ?? 0));
    const id = setInterval(
      () => setLeft((v) => (until ? remaining(until) : Math.max(0, v - 1))),
      1000
    );
    return () => clearInterval(id);
  }, [until, seconds]);

  const low = left < 600;

  return (
    <span
      className={cn(
        "font-mono tabular-nums",
        low ? "text-expired" : "text-foreground",
        className
      )}
      title="Time until the TTL reaper stops this instance"
    >
      {fmt(left)}
    </span>
  );
}

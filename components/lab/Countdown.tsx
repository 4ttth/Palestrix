"use client";

/*
 * TTL countdown for ephemeral instances. Semantic state, not decoration:
 * it shows real remaining lifetime. In Phase 1 templates it counts down
 * from a mock starting value; Phase 4 feeds it the server-authoritative
 * expiry timestamp.
 */

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

function fmt(total: number) {
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return [h, m, s].map((n) => String(n).padStart(2, "0")).join(":");
}

export function Countdown({
  seconds,
  className,
}: {
  seconds: number;
  className?: string;
}) {
  const [left, setLeft] = useState(seconds);

  useEffect(() => {
    const id = setInterval(() => setLeft((v) => Math.max(0, v - 1)), 1000);
    return () => clearInterval(id);
  }, []);

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

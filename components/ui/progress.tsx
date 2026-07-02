import * as React from "react";
import { cn } from "@/lib/utils";

/*
 * Course/module completion meter for the dense product surfaces.
 * Product UI only: never used as a decorative comparison visual on marketing pages.
 */
function Progress({
  value,
  className,
  label,
}: {
  value: number;
  className?: string;
  label?: string;
}) {
  const clamped = Math.min(100, Math.max(0, value));
  return (
    <div
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
      className={cn("h-1.5 w-full rounded-full bg-surface-2", className)}
    >
      <div
        className="h-full rounded-full bg-accent transition-[width] duration-300 ease-[var(--ease-swift)]"
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

export { Progress };

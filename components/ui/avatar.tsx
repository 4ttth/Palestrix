import * as React from "react";
import { cn } from "@/lib/utils";

/*
 * Handle-based initials avatar. PalestrIX is pseudonymous by design
 * (competitors go by handles), so avatars are styled initials with a
 * stable per-handle hue rather than face photos.
 */
const HUES = [212, 158, 262, 22, 340, 96, 190];

function hueFor(seed: string) {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) % 997;
  return HUES[h % HUES.length];
}

function Avatar({
  handle,
  size = "md",
  className,
}: {
  handle: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const hue = hueFor(handle);
  const initials = handle.replace(/[^a-zA-Z0-9]/g, "").slice(0, 2).toUpperCase();
  const sizes = {
    sm: "size-6 text-[10px]",
    md: "size-8 text-[11px]",
    lg: "size-12 text-sm",
  };
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full font-mono font-semibold",
        sizes[size],
        className
      )}
      style={{
        backgroundColor: `oklch(0.93 0.03 ${hue} / 0.9)`,
        color: `oklch(0.42 0.09 ${hue})`,
      }}
    >
      {initials}
    </span>
  );
}

export { Avatar };

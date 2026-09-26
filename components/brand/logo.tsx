import { cn } from "@/lib/utils";

/*
 * The PalestrIX mark, "The Keystone": a palaestra courtyard seen from above,
 * its top-right corner lifted out as a separate block. Geometry, meaning and
 * usage rules live in docs/brand.md; static files live in public/brand/.
 *
 * The wall takes currentColor (foreground by default) and the keystone takes
 * the theme accent, so the mark follows light/dark mode with no variants.
 * Every coordinate is a multiple of 4 on a 64 grid: render it at 16, 24, 32,
 * 48 px and it stays pixel-sharp.
 */
export function BrandMark({
  size = 24,
  className,
  title,
}: {
  size?: number;
  className?: string;
  title?: string;
}) {
  return (
    <svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      className={cn("shrink-0", className)}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      <path fill="currentColor" d="M28 4H4v56h56V36H48v12H16V16h12z" />
      <rect x="36" y="4" width="24" height="24" fill="var(--accent)" />
    </svg>
  );
}

/*
 * Mark + wordmark lockup. The mark is 1.25x the text size, snapped to the
 * 4px grid so it stays sharp; the gap is 0.4x the mark. "IX" keeps the accent
 * it always had.
 */
export function BrandLockup({
  textSize = 17,
  className,
}: {
  textSize?: number;
  className?: string;
}) {
  const mark = Math.round((textSize * 1.25) / 4) * 4;
  return (
    <span
      className={cn("inline-flex items-center font-semibold tracking-tight", className)}
      style={{ fontSize: textSize, gap: mark / 2.5 }}
    >
      <BrandMark size={mark} />
      <span>
        Palestr<span className="text-accent">IX</span>
      </span>
    </span>
  );
}

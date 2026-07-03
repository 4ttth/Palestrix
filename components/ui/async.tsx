/*
 * Shared async-state blocks so every live surface renders loading, failure,
 * and empty the same way. Loading is a quiet mono line, never a fake bar.
 */

import type { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";

export function Loading({ label = "loading", className }: { label?: string; className?: string }) {
  return (
    <p
      role="status"
      className={cn("py-4 text-center font-mono text-xs text-muted", className)}
    >
      {label}...
    </p>
  );
}

export function LoadFailed({
  error,
  retry,
  className,
}: {
  error: ApiError;
  retry?: () => void;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "rounded-(--radius-input) bg-expired-soft px-4 py-3 text-[13px] leading-relaxed text-expired",
        className
      )}
    >
      {error.message}
      {retry && (
        <button
          type="button"
          onClick={retry}
          className="ml-2 font-medium underline underline-offset-2"
        >
          Retry
        </button>
      )}
    </div>
  );
}

export function Empty({
  title,
  hint,
  children,
  className,
}: {
  title: string;
  hint?: string;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-(--radius-input) border border-dashed border-border px-6 py-10 text-center",
        className
      )}
    >
      <p className="text-sm font-medium">{title}</p>
      {hint && (
        <p className="mx-auto mt-1 max-w-[46ch] text-[13px] leading-relaxed text-muted">
          {hint}
        </p>
      )}
      {children}
    </div>
  );
}

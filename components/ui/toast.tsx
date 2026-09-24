"use client";

/*
 * Transient feedback, which the product had none of.
 *
 * Every mutating action in PalestrIX — launching a lab, publishing an
 * assignment, uploading an ISO, completing a module, submitting a flag —
 * either wrote a sentence into a panel-local <p> or said nothing at all.
 * Panel-local text has two failure modes that showed up constantly here:
 * it is invisible when the action was triggered from somewhere the user
 * has since scrolled past, and it is indistinguishable between "this
 * worked" and "this failed" until you read it.
 *
 * Design notes:
 *
 *  - Outcome is carried by icon, colour, and *motion* together, so it
 *    survives colour-blindness and a glance. Success pops once; failure
 *    shakes once. Neither repeats.
 *  - Errors do not auto-dismiss. A student who looks away must not lose
 *    the reason their lab refused to start. Successes clear themselves.
 *  - aria-live="polite" on an always-present region, so a screen reader
 *    announces the text without the region itself being a focus trap.
 *    Errors use role="alert" for assertive delivery.
 *  - The stack is capped and oldest-first-out: a failing retry loop must
 *    not bury the page.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  CheckCircle,
  Info,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

export type ToastTone = "success" | "error" | "info";

export interface Toast {
  id: number;
  tone: ToastTone;
  title: string;
  detail?: string;
  /** Milliseconds before self-dismissal; 0 pins it until dismissed. */
  ttl: number;
}

interface ToastApi {
  push: (t: Omit<Toast, "id" | "ttl"> & { ttl?: number }) => number;
  success: (title: string, detail?: string) => number;
  error: (title: string, detail?: string) => number;
  info: (title: string, detail?: string) => number;
  dismiss: (id: number) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

const MAX_VISIBLE = 4;
const DEFAULT_TTL = 4200;

/** Feedback for an action the user just took. Safe to call from anywhere
 * below <ToastProvider>; outside it, a no-op so a component can be reused
 * in a context (a plugin slot, a test) that has no provider. */
export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  const fallback = useMemo<ToastApi>(
    () => ({
      push: () => 0,
      success: () => 0,
      error: () => 0,
      info: () => 0,
      dismiss: () => {},
    }),
    []
  );
  return ctx ?? fallback;
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((all) => all.filter((t) => t.id !== id));
  }, []);

  const push = useCallback<ToastApi["push"]>((t) => {
    const id = nextId.current++;
    // Errors persist: losing the reason a lab refused to launch is worse
    // than a toast that outstays its welcome.
    const ttl = t.ttl ?? (t.tone === "error" ? 0 : DEFAULT_TTL);
    setToasts((all) => [...all, { ...t, id, ttl }].slice(-MAX_VISIBLE));
    return id;
  }, []);

  const api = useMemo<ToastApi>(
    () => ({
      push,
      dismiss,
      success: (title, detail) => push({ tone: "success", title, detail }),
      error: (title, detail) => push({ tone: "error", title, detail }),
      info: (title, detail) => push({ tone: "info", title, detail }),
    }),
    [push, dismiss]
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

const TONE: Record<
  ToastTone,
  { icon: typeof CheckCircle; ring: string; iconClass: string; enter: string }
> = {
  success: {
    icon: CheckCircle,
    ring: "border-l-running",
    iconClass: "text-running",
    enter: "plx-pop",
  },
  error: {
    icon: WarningCircle,
    ring: "border-l-danger",
    iconClass: "text-danger",
    enter: "plx-shake",
  },
  info: {
    icon: Info,
    ring: "border-l-accent",
    iconClass: "text-accent",
    enter: "plx-rise",
  },
};

function ToastViewport({
  toasts,
  onDismiss,
}: {
  toasts: Toast[];
  onDismiss: (id: number) => void;
}) {
  return (
    <div
      // Always mounted so assistive tech observes mutations rather than
      // the region itself appearing.
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center gap-2 p-4 sm:inset-x-auto sm:right-0 sm:top-0 sm:items-end sm:justify-start"
    >
      {toasts.map((toast) => (
        <ToastRow key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

function ToastRow({
  toast,
  onDismiss,
}: {
  toast: Toast;
  onDismiss: (id: number) => void;
}) {
  const tone = TONE[toast.tone];
  const Icon = tone.icon;
  const [leaving, setLeaving] = useState(false);

  const close = useCallback(() => {
    // Let the exit animation run before the row leaves the tree. The
    // timeout matches --duration-quick; under reduced motion the global
    // rule collapses the animation and this is an imperceptible delay.
    setLeaving(true);
    window.setTimeout(() => onDismiss(toast.id), 180);
  }, [onDismiss, toast.id]);

  useEffect(() => {
    if (!toast.ttl) return;
    const timer = window.setTimeout(close, toast.ttl);
    return () => window.clearTimeout(timer);
  }, [toast.ttl, close]);

  return (
    <div
      role={toast.tone === "error" ? "alert" : undefined}
      style={{
        animation: leaving
          ? "plx-slide-out-right var(--duration-quick) var(--ease-out-soft) both"
          : undefined,
      }}
      className={cn(
        "pointer-events-auto flex w-[min(24rem,calc(100vw-2rem))] items-start gap-3 rounded-(--radius-card) border border-l-4 border-border bg-surface px-4 py-3 shadow-lg",
        tone.ring,
        !leaving && tone.enter
      )}
    >
      <Icon
        weight="fill"
        className={cn("mt-0.5 size-5 shrink-0", tone.iconClass)}
        aria-hidden
      />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium leading-snug">{toast.title}</p>
        {toast.detail && (
          <p className="mt-0.5 text-[13px] leading-relaxed text-muted">
            {toast.detail}
          </p>
        )}
      </div>
      <button
        type="button"
        onClick={close}
        aria-label="Dismiss"
        className="-mr-1 rounded-md p-1 text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
      >
        <X className="size-4" aria-hidden />
      </button>
    </div>
  );
}

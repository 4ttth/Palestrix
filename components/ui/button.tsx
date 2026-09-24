import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/*
 * shadcn-style button, customized to the PalestrIX theme (never default state):
 * primary CTAs are pill-shaped per the shape lock; utility buttons use the 8px input radius.
 */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap font-medium transition-[transform,background-color,border-color] duration-150 ease-[var(--ease-swift)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring active:translate-y-px active:scale-[0.99] disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        primary: "rounded-full bg-accent text-accent-foreground hover:opacity-90",
        secondary:
          "rounded-full border border-border bg-surface text-foreground hover:bg-surface-2",
        outline:
          "rounded-(--radius-input) border border-border bg-surface text-foreground hover:bg-surface-2",
        ghost: "rounded-(--radius-input) text-foreground hover:bg-surface-2",
        destructive:
          "rounded-(--radius-input) bg-danger text-danger-foreground hover:opacity-90",
        link: "text-accent underline-offset-4 hover:underline",
      },
      size: {
        sm: "h-8 px-3.5 text-[13px]",
        md: "h-10 px-5 text-sm",
        lg: "h-11 px-6 text-[15px]",
        icon: "size-9",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  /* Pending state. Every mutating button in the product used to swap its
   * own label to "Publishing..." by hand, which meant the label jumped
   * width mid-click and nothing moved while the request was in flight.
   * This keeps the label in place, holds the button's width, and puts a
   * spinner where the icon sits. */
  loading?: boolean;
  /* Announced to assistive tech while `loading`, since the visible label
   * deliberately does not change. */
  loadingLabel?: string;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant,
      size,
      loading = false,
      loadingLabel = "Working",
      disabled,
      children,
      ...props
    },
    ref
  ) => (
    <button
      ref={ref}
      aria-busy={loading || undefined}
      disabled={disabled || loading}
      className={cn(
        buttonVariants({ variant, size }),
        // A disabled-by-loading button should read as busy, not as
        // unavailable, so it keeps more contrast than plain :disabled.
        loading && "disabled:opacity-80",
        className
      )}
      {...props}
    >
      {loading && <Spinner />}
      {children}
      {loading && <span className="sr-only">{loadingLabel}</span>}
    </button>
  )
);
Button.displayName = "Button";

/* Sized in em so it tracks the button's own font-size across sm/md/lg
 * rather than needing a variant of its own. */
function Spinner() {
  return (
    <svg
      viewBox="0 0 16 16"
      aria-hidden
      className="size-[1.1em] shrink-0 animate-spin"
    >
      <circle
        cx="8"
        cy="8"
        r="6.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        opacity="0.25"
      />
      <path
        d="M8 1.5A6.5 6.5 0 0 1 14.5 8"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export { Button, buttonVariants };

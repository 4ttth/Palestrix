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
    VariantProps<typeof buttonVariants> {}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  )
);
Button.displayName = "Button";

export { Button, buttonVariants };

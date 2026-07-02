import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/*
 * Badges carry semantic state only. Lifecycle variants map 1:1 to the
 * instance state machine documented in docs/ephemeral-lifecycle.md.
 */
const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-medium",
  {
    variants: {
      variant: {
        neutral: "bg-surface-2 text-muted",
        accent: "bg-accent-soft text-accent",
        provisioning: "bg-provisioning-soft text-provisioning",
        running: "bg-running-soft text-running",
        stopped: "bg-stopped-soft text-stopped",
        expired: "bg-expired-soft text-expired",
        palestras: "bg-palestras-soft text-palestras",
        danger: "bg-expired-soft text-expired",
      },
    },
    defaultVariants: {
      variant: "neutral",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };

import * as React from "react";
import { CaretDown } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

/*
 * Styled native select: the management consoles need dependable dropdowns
 * (role, tenant) more than they need a custom popover. Same input chrome as
 * ui/input.tsx.
 */
const Select = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(({ className, children, ...props }, ref) => (
  <span className={cn("relative inline-flex w-full", className)}>
    <select
      ref={ref}
      className="h-9 w-full cursor-pointer appearance-none rounded-(--radius-input) border border-border bg-surface pl-3 pr-8 text-[13px] text-foreground focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50"
      {...props}
    >
      {children}
    </select>
    <CaretDown
      size={12}
      className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-muted"
    />
  </span>
));
Select.displayName = "Select";

export { Select };

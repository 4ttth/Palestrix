import * as React from "react";
import { cn } from "@/lib/utils";

/* Labels sit ABOVE inputs, always. No placeholder-as-label. */
const Label = React.forwardRef<
  HTMLLabelElement,
  React.LabelHTMLAttributes<HTMLLabelElement>
>(({ className, ...props }, ref) => (
  <label
    ref={ref}
    className={cn("text-[13px] font-medium text-foreground", className)}
    {...props}
  />
));
Label.displayName = "Label";

export { Label };

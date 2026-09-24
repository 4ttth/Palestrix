/*
 * The instance state badge, with the one thing the plain <Badge> could not
 * say: whether the machine is still moving.
 *
 * "Requested" and "Provisioning" are states the platform is actively
 * working through, and they rendered identically to "Stopped" — a static
 * pill. A student watching a lab come up had no way to tell a slow
 * provision from a stuck one without reloading, which is exactly what they
 * did. A live dot pulses while the state is in flight and sits still once
 * it settles, so the badge answers "is anything happening?" at a glance.
 *
 * The lifecycle itself is documented in docs/ephemeral-lifecycle.md; badge
 * variants map 1:1 to its states.
 */

import { Badge } from "@/components/ui/badge";
import { stateLabel } from "@/lib/labels";
import { cn } from "@/lib/utils";
import type { InstanceState } from "@/lib/api/types";

/** States the orchestration worker is still acting on. */
const IN_FLIGHT: ReadonlySet<InstanceState> = new Set<InstanceState>([
  "requested",
  "provisioning",
]);

export function StateBadge({
  state,
  className,
}: {
  state: InstanceState;
  className?: string;
}) {
  const moving = IN_FLIGHT.has(state);
  return (
    <Badge variant={state} className={cn("gap-1.5", className)}>
      <span className="relative flex size-1.5" aria-hidden>
        {moving && (
          // The expanding ring, behind the dot. aria-hidden on the wrapper:
          // the badge text already names the state, and a screen reader
          // announcing decoration would only add noise.
          <span className="absolute inline-flex size-full animate-[plx-ping_1.6s_var(--ease-out-soft)_infinite] rounded-full bg-current" />
        )}
        <span className="relative inline-flex size-1.5 rounded-full bg-current" />
      </span>
      {stateLabel[state]}
    </Badge>
  );
}

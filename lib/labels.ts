/* Display names for the instance state machine (docs/ephemeral-lifecycle.md).
 * Badge variants in components/ui/badge.tsx map 1:1 to these states. */

import type { InstanceState } from "@/lib/api/types";

export const stateLabel: Record<InstanceState, string> = {
  requested: "Requested",
  provisioning: "Provisioning",
  running: "Running",
  stopped: "Stopped",
  expired: "Expired",
  failed: "Failed",
};

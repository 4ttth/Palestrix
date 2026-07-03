/*
 * SAMPLE DATA for the marketing landing page only.
 *
 * As of Phase 5 every product surface renders live /api/v1 responses
 * (lib/api/), and the wire types live in lib/api/types.ts. What remains
 * here is the demo provisioning-log replay the public landing page shows
 * to visitors who are not signed in — clearly a demonstration, not state.
 */

export const provisioningSample = [
  { t: "09:14:02", level: "info" as const, msg: "queue: job accepted (tenant hau-bscs-3a, quota 2/3 instances)" },
  { t: "09:14:03", level: "info" as const, msg: "docker: pulling registry.palestrix.local/labs/log-triage:1.4" },
  { t: "09:14:09", level: "info" as const, msg: "docker: layer 7f3a2c11 extracted (34.2 MB)" },
  { t: "09:14:12", level: "info" as const, msg: "network: attached to isolated bridge net-hau-bscs-3a" },
  { t: "09:14:14", level: "info" as const, msg: "firewall: tenant egress policy applied (deny-all, allow 10.24.7.0/24)" },
  { t: "09:14:18", level: "info" as const, msg: "container: started, healthcheck 1/3" },
  { t: "09:14:21", level: "ok" as const, msg: "healthcheck passed, ssh exposed on 10.24.7.31:2211" },
  { t: "09:14:22", level: "ok" as const, msg: "instance running, TTL reaper armed for 90 min" },
];

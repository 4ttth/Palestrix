# Ephemeral Instance Lifecycle

Every lab instance in PalestrIX is ephemeral: it is born from a request,
lives on a TTL, and is destroyed by a reaper. This document is the contract
between the UI, the API, the orchestration workers, and the adapters.

## State machine

```
            +-----------+        +--------------+        +---------+
 request -> | requested | -----> | provisioning | -----> | running |
            +-----------+  job   +--------------+  ready +----+----+
                  |        taken       |                      |
                  | quota denied       | provision failed     | stop / TTL hit
                  v                    v                      v
             +---------+          +--------+            +---------+
             | denied  |          | failed |            | stopped |
             +---------+          +--------+            +----+----+
                                                             | destroy / TTL hit
                                                             v
                                                        +---------+
                                                        | expired |  (terminal: destroyed,
                                                        +---------+   quota released)
```

UI badge mapping (theme tokens): `provisioning` (sky), `running` (green),
`stopped` (gray), `expired` (rose). `requested`, `denied`, and `failed`
render as toasts/inline errors, not badges, because they are transient.

## Walkthrough

1. **Request.** Student opens a lab (or teacher test-launches one).
   `POST /api/v1/instances` with the lab template id. The API checks RBAC,
   then tenant quota (instances, vCPU, RAM). Denials return `409` with the
   quota that blocked, so the UI can say exactly why.
2. **Queue.** An `instance.requested` job lands on the queue (Redis/SQS)
   with tenant, template, TTL, and access mode.
3. **Provision.** A worker claims the job and calls the provider adapter:
   - **Proxmox VM:** clone from template (`POST /nodes/{node}/qemu/{vmid}/clone`),
     attach ISO if the template requires one, set the tenant VLAN/bridge,
     start, wait for the QEMU guest agent heartbeat.
   - **Docker container:** ensure the image is built from the teacher's
     archive, create the container on the tenant network with resource
     limits, start, wait for the healthcheck.
   Every adapter action emits a structured log line; the worker publishes
   them to a channel the API relays over SSE
   (`GET /api/v1/instances/{id}/logs/stream`). The frontend renders this
   stream in `components/lab/ProvisioningLog.tsx`. No fake progress bars:
   the log is the progress.
4. **Expose.**
   - **GUI mode:** the adapter requests a noVNC ticket (Proxmox) or attaches
     a VNC bridge (container); the UI embeds the console.
   - **Headless mode:** the adapter reports `host:port`; the UI shows the
     connect command. Credentials are generated per-instance and die with it.
5. **Run + countdown.** `expires_at = started_at + ttl`. The UI countdown
   (`components/lab/Countdown.tsx`) renders the server-authoritative expiry.
   Extensions: `POST /api/v1/instances/{id}/extend` spends Palestras through
   the gamification service and moves `expires_at`, within the template's
   maximum.
6. **Reap.** The reaper worker scans every 60 s for
   `expires_at < now() AND state IN ('running','stopped')`:
   stop, destroy, release quota, emit `instance.expired` (webhook + UI
   event), write the ledger entries. A slower reconciliation pass compares
   provider reality against the registry and kills orphans in both
   directions (records without resources, resources without records).

## Multitenancy invariants

- An instance always belongs to exactly one tenant; the tenant fixes its
  network (VLAN/VXLAN/bridge on baremetal, namespace + NetworkPolicy on
  cloud), its naming prefix, and its quota pool.
- Default-deny between tenants and from tenants to management networks.
- Quota is reserved at request time and released only by the reaper or a
  failed provision. There is no code path that destroys an instance without
  releasing quota (single `release()` in the registry layer).

## Failure policy

| Failure | Behavior |
|---|---|
| Provision fails | State `failed`, quota released, logs kept 24 h for the teacher, student sees the real error line |
| Worker dies mid-provision | Job re-queued once with the same instance id (adapters are idempotent by instance id); second failure marks `failed` |
| Reaper misses (outage) | Reconciliation pass or the cloud fallback reaper catches it; alarm fires if any instance outlives max TTL |
| Node dies | Registry marks its instances `expired`; students relaunch, quota already released |

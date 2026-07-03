# Use Case B: Cloud Deployment (Generic / AWS Names)

Run PalestrIX on managed cloud services. Every service below is named twice:
the **generic** capability first, then the **AWS** product. If your provider
lacks one of the AWS-named products, fall back to whichever equivalent exists
(the generic column is the contract, the AWS column is the reference
implementation).

## Service map

| # | Capability (generic name) | AWS name | PalestrIX role |
|---|---|---|---|
| 1 | Virtual machines | EC2 | Heavy/GUI lab instances, optional spot capacity |
| 2 | Managed Kubernetes | EKS (ECS as simpler alternative) | Platform services + container labs |
| 3 | Serverless functions | Lambda | TTL reaper trigger, webhook fan-out, image cleanup |
| 4 | Object storage | S3 | ISOs, teacher archives, writeup assets, reports, backups |
| 5 | Managed PostgreSQL | RDS (PostgreSQL) | Primary database |
| 6 | Managed Redis | ElastiCache (Redis) | Queue backend and cache |
| 7 | Load balancer | ALB (plus NLB for raw TCP labs) | Ingress for app/API; TCP entry for headless labs |
| 8 | DNS | Route 53 | `palestrix.example.edu`, wildcard lab records |
| 9 | TLS certificates | ACM | Certificates for the load balancer and CDN |
| 10 | Platform identity | IAM | Service roles, least-privilege policies |
| 11 | User identity (optional) | Cognito | OIDC federation if the school mandates SSO |
| 12 | Secrets | Secrets Manager (or SSM Parameter Store) | DB creds, API keys, webhook secrets |
| 13 | Container registry | ECR | Lab images built from teacher archives |
| 14 | Message queue | SQS | Provisioning jobs, reaper work items |
| 15 | CDN | CloudFront | Static frontend assets, writeup media |
| 16 | Monitoring/logs | CloudWatch | Metrics, alarms, provisioning log retention |

## Target topology

```
Route 53 (DNS) --> CloudFront (CDN, static) 
                \-> ALB (TLS via ACM)
                      |
        +-------------+--------------+
        |                            |
   [ EKS cluster ]              [ NLB (TCP) ]
   namespaces:                       |
     platform: frontend, API,   headless lab
       workers, webhooks        entry points
     labs-<tenant>: ephemeral
       lab pods (one namespace
       per class/event)
        |
   ECR (images)   SQS (jobs)   Lambda (reaper tick, webhooks)
        |
   RDS Postgres   ElastiCache Redis   S3 (objects)   Secrets Manager

   Optional: EC2 (spot) node group for VM-class/GUI labs
   Isolated: sandbox node group or separate account for the malware sandbox
```

## Platform services on Kubernetes / EKS

- One cluster, two node groups: `platform` (on-demand) and `labs`
  (spot-friendly, tainted so only lab pods schedule there).
- Namespace `platform` runs the Next.js frontend, FastAPI core API, workers,
  and the webhook dispatcher. Standard Deployments + HPA.
- Images build in CI and land in the container registry / **ECR**.
- Configuration comes from the secrets service / **Secrets Manager** via
  external-secrets or CSI driver; nothing sensitive in manifests.

## Ephemeral labs in the cloud

Container labs (the common case):

1. Teacher uploads a Dockerfile/compose archive; a build job produces an
   image in the registry / **ECR**.
2. A provisioning job goes on the queue / **SQS**.
3. A worker creates (or reuses) the tenant namespace `labs-<tenant>` and
   applies: Pod (or Deployment), NetworkPolicy (default-deny, tenant-scoped
   allows), ResourceQuota, and a Service.
4. Exposure: GUI labs run a websocket VNC bridge behind the load balancer /
   **ALB**; headless labs get a TCP port on the network load balancer /
   **NLB** or a per-instance NodePort reachable through the event VPN.
5. Logs: the worker streams pod events and container stdout to the browser
   over SSE, and retains them in the monitoring service / **CloudWatch**.

VM-class labs (Windows targets, kernel exercises):

- Provision short-lived virtual machines / **EC2** (spot where interruption
  is acceptable) from prebuilt AMIs; tag with `palestrix:tenant` and
  `palestrix:expires-at`.

## Multitenancy

| Concern | Kubernetes mechanism | VM mechanism |
|---|---|---|
| Isolation | Namespace per tenant + NetworkPolicy default-deny | Security groups per tenant, no cross-tenant rules |
| Quotas | ResourceQuota + LimitRange per namespace | Service quotas + orchestration-level caps |
| Naming | `labs-<tenant>` namespaces, labeled pods | Resource tags |
| Cleanup | Namespace delete removes everything for an event | Terminate by tag |

The tenant registry (Phase 7) is the same as on baremetal: cloud deployments
run `PALESTRIX_CLOUD_BACKEND=local` — OpenNebula/CloudStack front a
hypervisor you own, not a managed cloud — and the tenant row's CIDR and
naming drive the mechanisms above (`labs-<tenant>` namespaces, per-tenant
subnets/security groups). The API enforces all three tenant quotas
(instances, vCPU, RAM against each template's declared `cpu`/`ram_gb`) at
launch, before any pod or VM exists; namespace ResourceQuota is the
defense-in-depth behind it, not the primary control. Archiving a tenant
stops launches immediately and is the signal to delete its namespace.

## TTL reaper in the cloud

Two cooperating mechanisms (belt and suspenders):

1. **Primary:** the same reaper worker as baremetal, running in the
   `platform` namespace, driven by the queue / **SQS**.
2. **Fallback:** a scheduled serverless function / **Lambda** (EventBridge
   rule, every 5 minutes) lists lab pods and tagged VMs / **EC2** past
   `expires-at` and force-deletes them, then reports discrepancies. This
   catches reaper outages and orphaned resources, which on cloud are billed
   money instead of just wasted RAM.

## Storage

- Object storage / **S3** buckets: `palestrix-isos`, `palestrix-archives`,
  `palestrix-writeups`, `palestrix-sandbox-reports`, `palestrix-backups`.
  Lifecycle rules: expire sandbox reports at 90 days, backups at 30 days.
- Database / **RDS PostgreSQL**: Multi-AZ for production, automated
  snapshots, 7-day PITR window.
- Queue/cache / **ElastiCache Redis**: single replica group; the queue
  contents are re-derivable so no backup needed.

## Identity and secrets

- Platform identity / **IAM**: one role per service (frontend, API, workers,
  reaper function) with least-privilege policies; IRSA binds roles to
  service accounts on the cluster.
- User identity: PalestrIX's own passkey auth is primary. If the school
  requires SSO, federate through the managed identity pool / **Cognito**
  as an OIDC provider (the API is OIDC-ready).
- Secrets / **Secrets Manager**: database URL, Redis URL, webhook signing
  keys, registry credentials, Canvas keys (Phase 8).

## Production boot guard (Phase 7)

Set `PALESTRIX_ENVIRONMENT=production` on the API and worker pods. At boot
the app runs its readiness checks and refuses to start while any fail —
a crash-looping pod after a config change means a finding to fix, never a
check to skip. Each finding maps to a service in the table above:

| Finding | Cloud remedy |
|---|---|
| Secret is the dev default / under 32 chars | Unique `PALESTRIX_SECRET_KEY` from the secrets service / **Secrets Manager** |
| Database is SQLite | `PALESTRIX_DATABASE_URL` at the managed PostgreSQL / **RDS** |
| Origin is not https | `PALESTRIX_ORIGIN=https://...` behind the load balancer / **ALB** + **ACM** (passkeys require a secure origin) |
| CORS allows `*` or plaintext origins | Pin `PALESTRIX_CORS_ORIGINS` to the exact frontend origin |
| Queue is inline | `PALESTRIX_QUEUE_BACKEND=redis` at the managed Redis / **ElastiCache** |
| Reaper disabled | `PALESTRIX_REAPER_ENABLED=true` (a missed TTL is a billing bug here) |
| Storage is the local folder | `PALESTRIX_STORAGE_BACKEND=minio` pointed at object storage / **S3** |

Every API response also carries baseline security headers (nosniff,
frame-deny, no-referrer, Permissions-Policy, HSTS in production); keep the
load balancer/CDN copies of those headers as belt and suspenders, not as
the only source.

## Cost guardrails

- Lab node group scales to zero outside class hours (scheduled scaling).
- Spot capacity / **EC2 Spot** for VM labs where interruption is tolerable.
- The reaper is the cost control: a missed TTL is a billing bug. Alarm on
  `palestrix_instances_running > expected_max` and on any instance older
  than the max TTL (monitoring / **CloudWatch** alarm).
- Budget alert at the account level before the first class uses the range.

## Acceptance test

Identical to Use Case A's acceptance test, plus:

1. Kill the reaper deployment mid-class; confirm the fallback function /
   **Lambda** still reaps expired labs within 5 minutes.
2. Delete an event namespace after a CTF; confirm zero lab resources remain
   (pods, services, load balancer target groups, tagged VMs).
3. Review the bill the day after the first event; every line item should map
   to a row in the service table above.
4. Deploy once with a deliberately broken readiness check (for example the
   dev secret): the API pod must crash-loop naming the finding instead of
   serving traffic.
5. Launch labs up to a tenant's vCPU cap; the next launch must be refused
   with the quota named, before any pod or VM is created.

# Installing PalestrIX — Use Case B: Cloud (AWS Reference)

A step-by-step installation on managed cloud services, using AWS product
names with the generic capability alongside (the pattern from
[usecase-b-cloud-aws.md](usecase-b-cloud-aws.md): the generic name is the
contract, AWS is the reference). Follow it top to bottom in a fresh account.

**What you end up with:** one application VM (EC2) running the API, worker,
frontend, and Docker-provisioned container labs, backed by managed
PostgreSQL (RDS), managed Redis (ElastiCache), and object storage (S3),
fronted by a load balancer (ALB) with managed TLS (ACM) on your domain
(Route 53) — the smallest production-grade cloud deployment. The Kubernetes
scale-out architecture (EKS, per-tenant namespaces, the Lambda fallback
reaper) is described in the [runbook](usecase-b-cloud-aws.md); everything
you configure here carries over to it unchanged.

## Contents

1. [Prerequisites](#1-prerequisites)
2. [VPC and security groups](#2-vpc-and-security-groups)
3. [Object storage (S3)](#3-object-storage-s3)
4. [Managed PostgreSQL (RDS)](#4-managed-postgresql-rds)
5. [Managed Redis (ElastiCache)](#5-managed-redis-elasticache)
6. [Secrets (Secrets Manager)](#6-secrets-secrets-manager)
7. [The application VM (EC2)](#7-the-application-vm-ec2)
8. [Services and configuration](#8-services-and-configuration)
9. [TLS, load balancer, DNS (ACM, ALB, Route 53)](#9-tls-load-balancer-dns-acm-alb-route-53)
10. [Container labs on the cloud](#10-container-labs-on-the-cloud)
11. [Canvas LMS (optional)](#11-canvas-lms-optional)
12. [Boot guard, cost guardrails, verification](#12-boot-guard-cost-guardrails-verification)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Prerequisites

| You need | Details |
|---|---|
| An AWS account | Fresh or a dedicated sub-account; budget alert configured first |
| AWS CLI v2 | Authenticated as an admin able to create the resources below |
| A domain | Hosted zone in Route 53 (or DNS you can point at an ALB alias) |
| This repository | Cloned onto the application VM in step 7 |

Set the working variables used throughout (adjust region and domain):

```sh
export AWS_REGION=ap-southeast-1
export DOMAIN=palestrix.example.edu
```

## 2. VPC and security groups

1. One VPC with two public and two private subnets (the console's *VPC and
   more* wizard does this in one screen), or:

   ```sh
   aws ec2 create-vpc --cidr-block 10.30.0.0/16 \
     --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=palestrix}]'
   ```

   Public subnets carry the load balancer and the application VM; private
   subnets carry RDS and ElastiCache.

2. Security groups (least privilege, referenced by id below):

   | Group | Inbound | Purpose |
   |---|---|---|
   | `palestrix-alb` | 80, 443 from `0.0.0.0/0` | The load balancer |
   | `palestrix-app` | 8000, 3000 from `palestrix-alb`; 22 from your admin IP; lab port range 20000–20999 from where students connect | The application VM |
   | `palestrix-data` | 5432, 6379 from `palestrix-app` only | RDS + ElastiCache |

   ```sh
   aws ec2 create-security-group --group-name palestrix-alb  --description "edge"  --vpc-id <vpc-id>
   aws ec2 create-security-group --group-name palestrix-app  --description "app"   --vpc-id <vpc-id>
   aws ec2 create-security-group --group-name palestrix-data --description "data"  --vpc-id <vpc-id>
   # then authorize-security-group-ingress per the table
   ```

## 3. Object storage (S3)

The backend's storage client is S3-compatible; it talks to AWS S3 directly
(`PALESTRIX_STORAGE_BACKEND=minio` with the S3 endpoint).

```sh
for b in isos lab-archives writeups sandbox-samples sandbox-reports backups; do
  aws s3 mb "s3://palestrix-$b" --region $AWS_REGION
done
aws s3api put-bucket-lifecycle-configuration --bucket palestrix-sandbox-reports \
  --lifecycle-configuration '{"Rules":[{"ID":"expire","Status":"Enabled","Filter":{},"Expiration":{"Days":90}}]}'
aws s3api put-bucket-lifecycle-configuration --bucket palestrix-backups \
  --lifecycle-configuration '{"Rules":[{"ID":"expire","Status":"Enabled","Filter":{},"Expiration":{"Days":30}}]}'
```

> **Bucket names are global.** If `palestrix-*` is taken, pick a site prefix
> (`hau-palestrix-*`) — the application only needs the six bucket suffixes
> to exist under one credential; bucket names are configured nowhere else.
> Create an IAM user (or better, an instance-role policy in step 7) scoped
> to these buckets and record the access key pair.

## 4. Managed PostgreSQL (RDS)

```sh
aws rds create-db-subnet-group --db-subnet-group-name palestrix \
  --db-subnet-group-description palestrix --subnet-ids <private-subnet-1> <private-subnet-2>

aws rds create-db-instance \
  --db-instance-identifier palestrix \
  --engine postgres --engine-version 16.4 \
  --db-instance-class db.t4g.medium \
  --allocated-storage 50 \
  --master-username palestrix \
  --master-user-password 'CHANGE-ME-DB-PASSWORD' \
  --db-name palestrix \
  --vpc-security-group-ids <palestrix-data-sg-id> \
  --db-subnet-group-name palestrix \
  --backup-retention-period 7 \
  --no-publicly-accessible
```

For production classes, add `--multi-az`. Record the endpoint hostname once
available:

```sh
aws rds describe-db-instances --db-instance-identifier palestrix \
  --query 'DBInstances[0].Endpoint.Address' --output text
```

## 5. Managed Redis (ElastiCache)

```sh
aws elasticache create-cache-subnet-group --cache-subnet-group-name palestrix \
  --cache-subnet-group-description palestrix --subnet-ids <private-subnet-1> <private-subnet-2>

aws elasticache create-replication-group \
  --replication-group-id palestrix \
  --replication-group-description "palestrix queue" \
  --engine redis --cache-node-type cache.t4g.small \
  --num-cache-clusters 1 \
  --cache-subnet-group-name palestrix \
  --security-group-ids <palestrix-data-sg-id>
```

Record the primary endpoint:

```sh
aws elasticache describe-replication-groups --replication-group-id palestrix \
  --query 'ReplicationGroups[0].NodeGroups[0].PrimaryEndpoint.Address' --output text
```

## 6. Secrets (Secrets Manager)

Generate and store the application secret; keep every credential here
rather than in shell history or AMIs:

```sh
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # PALESTRIX_SECRET_KEY

aws secretsmanager create-secret --name palestrix/env --secret-string '{
  "PALESTRIX_SECRET_KEY": "<generated above>",
  "DB_PASSWORD": "CHANGE-ME-DB-PASSWORD",
  "S3_ACCESS_KEY": "<from step 3>",
  "S3_SECRET_KEY": "<from step 3>"
}'
```

The instance role (step 7) gets `secretsmanager:GetSecretValue` on this one
secret; the boot script renders it into the env file.

## 7. The application VM (EC2)

1. Launch the instance:

   ```sh
   aws ec2 run-instances \
     --image-id <ubuntu-24.04 AMI for your region> \
     --instance-type t3.xlarge \
     --key-name <your-keypair> \
     --security-group-ids <palestrix-app-sg-id> \
     --subnet-id <public-subnet-1> \
     --iam-instance-profile Name=palestrix-app \
     --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=100,VolumeType=gp3}' \
     --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=palestrix-app}]'
   ```

   The `palestrix-app` instance profile carries two policies: read on
   `palestrix/env` (Secrets Manager) and read/write scoped to the six
   `palestrix-*` buckets.

2. SSH in and install the base:

   ```sh
   sudo apt update && sudo apt install -y git python3.12 python3.12-venv docker.io
   curl -fsSL https://deb.nodesource.com/setup_22.x | sudo bash - && sudo apt install -y nodejs
   sudo useradd --system --create-home --shell /usr/sbin/nologin palestrix
   sudo usermod -aG docker palestrix        # the Docker adapter drives the local CLI
   sudo -u palestrix git clone https://github.com/<your-org>/palestrix.git /home/palestrix/app
   ```

## 8. Services and configuration

The service topology is identical to baremetal from here — same venv, same
three systemd units. Follow
[install-usecase-a-baremetal.md §8–9](install-usecase-a-baremetal.md#8-the-core-api-and-worker)
for the unit files verbatim; only the `.env` differs:

```ini
PALESTRIX_ENVIRONMENT=production
PALESTRIX_SECRET_KEY=<from Secrets Manager>

PALESTRIX_DATABASE_URL=postgresql+psycopg://palestrix:<DB_PASSWORD>@<rds-endpoint>:5432/palestrix

PALESTRIX_RP_ID=palestrix.example.edu
PALESTRIX_ORIGIN=https://palestrix.example.edu
PALESTRIX_CORS_ORIGINS=https://palestrix.example.edu

# Object storage / S3: the storage client is S3-compatible.
PALESTRIX_STORAGE_BACKEND=minio
PALESTRIX_MINIO_ENDPOINT=s3.ap-southeast-1.amazonaws.com
PALESTRIX_MINIO_ACCESS_KEY=<S3_ACCESS_KEY>
PALESTRIX_MINIO_SECRET_KEY=<S3_SECRET_KEY>
PALESTRIX_MINIO_SECURE=true

PALESTRIX_QUEUE_BACKEND=redis
PALESTRIX_REDIS_URL=redis://<elasticache-endpoint>:6379/0
PALESTRIX_REAPER_ENABLED=true

# Container labs via the Docker adapter (step 10).
PALESTRIX_DOCKER_ENABLED=true
PALESTRIX_DOCKER_HOST_ADDRESS=<the VM's public/elastic IP>

# Tenants: "local" registry allocation is correct here — OpenNebula and
# CloudStack front hypervisors you own, not a managed cloud (see runbook).
PALESTRIX_CLOUD_BACKEND=local
PALESTRIX_TENANT_CIDR_POOL=10.24.0.0/16
```

A small render script keeps secrets out of the disk image — run it from the
unit's `ExecStartPre` or at boot:

```sh
aws secretsmanager get-secret-value --secret-id palestrix/env \
  --query SecretString --output text | python3 -c '
import json,sys
for k,v in json.load(sys.stdin).items(): print(f"{k}={v}")' >> /home/palestrix/app/backend/.env
```

Initialize the schema and start the units exactly as in
[Use Case A §8.4–8.6](install-usecase-a-baremetal.md#8-the-core-api-and-worker);
build and start the frontend as in [§9](install-usecase-a-baremetal.md#9-the-frontend).
The production boot guard runs at startup here too — a crash-looping service
names its finding in the journal.

## 9. TLS, load balancer, DNS (ACM, ALB, Route 53)

1. Certificate (DNS-validated, auto-renewing):

   ```sh
   aws acm request-certificate --domain-name $DOMAIN --validation-method DNS
   # add the CNAME it prints to Route 53, wait for ISSUED
   ```

2. Load balancer with path routing — `/api/*` and `/healthz` to the API
   target group (port 8000), everything else to the frontend (port 3000):

   ```sh
   aws elbv2 create-load-balancer --name palestrix --type application \
     --subnets <public-subnet-1> <public-subnet-2> --security-groups <palestrix-alb-sg-id>
   aws elbv2 create-target-group --name palestrix-api --protocol HTTP --port 8000 \
     --vpc-id <vpc-id> --health-check-path /healthz --target-type instance
   aws elbv2 create-target-group --name palestrix-app --protocol HTTP --port 3000 \
     --vpc-id <vpc-id> --health-check-path / --target-type instance
   # register the EC2 instance in both, then:
   aws elbv2 create-listener --load-balancer-arn <alb-arn> --protocol HTTPS --port 443 \
     --certificates CertificateArn=<acm-arn> \
     --default-actions Type=forward,TargetGroupArn=<palestrix-app-tg-arn>
   aws elbv2 create-rule --listener-arn <listener-arn> --priority 10 \
     --conditions Field=path-pattern,Values='/api/*','/healthz' \
     --actions Type=forward,TargetGroupArn=<palestrix-api-tg-arn>
   # plus an HTTP:80 listener that redirects to HTTPS
   ```

3. DNS alias:

   ```sh
   aws route53 change-resource-record-sets --hosted-zone-id <zone-id> --change-batch '{
     "Changes": [{"Action": "UPSERT", "ResourceRecordSet": {
       "Name": "palestrix.example.edu", "Type": "A",
       "AliasTarget": {"HostedZoneId": "<alb-hosted-zone-id>",
                        "DNSName": "<alb-dns-name>", "EvaluateTargetHealth": true}}}]}'
   ```

4. Verify from outside: `curl -s https://$DOMAIN/healthz` → `{"ok":true}`,
   then register your account, enroll a passkey, and promote yourself to
   superadmin (SQL against RDS, as in Use Case A §8.7).

## 10. Container labs on the cloud

With `PALESTRIX_DOCKER_ENABLED=true`, teacher-published archives build into
images on the VM and launch as containers with published ports in the
20000–20999 range; the `palestrix-app` security group already admits that
range. Per-tenant isolation comes from the Docker adapter pinning each
tenant's bridge network to its registry-allocated subnet; quotas are
enforced by the API at launch, before any container exists.

Scaling beyond one VM — GPU labs, Windows VM labs, hundreds of concurrent
students — is the EKS architecture in the
[runbook](usecase-b-cloud-aws.md#ephemeral-labs-in-the-cloud): per-tenant
namespaces, ResourceQuota as defense-in-depth, the NLB for headless entry,
and the EventBridge + Lambda fallback reaper (on cloud, a missed TTL is a
billing bug, so it gets a second, independent mechanism).

## 11. Canvas LMS (optional)

Identical to baremetal — the integration is deployment-agnostic. Follow
[install-usecase-a-baremetal.md §13](install-usecase-a-baremetal.md#13-canvas-lms-optional)
end to end, with two cloud notes:

- Keep `PALESTRIX_CANVAS_TOOL_PRIVATE_KEY` in Secrets Manager with the rest
  of `palestrix/env` (the runbook's secrets table lists Canvas keys there
  on purpose — Canvas pins the published JWKS, so this key must survive
  instance replacement).
- Instructure-cloud Canvas (`*.instructure.com`) needs the three SSO URL
  overrides shown in that section.

## 12. Boot guard, cost guardrails, verification

1. **Boot guard.** Deliberately break one readiness check (for example set
   the dev secret), restart `palestrix-api`, and confirm the unit refuses
   to start naming the finding; restore it. Every finding's cloud remedy is
   tabled in the [runbook](usecase-b-cloud-aws.md#production-boot-guard-phase-7).

2. **Cost guardrails** (do these before the first class):

   ```sh
   aws budgets create-budget --account-id <acct> --budget '{
     "BudgetName": "palestrix", "BudgetLimit": {"Amount": "200", "Unit": "USD"},
     "TimeUnit": "MONTHLY", "BudgetType": "COST"}' \
     --notifications-with-subscribers '[{"Notification": {"NotificationType": "ACTUAL",
       "ComparisonOperator": "GREATER_THAN", "Threshold": 80},
       "Subscribers": [{"SubscriptionType": "EMAIL", "Address": "you@example.edu"}]}]'
   ```

   Alarm on any lab instance older than the maximum TTL (CloudWatch): the
   reaper is the cost control, and this alarm is how you notice it failing.

3. **Acceptance test.** Run the [Use Case B acceptance test](usecase-b-cloud-aws.md#acceptance-test)
   (Use Case A's list plus the cloud items: reaper-kill drill, post-event
   resource sweep, the bill-to-service-table review, the broken-readiness
   deploy, and the named-quota refusal).

## 13. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| API can't reach RDS/Redis | Security group chain broken | `palestrix-data` must admit 5432/6379 from `palestrix-app` (group-to-group, not CIDR) |
| ALB targets unhealthy | Health-check path or port wrong | API target group checks `/healthz` on 8000; frontend checks `/` on 3000 |
| Passkeys fail behind the ALB | Origin mismatch | `PALESTRIX_RP_ID`/`_ORIGIN` must be the public domain; the ALB terminates TLS so the app never sees https itself — that is fine, the origin config is what matters |
| Uploads fail with S3 | Bucket policy/credentials | The instance-role or key pair must cover all six buckets; `PALESTRIX_MINIO_SECURE=true` for AWS endpoints |
| Lab ports unreachable | Security group range | Published container ports live in 20000–20999 on the VM's address (`PALESTRIX_DOCKER_HOST_ADDRESS`) |
| Boot guard refuses to start | It is doing its job | The journal names the finding; the runbook tables the cloud remedy for each |
| Canvas rejects launches after an instance rebuild | Tool key regenerated | Serve the same `PALESTRIX_CANVAS_TOOL_PRIVATE_KEY` from Secrets Manager; never let it default to ephemeral in production |

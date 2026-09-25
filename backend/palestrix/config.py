"""Application settings. Every value can come from the environment with the
PALESTRIX_ prefix, or from a .env file next to the working directory."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PALESTRIX_", env_file=".env", extra="ignore"
    )

    # "production" arms the Phase 7 boot guard: the app refuses to start
    # while hardening.production_readiness() reports failures (dev secret,
    # SQLite, plaintext CORS origins, TLS verification off, ...).
    environment: str = "development"  # "development" | "production"

    database_url: str = "sqlite:///./palestrix.db"
    secret_key: str = "dev-only-secret-change-me"

    # Sessions and tokens
    session_ttl_minutes: int = 12 * 60
    client_token_ttl_minutes: int = 60

    # WebAuthn relying party
    rp_id: str = "localhost"
    rp_name: str = "PalestrIX"
    origin: str = "http://localhost:3000"
    # Where WebAuthn challenges live between the options call and the verify
    # call. "memory" is an in-process dict: correct for one API process, and
    # broken under `uvicorn --workers N`, because the two calls land on
    # different workers and the verify cannot see the challenge the options
    # call issued. Any multi-worker deployment must set "redis" -- the
    # production boot guard fails on "memory" for that reason.
    webauthn_challenge_backend: str = "memory"  # "memory" | "redis"

    # Object storage
    storage_backend: str = "local"  # "local" | "minio"
    storage_local_root: str = "./.objects"
    minio_endpoint: str = ""
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_secure: bool = False

    cors_origins: str = "http://localhost:3000"

    # Comma-separated directories holding development plugins
    # (each with plugin.toml + the entry module as a .py file).
    plugin_paths: str = ""

    # Academy. The four paths in academy_catalog.py are applied to the
    # database at startup so a pull-and-restart publishes catalog changes.
    # Set false to freeze the catalog and manage paths through the API only.
    academy_catalog_autoload: bool = True

    # Compete
    flag_cooldown_seconds: int = 30

    # Instances
    instance_extend_cost_palestras: int = 150
    instance_extend_step_minutes: int = 30

    # Orchestration (Phase 4). The queue runs jobs inline (same process,
    # dev/test default) or on Redis via RQ ("redis"), consumed by
    # `python -m palestrix.worker`.
    queue_backend: str = "inline"  # "inline" | "redis"
    redis_url: str = "redis://localhost:6379/0"
    provision_max_attempts: int = 2  # re-queued once, then marked failed

    # TTL reaper: scans for expired instances and destroys them. Runs as a
    # background thread in-app for the inline backend; the worker process
    # owns it in a Redis deployment.
    reaper_enabled: bool = True
    reaper_interval_seconds: int = 60

    # Log stream (SSE): poll cadence and the cap on how long one client may
    # hold a stream open while an instance is still provisioning.
    log_stream_poll_seconds: float = 0.5
    log_stream_max_seconds: float = 300.0

    # Proxmox VE adapter: activated for the "vm" kind when a host is set.
    # Auth is an API token (Datacenter -> Permissions -> API Tokens).
    proxmox_host: str = ""  # e.g. https://pve-01.example.edu:8006
    proxmox_token_id: str = ""  # user@pam!tokenname
    proxmox_token_secret: str = ""
    proxmox_node: str = "pve"
    proxmox_verify_tls: bool = True
    # PEM of the CA that signed the Proxmox API cert, pinned as the only
    # trust anchor. Set this for a self-signed cluster: Proxmox's own root CA
    # (/etc/pve/pve-root-ca.pem) carries no keyUsage extension, which the
    # system trust store path rejects on Python 3.13+ (see tls.py).
    proxmox_ca_bundle: str = ""
    proxmox_bridge: str = "vmbr0"  # tenant VLAN tags ride on this bridge
    proxmox_timeout_seconds: float = 120.0
    proxmox_iso_storage: str = "local"  # admin ISO uploads forward here

    # Multitenant cloud layer (Phase 7). "local" allocates tenant VLANs and
    # CIDRs in the registry only (the dev/test default and the smallest
    # baremetal deployment); "opennebula" or "cloudstack" additionally
    # materializes every tenant in that manager (group/VDC or domain/account,
    # quotas, and the tenant network). Pick one per site.
    cloud_backend: str = "local"  # "local" | "opennebula" | "cloudstack"
    # Auto tenancy for self-registration: new accounts join this tenant.
    # Empty falls back to "the sole active tenant, if exactly one exists"
    # (the single-class deployment), else the account starts unassigned and
    # an admin assigns it from the users console.
    default_tenant_id: str = ""
    tenant_vlan_min: int = 100
    tenant_vlan_max: int = 1999
    tenant_cidr_pool: str = "10.24.0.0/16"  # carved into /24s per tenant

    # OpenNebula front-end (XML-RPC), e.g. http://one.internal:2633/RPC2
    opennebula_endpoint: str = ""
    opennebula_username: str = ""
    opennebula_password: str = ""
    opennebula_phydev: str = "bond0"  # trunk device carrying the 802.1Q tags
    opennebula_timeout_seconds: float = 30.0

    # CloudStack management server, e.g. https://cs.internal:8080/client/api
    cloudstack_endpoint: str = ""
    cloudstack_api_key: str = ""
    cloudstack_secret_key: str = ""
    cloudstack_zone_id: str = ""
    cloudstack_network_offering_id: str = ""
    cloudstack_verify_tls: bool = True
    cloudstack_ca_bundle: str = ""  # PEM to pin; see proxmox_ca_bundle
    cloudstack_timeout_seconds: float = 30.0

    # Docker adapter: activated for the "container" kind when enabled. Drives
    # the local docker CLI; images build from teacher archives in storage.
    docker_enabled: bool = False
    docker_binary: str = "docker"
    docker_host_address: str = "127.0.0.1"  # where published ports are reachable
    docker_memory_limit: str = "512m"
    docker_cpu_limit: str = "1.0"
    docker_network_prefix: str = "net-"  # tenant network: net-<tenant_id>

    # Malware sandbox (Phase 6). The demo detonator runs real static analysis
    # on the submitted bytes and a clearly-labelled synthetic behavior trace —
    # it never executes a sample, so it is safe in dev/test. A deployment sets
    # sandbox_coordinator_url to the isolated detonation host (a single TCP
    # port, per the VLAN ACL in docs/sandbox-security.md); the coordinator
    # detonator then takes over and the demo one steps aside.
    sandbox_enabled: bool = True  # the module answers instead of 501
    sandbox_max_sample_mb: int = 100
    # Command-line submissions. Obfuscated one-liners get long -- a base64
    # blob inside a base64 blob is routinely several KB -- so the ceiling is
    # generous; it exists to bound storage, not to second-guess the input.
    sandbox_max_command_chars: int = 64_000
    # Advertised on /sandbox/status. The kill itself is enforced by the
    # coordinator (SBX_WALL_CLOCK_SECONDS), which owns the VM -- keep the two
    # in step, and both under sandbox_coordinator_timeout_seconds.
    sandbox_wall_clock_seconds: int = 300  # hard kill (doc default: 5 min)
    sandbox_coordinator_url: str = ""  # e.g. https://sandbox-01.internal:8443
    sandbox_coordinator_token: str = ""
    sandbox_coordinator_verify_tls: bool = True
    sandbox_coordinator_ca_bundle: str = ""  # PEM to pin; see proxmox_ca_bundle
    sandbox_coordinator_timeout_seconds: float = 360.0
    # Static pre-check heuristics: a high-entropy payload reads as packed.
    sandbox_entropy_packed_threshold: float = 7.2

    # Remote lab access (docs/lab-networking.md Layer 2). Lab VMs sit on an
    # isolated tenant VLAN with no route off it, so a student reaches one
    # through an overlay network rather than from the campus LAN. Setting a
    # management URL turns on the "How do I connect?" help the lab page shows
    # beside the endpoint; it is documentation only -- the platform never
    # talks to NetBird, and enrolment is the student's own client.
    # Webhook delivery targets. Subscriptions are created by ordinary users
    # (webhooks:manage is granted to every role), so by default the
    # platform refuses to POST to anything that is not a routable internet
    # address (palestrix/netguard.py) -- otherwise a student's
    # subscription is an SSRF primitive against the lab network, the
    # hypervisor API, and the cloud metadata service. Turn this on only
    # for a site whose collector really is internal.
    allow_private_webhooks: bool = False

    # Rate limits, per minute per caller (0 disables a bucket). These are the
    # numbers docs/public-api.md publishes and the limiter enforces
    # (palestrix/ratelimit.py). "auth" covers the credential endpoints --
    # without it the login form takes unlimited password guesses. Per process,
    # so the edge proxy stays the authoritative limiter for a deployment.
    rate_limit_enabled: bool = True
    rate_limit_general_per_minute: int = 600
    rate_limit_launch_per_minute: int = 60
    rate_limit_flag_per_minute: int = 10
    rate_limit_auth_per_minute: int = 20

    netbird_management_url: str = ""  # e.g. https://netbird.example.edu
    netbird_network_name: str = ""  # friendly name shown in the UI
    netbird_setup_key_url: str = ""  # where a student gets their setup key
    netbird_docs_url: str = "https://docs.netbird.io/how-to/getting-started"
    # The shared, reusable, ephemeral setup key every student joins with. This
    # deployment runs one pseudo-identity for the whole cohort rather than a
    # NetBird user per student, because the free plan caps users at 5; the
    # key's peers are ephemeral and reaped an hour after they go offline, which
    # is what keeps the cohort under the 100-peer cap. It is low-value on its
    # own — it only lets a device *join* an overlay whose policies confine it
    # to the lab route — so the connect modal shows it to a signed-in student
    # directly, turning enrolment into one copy-pasted command.
    netbird_setup_key: str = ""
    # A NetBird API token (PAT), used only by the superadmin NetBird console to
    # read peer status and reap slots by hand. Never sent to the browser. Empty
    # disables the console's live view and the manual reap; the overlay itself
    # keeps working, and native inactivity expiration keeps reaping.
    netbird_api_token: str = ""
    netbird_api_url: str = "https://api.netbird.io/api"
    # The plan's peer ceiling, shown in the console so a superadmin sees how
    # close the cohort is to it. The free plan is 100; this is display only.
    netbird_peer_limit: int = 100

    # The SSH credential a student uses to reach a provisioned lab VM. The
    # platform bakes one shared account into the VM template rather than
    # minting a credential per instance, so this is the same for every lab;
    # the connect modal shows it to a signed-in student beside the ssh line,
    # the way it shows the shared overlay key. Empty password means the modal
    # prints the username and lets the student use whatever the template's own
    # cloud-init set, rather than displaying a blank.
    lab_ssh_username: str = "student"
    lab_ssh_password: str = ""

    # Canvas LMS integration (Phase 8). Setting the issuer + client id
    # activates the adapter (docs/integrations-canvas-lms.md): LTI 1.3
    # launches, NRPS roster sync, AGS grade passback, and Deep Linking 2.0.
    # The endpoint URLs default to Canvas's conventional paths under the
    # issuer; override them only for a nonstandard mount.
    canvas_issuer: str = ""  # e.g. https://canvas.example.edu
    canvas_client_id: str = ""  # the LTI Developer Key's client id
    canvas_deployment_id: str = ""  # optional; checked on launch when set
    canvas_auth_url: str = ""  # default: <issuer>/api/lti/authorize_redirect
    canvas_jwks_url: str = ""  # default: <issuer>/api/lti/security/jwks
    canvas_token_url: str = ""  # default: <issuer>/login/oauth2/token
    # The tool's RS256 signing key (PEM). Empty generates an ephemeral dev
    # key at startup — fine locally, flagged by the production boot guard
    # because Canvas pins the tool JWKS and restarts would rotate it.
    canvas_tool_private_key: str = ""
    canvas_verify_tls: bool = True
    canvas_ca_bundle: str = ""  # PEM to pin; see proxmox_ca_bundle
    canvas_timeout_seconds: float = 20.0
    # Grade passback queue: exponential backoff (2^attempts minutes) until
    # delivered, then marked failed after this many attempts; failures stay
    # visible in the teacher's course view and can be retried manually.
    grade_passback_max_attempts: int = 5

    # Gamification (Phase 3) — the balance rules the service enforces. All
    # earning is student-only (rbac-matrix.md); staff have no earn path.
    #
    # Per-source daily earn caps (0 disables a cap). Anti-abuse: no single
    # source can be farmed past its ceiling in a UTC day.
    palestras_daily_cap_module: int = 500
    palestras_daily_cap_flag: int = 1000
    palestras_daily_cap_writeup: int = 180
    # Flat awards / costs.
    writeup_publish_award_palestras: int = 60
    first_blood_bonus_palestras: int = 25
    streak_weekly_bonus_palestras: int = 100
    hint_cost_palestras: int = 50
    # Flag-capture dynamic scoring: the award decays by `flag_scale_step` for
    # each prior solve, never below `flag_scale_floor` of the base award, so
    # early solves of a hard challenge are worth the most.
    flag_scale_step: float = 0.08
    flag_scale_floor: float = 0.4
    # Community score: contributions fade with a half-life so ranks reward
    # recency (rbac-matrix.md). Each published writeup is worth a base plus its
    # net votes, multiplied by 0.5 ** (age_days / half_life).
    community_score_halflife_days: float = 30.0
    community_writeup_base_points: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()

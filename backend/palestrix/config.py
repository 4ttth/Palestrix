"""Application settings. Every value can come from the environment with the
PALESTRIX_ prefix, or from a .env file next to the working directory."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PALESTRIX_", env_file=".env", extra="ignore"
    )

    database_url: str = "sqlite:///./palestrix.db"
    secret_key: str = "dev-only-secret-change-me"

    # Sessions and tokens
    session_ttl_minutes: int = 12 * 60
    client_token_ttl_minutes: int = 60

    # WebAuthn relying party
    rp_id: str = "localhost"
    rp_name: str = "PalestrIX"
    origin: str = "http://localhost:3000"

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

    # Compete
    flag_cooldown_seconds: int = 30

    # Instances (demo provider until the Phase 4 orchestration adapters land)
    instance_extend_cost_palestras: int = 150
    instance_extend_step_minutes: int = 30

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

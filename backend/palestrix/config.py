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


@lru_cache
def get_settings() -> Settings:
    return Settings()

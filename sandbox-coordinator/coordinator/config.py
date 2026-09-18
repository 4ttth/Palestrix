"""Coordinator settings. Every value can come from the environment with the
SBX_ prefix, or from a .env file next to the working directory."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SBX_", env_file=".env", extra="ignore"
    )

    # The core API sends "Authorization: Bearer <token>". Empty means the
    # service refuses every request rather than running open.
    auth_token: str = ""

    template_vmid: int = 900
    clone_vmid_min: int = 9000
    clone_vmid_max: int = 9099

    bridge: str = "sandbox"
    iso_storage: str = "local"
    iso_storage_path: str = "/var/lib/vz/template/iso"

    boot_grace_seconds: int = 45
    detonation_seconds: int = 180
    max_sample_bytes: int = 64 * 1024 * 1024

    work_dir: str = "/var/lib/palestrix-sandbox"
    capture_enabled: bool = True
    screenshot_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()

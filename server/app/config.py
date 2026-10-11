"""Centralized configuration for the BioUnlock backend.

All values are read from environment variables with a ``BIO_`` prefix or from
a ``server/.env`` file. No secrets are embedded in code.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_RP_ID = "localhost"


def _parse_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return []


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BIO_",
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "development"
    log_level: str = "INFO"

    # Application secrets. ``secret_key`` must be replaced in production. It is
    # not used as a root of trust for the auth protocol (Ed25519 keys are).
    secret_key: str = "development-only-insecure-key-change-me"

    database_url: str = "sqlite:///./biounlock.db"
    data_dir: str = "./data"
    signing_key_path: str | None = None

    # WebAuthn relying party
    rp_id: str = DEFAULT_RP_ID
    rp_name: str = "BioUnlock"
    # Comma separated list of allowed WebAuthn origins (full origins, e.g.
    # "https://app.example.com" or "android:apk-key-hash:..." for native apps).
    allowed_origins: list[str] = [f"http://{DEFAULT_RP_ID}:8000"]

    # CORS origins for browser tooling (not required by native apps).
    cors_origins: list[str] = [f"http://{DEFAULT_RP_ID}:8000"]

    # TTLs (seconds)
    session_ttl_seconds: int = 3600
    challenge_ttl_seconds: int = 120
    pairing_ttl_seconds: int = 300
    auth_request_ttl_seconds: int = 120
    heartbeat_interval_seconds: int = 60
    clock_skew_seconds: int = 30
    pairing_max_attempts: int = 5

    # Security toggles
    rate_limit_enabled: bool = True
    cookie_secure: bool = False

    @field_validator("allowed_origins", "cors_origins", mode="before")
    @classmethod
    def _split_lists(cls, v: object) -> object:
        return _parse_list(v)

    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"

    @property
    def resolved_signing_key_path(self) -> Path:
        if self.signing_key_path:
            return Path(self.signing_key_path)
        return Path(self.data_dir) / "server_signing_key.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()

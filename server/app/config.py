"""Centralized configuration for the BioUnlock backend.

All values are read from environment variables with a ``BIO_`` prefix or from
a ``server/.env`` file. No secrets are embedded in code.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_RP_ID = "localhost"
AUTO_RP_ID = "auto"
DEFAULT_ENVIRONMENT = "production"
DEFAULT_DATABASE_URL = "sqlite:///./biounlock.db"

# Connection strings injected by hosted Postgres integrations (e.g. a database
# connected in Vercel). Used only when BIO_DATABASE_URL is not set. Pooled URLs
# come first because they suit serverless better; direct URLs are the fallback.
_DATABASE_URL_ENV_FALLBACKS = (
    "DATABASE_URL",
    "POSTGRES_URL",
    "DATABASE_URL_UNPOOLED",
    "POSTGRES_URL_NON_POOLING",
    "POSTGRES_PRISMA_URL",
)


def _normalize_postgres_url(url: str) -> str:
    """Point Postgres URLs at the psycopg (v3) driver.

    Providers hand out ``postgres://`` / ``postgresql://``, but SQLAlchemy would
    try to load psycopg2 for those; we install ``psycopg``.
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def _find_integration_database_url() -> str | None:
    """Find a Postgres URL under any ``*DATABASE_URL`` env var.

    Storage integrations prefix their variables with the store name (e.g.
    ``biounlockdb_DATABASE_URL``), so the exact name varies per project.
    """
    candidates = [
        name
        for name, value in os.environ.items()
        if name.upper().endswith("DATABASE_URL")
        and not name.upper().startswith("BIO_")
        and value
        and value.lower().startswith(("postgres://", "postgresql://"))
    ]
    if not candidates:
        return None

    def _rank(name: str) -> int:
        upper = name.upper()
        if "UNPOOLED" in upper or "NON_POOLING" in upper or "NO_SSL" in upper:
            return 2
        if "POOL" in upper:
            return 0
        return 1

    candidates.sort(key=lambda n: (_rank(n), n))
    return os.environ[candidates[0]]


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

    environment: str = DEFAULT_ENVIRONMENT
    log_level: str = "INFO"

    # Shared secret the mobile app presents as ``Authorization: Bearer <token>``
    # on every owner endpoint. The PC agent uses its own signed device
    # credential instead, so it never needs this. Only an explicit test harness
    # may bypass owner-token enforcement.
    api_token: str | None = None

    database_url: str = DEFAULT_DATABASE_URL
    data_dir: str = "./data"

    # Optional path to a Digital Asset Links file served at
    # ``/.well-known/assetlinks.json`` so Android can associate the mobile app
    # with this WebAuthn relying party domain. When unset, a bundled default is
    # served (see :mod:`app.static_assets`).
    asset_links_path: str | None = None

    # WebAuthn relying party
    rp_id: str = AUTO_RP_ID
    rp_name: str = "BioUnlock"
    # Comma separated list of allowed WebAuthn origins (full origins, e.g.
    # "https://app.example.com" or "android:apk-key-hash:..." for native apps).
    allowed_origins: Annotated[list[str], NoDecode] = [f"http://{DEFAULT_RP_ID}:8000"]

    # CORS origins for browser tooling (not required by native apps).
    cors_origins: Annotated[list[str], NoDecode] = [f"http://{DEFAULT_RP_ID}:8000"]

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

    @field_validator("allowed_origins", "cors_origins", mode="before")
    @classmethod
    def _split_lists(cls, v: object) -> object:
        return _parse_list(v)

    @model_validator(mode="after")
    def _resolve_environment(self) -> Settings:
        # Vercel exposes ``VERCEL_ENV`` (production/preview/development). Adopt
        # it so production does not publicly serve the API docs by accident,
        # without requiring a hand-set BIO_ENVIRONMENT.
        if self.environment == DEFAULT_ENVIRONMENT:
            vercel_env = os.environ.get("VERCEL_ENV")
            if vercel_env:
                self.environment = vercel_env
        return self

    @model_validator(mode="after")
    def _resolve_database_url(self) -> Settings:
        url = self.database_url
        # Nothing explicit was configured: adopt a hosted Postgres URL if one of
        # the standard integration env vars is present.
        if url == DEFAULT_DATABASE_URL:
            for name in _DATABASE_URL_ENV_FALLBACKS:
                value = os.environ.get(name)
                if value:
                    url = value
                    break
            else:
                url = _find_integration_database_url() or url
        self.database_url = _normalize_postgres_url(url)
        return self

    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"

@lru_cache
def get_settings() -> Settings:
    return Settings()

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import PostgresDsn, RedisDsn, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


import urllib.parse


def _normalize_db_url(raw: str) -> str:
    """Safely URL-encodes passwords with special characters (like @ or $) in database URLs."""
    if "://" not in raw or "@" not in raw:
        return raw
    scheme, rest = raw.split("://", 1)
    userinfo, hostinfo = rest.rsplit("@", 1)
    if ":" in userinfo:
        user, pwd = userinfo.split(":", 1)
        pwd_encoded = urllib.parse.quote(urllib.parse.unquote(pwd), safe="")
        return f"{scheme}://{user}:{pwd_encoded}@{hostinfo}"
    return raw


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ────────────────────────────────────────────────────────────────
    app_env: Literal["development", "staging", "production"] = "development"
    secret_key: str = "change-me"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # ── Database ───────────────────────────────────────────────────────────
    postgres_user: str = "tbp"
    postgres_password: str = "tbp_secret"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "tbp_db"

    # Optional explicit override — if set it wins over the assembled URL.
    database_url: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def async_database_url(self) -> str:
        """Always returns an asyncpg-compatible URL."""
        if self.database_url:
            raw = _normalize_db_url(str(self.database_url))
            # Ensure the driver is asyncpg
            return raw.replace("postgresql://", "postgresql+asyncpg://", 1).replace(
                "postgres://", "postgresql+asyncpg://", 1
            )
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sync_database_url(self) -> str:
        """psycopg2-compatible URL for Alembic (runs synchronously)."""
        return self.async_database_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    # ── Redis / Celery ─────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def celery_broker_url(self) -> str:
        return self.redis_url

    @computed_field  # type: ignore[prop-decorator]
    @property
    def celery_result_backend(self) -> str:
        return self.redis_url

    # ── External / Affiliate & GSC ─────────────────────────────────────────
    amazon_pa_api_key: str = ""
    amazon_pa_api_secret: str = ""
    amazon_pa_partner_tag: str = ""
    cuelinks_api_key: str = ""
    admitad_api_key: str = ""
    gsc_site_url: str = "sc-domain:thebeautyproject.com"
    gsc_service_account_json: str = ""
    gsc_credentials_file: str = ""

    # ── DCS gate ───────────────────────────────────────────────────────────
    dcs_index_threshold: int = 70  # pages below this score get noindex


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton of Settings."""
    return Settings()

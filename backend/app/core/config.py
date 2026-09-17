"""Application configuration loaded from environment variables.

Config lives outside code (Requirement 13). In production, values are injected
from SSM Parameter Store / Secrets Manager.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # SQLite default for local dev; set DATABASE_URL to a PostgreSQL DSN in production.
    database_url: str = "sqlite:///./planning.db"

    # Comma-separated allowed origins for CORS (Requirement 5.5).
    cors_origins: str = "http://localhost:5173"

    # "dev" trusts an identity header for local work; "cognito" verifies JWTs (Requirement 12).
    auth_mode: str = "dev"

    app_name: str = "Capacity Planning Platform"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

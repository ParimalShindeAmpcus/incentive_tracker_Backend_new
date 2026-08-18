"""Application settings loaded from environment only."""

from functools import lru_cache
from typing import List, Optional
from urllib.parse import quote_plus

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings — env-backed with sensible defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Incentive Tracker API"
    environment: str = "development"
    debug: bool = False

    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # Database (compose URL from parts when DB_NAME is set)
    db_user: Optional[str] = None
    db_password: Optional[str] = None
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: Optional[str] = None
    database_url: Optional[str] = None

    # CORS — comma-separated origins (include both localhost and 127.0.0.1)
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:8080,http://127.0.0.1:8080"
    )

    # Security / JWT
    secret_key: str = "change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_minutes: int = 10080

    # Seed defaults
    default_admin_email: str = "admin@example.com"
    default_admin_password: str = "Admin@123"
    seed_on_startup: bool = True

    # API
    api_v1_prefix: str = "/api/v1"

    # VLOOKUP reconciliation thresholds (identity + client gated)
    threshold_auto_match: float = 88.0
    threshold_suggest: float = 80.0
    threshold_review: float = 70.0
    hours_validation_cap: float = 160.0
    # Configurable confidence weights (renormalized when a signal is absent)
    vlookup_weight_name: float = 0.60
    vlookup_weight_client: float = 0.30
    vlookup_weight_month: float = 0.10
    # Client compatibility bands used by the decision matrix
    vlookup_client_compat_strong: float = 80.0
    vlookup_client_compat_moderate: float = 55.0
    vlookup_client_conflict_max: float = 40.0
    vlookup_strong_name_score: float = 90.0
    vlookup_moderate_name_score: float = 78.0
    vlookup_min_identity_name_score: float = 70.0
    vlookup_ambiguity_gap: float = 8.0

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug_value(cls, value):
        """Accept common deployment labels without preventing API startup."""
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "production", "prod", "off", "no"}:
                return False
            if normalized in {"development", "dev", "debug", "on", "yes"}:
                return True
        return value

    @model_validator(mode="after")
    def assemble_database_url(self):
        if self.db_user and self.db_name:
            password = quote_plus(self.db_password or "")
            object.__setattr__(
                self,
                "database_url",
                (
                    f"postgresql+psycopg2://{self.db_user}:{password}"
                    f"@{self.db_host}:{self.db_port}/{self.db_name}"
                ),
            )
        elif not self.database_url:
            object.__setattr__(self, "database_url", "sqlite:///./incentive_tracker.db")
        return self

    def get_cors_origins(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

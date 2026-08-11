from functools import lru_cache
from typing import List, Optional, Union
from urllib.parse import quote_plus

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_origins(value: Union[str, List[str], None]) -> List[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        import json

        return [str(v).strip() for v in json.loads(text) if str(v).strip()]
    return [v.strip() for v in text.split(",") if v.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str = "development"
    company_domain: Optional[str] = None

    # DeskFlow-style DB parts (preferred when present)
    db_user: Optional[str] = None
    db_password: Optional[str] = None
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: Optional[str] = None

    # Legacy / direct URL (used if DB_* not set)
    database_url: Optional[str] = None

    # Security — accept both SECRET_KEY and JWT_SECRET
    secret_key: Optional[str] = None
    jwt_secret: Optional[str] = None
    algorithm: str = "HS256"
    jwt_algorithm: Optional[str] = None
    access_token_expire_minutes: int = 30
    refresh_token_expire_minutes: int = 60 * 24 * 7
    debug: bool = False

    # Keep as str so pydantic-settings does not JSON-decode comma lists
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    allowed_origins: str = ""

    max_upload_size_mb: int = 50
    allowed_file_types: str = "csv,xlsx,xls"
    app_name: str = "Incentive Tracker"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_reload: bool = True
    app_debug: bool = True
    log_level: str = "WARNING"
    timezone: str = "UTC"

    default_admin_email: str = "admin@example.com"
    default_admin_password: str = "Admin@123"
    seed_on_startup: bool = True
    api_v1_prefix: str = "/api/v1"

    @model_validator(mode="after")
    def assemble_settings(self):
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

        if self.secret_key and not self.jwt_secret:
            object.__setattr__(self, "jwt_secret", self.secret_key)
        if not self.jwt_secret:
            object.__setattr__(self, "jwt_secret", "change-me")

        if self.jwt_algorithm is None:
            object.__setattr__(self, "jwt_algorithm", self.algorithm)

        return self

    def get_cors_origins(self) -> List[str]:
        origins = _split_origins(self.cors_origins)
        if origins:
            return origins
        return _split_origins(self.allowed_origins)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def is_sqlite(self) -> bool:
        return bool(self.database_url and self.database_url.startswith("sqlite"))


@lru_cache
def get_settings() -> Settings:
    return Settings()

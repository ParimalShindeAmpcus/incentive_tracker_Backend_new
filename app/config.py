"""Application settings loaded from environment only."""

from functools import lru_cache
from typing import List, Optional
from urllib.parse import quote_plus

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Empty/minimal settings stub — populate fields as features are added."""

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

    # CORS — comma-separated origins
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Security placeholders
    secret_key: str = "change-me"

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

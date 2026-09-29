from urllib.parse import quote_plus

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Recruitment MIS Incentive Tracker"
    APP_VERSION: str = "0.1.0"

    DB_HOST: str = Field(default="localhost", validation_alias=AliasChoices("MIS_DB_HOST", "DB_HOST"))
    DB_USER: str = Field(default="postgres", validation_alias=AliasChoices("MIS_DB_USER", "DB_USER"))
    DB_NAME: str = Field(default="mis_prism_db", validation_alias=AliasChoices("MIS_DB_NAME", "DB_NAME"))
    PASSWORD: str = Field(default="postgres", validation_alias=AliasChoices("MIS_DB_PASSWORD", "PASSWORD", "DB_PASSWORD"))
    PORT: int = Field(default=5432, validation_alias=AliasChoices("MIS_DB_PORT", "PORT", "DB_PORT"))
    DATABASE_URL: str | None = Field(default=None, validation_alias=AliasChoices("MIS_DATABASE_URL", "DATABASE_URL"))
    MIS_DB_SCHEMA: str = Field(default="mis", validation_alias=AliasChoices("MIS_DB_SCHEMA", "DB_SCHEMA"))

    REDIS_URL: str = "redis://localhost:6379/0"
    CORS_ORIGINS: str = (
        "http://localhost:5173,http://localhost:3000,"
        "http://localhost:8080,http://127.0.0.1:8080"
    )
    JOBDIVA_API_BASE_URL: str = ""
    JOBDIVA_API_KEY: str = ""

    # Auth / JWT
    JWT_SECRET_KEY: str = Field(default="dev-secret-key-mis-prism-shared-2026-min-32-chars", min_length=32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 hours
    AUTH_COOKIE_NAME: str = "mis_session"
    AUTH_COOKIE_SECURE: bool = False
    AUTH_COOKIE_SAMESITE: str = "lax"
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_LOGIN_MAX: int = 10
    RATE_LIMIT_RESET_MAX: int = 5
    ENABLE_API_DOCS: bool = False

    # IMAP & Email Ingestion Settings
    IMAP_SERVER: str = "imap.gmail.com"
    IMAP_PORT: int = 993
    IMAP_EMAIL: str = ""
    IMAP_PASSWORD: str = ""
    IMAP_INBOX_FOLDER: str = Field(default="INBOX", validation_alias=AliasChoices("IMAP_INBOX_FOLDER", "INBOX_FOLDER"))
    IMAP_PROCESSED_FOLDER: str = Field(default="Processed", validation_alias=AliasChoices("IMAP_PROCESSED_FOLDER", "PROCESSED_FOLDER"))
    IMAP_FAILED_FOLDER: str = Field(default="Failed", validation_alias=AliasChoices("IMAP_FAILED_FOLDER", "FAILED_FOLDER"))
    IMAP_SENDER_FILTER: str = Field(default="", validation_alias=AliasChoices("IMAP_SENDER_FILTER", "SENDER_FILTER"))
    ATTACHMENT_TEMP_DIR: str = Field(default="temp", validation_alias=AliasChoices("ATTACHMENT_TEMP_DIR", "TEMP_DIR"))
    TARGET_TABLE_NAME: str = "imported_jobdiva_records"

    # Automated Background Ingestion Scheduler
    EMAIL_INGESTION_ENABLED: bool = Field(default=True, validation_alias=AliasChoices("EMAIL_INGESTION_ENABLED", "ENABLE_EMAIL_INGESTION"))
    EMAIL_INGESTION_INTERVAL_MINUTES: int = Field(default=30, validation_alias=AliasChoices("EMAIL_INGESTION_INTERVAL_MINUTES", "INGESTION_INTERVAL_MINUTES"))

    # SMTP (outbound email — password reset, notifications)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "Starts MIS"
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False

    # Password reset / invitation flow
    FRONTEND_BASE_URL: str = "http://localhost:8080"
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 15
    INVITATION_TOKEN_EXPIRE_HOURS: int = 48


    @model_validator(mode="after")
    def build_database_url(self) -> "Settings":
        if self.JWT_SECRET_KEY == "change-me-in-production-use-a-long-random-string":
            raise ValueError("JWT_SECRET_KEY must be set to a unique random value")
        if not self.DATABASE_URL:
            password = quote_plus(self.PASSWORD or "postgres")
            db_name = self.DB_NAME or "ms"
            host = self.DB_HOST or "localhost"
            port = self.PORT or 5432
            user = self.DB_USER or "postgres"
            self.DATABASE_URL = (
                f"postgresql+asyncpg://{user}:{password}"
                f"@{host}:{port}/{db_name}"
            )
        return self

    @property
    def sync_database_url(self) -> str:
        """psycopg2-compatible URL for scripts / sync sessions."""
        assert self.DATABASE_URL is not None
        return (
            self.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
            .replace("postgresql+psycopg2://", "postgresql://")
        )

    @property
    def smtp_username(self) -> str:
        """SMTP login user; falls back to IMAP email when SMTP username is unset."""
        return (self.SMTP_USERNAME or self.IMAP_EMAIL).strip()

    @property
    def smtp_password(self) -> str:
        """SMTP password with spaces stripped (Gmail app passwords are often pasted with spaces)."""
        raw = self.SMTP_PASSWORD or self.IMAP_PASSWORD
        return raw.replace(" ", "").strip()

    @property
    def smtp_from_email(self) -> str:
        """Envelope/from address. For Gmail, must match the authenticated mailbox."""
        username = self.smtp_username
        explicit = self.SMTP_FROM_EMAIL.strip()
        if not explicit:
            return username
        if "gmail.com" in self.SMTP_HOST.lower() and explicit.lower() != username.lower():
            return username
        return explicit

    @property
    def smtp_is_ready(self) -> bool:
        return bool(self.SMTP_HOST and self.smtp_username and self.smtp_password and self.smtp_from_email)


settings = Settings()

"""Database connection / query helpers."""

from typing import Generator, Optional

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

_engine = None
_SessionLocal: Optional[sessionmaker] = None


class Base(DeclarativeBase):
    pass


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(settings.database_url, pool_pre_ping=True)
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _engine


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency stub for DB sessions."""
    get_engine()
    assert _SessionLocal is not None
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Import all ORM entities and create tables."""
    import app.repositories.entities  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    # create_all does not alter existing tables — add columns introduced after first create.
    inspector = inspect(engine)
    dialect = engine.dialect.name
    is_pg = dialect == "postgresql"

    def _add_missing(table: str, additions: dict[str, str]) -> None:
        if table not in inspector.get_table_names():
            return
        existing = {column["name"] for column in inspector.get_columns(table)}
        missing = {name: ddl for name, ddl in additions.items() if name not in existing}
        if not missing:
            return
        with engine.begin() as connection:
            for name, ddl in missing.items():
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))

    ts = "TIMESTAMP WITH TIME ZONE" if is_pg else "DATETIME"
    bool_type = "BOOLEAN" if is_pg else "BOOLEAN"
    _add_missing(
        "incentive_cycles",
        {"approved_at": ts},
    )
    _add_missing(
        "candidates",
        {
            "activity_id": "VARCHAR(100)",
            "start_id": "VARCHAR(100)",
            "email": "VARCHAR(255)",
            "end_client": "VARCHAR(255)",
            "markup_percent": "NUMERIC(12, 4)",
            "finders_fee": "NUMERIC(14, 2)",
            "onboarding_coordinator": "VARCHAR(255)",
            "placement_level": "VARCHAR(50)",
            "incentive_active": f"{bool_type} DEFAULT TRUE NOT NULL",
            "inactivation_reason": "VARCHAR(500)",
        },
    )
    if "candidates" in inspector.get_table_names():
        with engine.begin() as connection:
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_candidates_activity_id ON candidates (activity_id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_candidates_start_id ON candidates (start_id)"))
    _add_missing(
        "coordinator_records",
        {
            "start_date": "DATE",
            "is_deleted": f"{bool_type} DEFAULT FALSE NOT NULL",
        },
    )
    # AuditLog model gained title / user_display / username / metadata after the table was first created.
    json_type = "JSONB" if is_pg else "JSON"
    _add_missing(
        "audit_logs",
        {
            "title": "VARCHAR(255) NOT NULL DEFAULT ''",
            "user_display": "VARCHAR(255) NOT NULL DEFAULT ''",
            "username": "VARCHAR(255) NOT NULL DEFAULT ''",
            "metadata": json_type,
        },
    )
    # Model uses native_enum=False (VARCHAR(50)); older DBs used PG enum audit_action_enum.
    if is_pg and "audit_logs" in inspector.get_table_names():
        with engine.begin() as connection:
            action_meta = connection.execute(
                text(
                    """
                    SELECT data_type, udt_name, character_maximum_length
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'audit_logs'
                      AND column_name = 'action'
                    """
                )
            ).mappings().first()
            if action_meta is not None:
                data_type = action_meta["data_type"]
                udt_name = action_meta["udt_name"]
                max_len = action_meta["character_maximum_length"]
                if data_type == "USER-DEFINED" or udt_name == "audit_action_enum":
                    connection.execute(
                        text(
                            "ALTER TABLE audit_logs "
                            "ALTER COLUMN action TYPE VARCHAR(50) USING action::text"
                        )
                    )
                    # Drop orphaned enum type when nothing else depends on it.
                    still_used = connection.execute(
                        text(
                            """
                            SELECT 1
                            FROM information_schema.columns
                            WHERE udt_name = 'audit_action_enum'
                            LIMIT 1
                            """
                        )
                    ).first()
                    if still_used is None:
                        connection.execute(text("DROP TYPE IF EXISTS audit_action_enum"))
                elif max_len is not None and int(max_len) < 50:
                    connection.execute(
                        text("ALTER TABLE audit_logs ALTER COLUMN action TYPE VARCHAR(50)")
                    )

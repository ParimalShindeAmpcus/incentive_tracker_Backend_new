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

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

    # create_all does not alter existing tables. Repair databases that predate
    # the approval timestamp used by the dashboard and cycle approval flow.
    inspector = inspect(engine)
    if "incentive_cycles" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("incentive_cycles")}
        if "approved_at" not in columns:
            column_type = "TIMESTAMP WITH TIME ZONE" if engine.dialect.name == "postgresql" else "DATETIME"
            with engine.begin() as connection:
                connection.execute(text(f"ALTER TABLE incentive_cycles ADD COLUMN approved_at {column_type}"))

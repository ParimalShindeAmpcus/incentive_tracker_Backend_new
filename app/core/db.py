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
            "contact": "VARCHAR(50)",
            "subcontractor_contact": "VARCHAR(50)",
            "end_client": "VARCHAR(255)",
            # Older local PostgreSQL databases predate the expanded candidate
            # master. Keep startup additive so a cycle request never fails
            # merely because a persisted development database is behind code.
            "normalized_client": "VARCHAR(255)",
            "job_title": "VARCHAR(255)",
            "end_date": "DATE",
            "req_id": "VARCHAR(100)",
            "contract_type": "VARCHAR(50)",
            "subcontractor": "VARCHAR(255)",
            "subcontractor_email": "VARCHAR(255)",
            "job_level": "VARCHAR(100)",
            "salary": "NUMERIC(14, 2)",
            "pay_rate": "NUMERIC(12, 4)",
            "taxes": "NUMERIC(12, 4)",
            "benefits": "NUMERIC(12, 4)",
            "referral_fee": "NUMERIC(14, 2)",
            "finders_fee": "NUMERIC(14, 2)",
            "bill_rate": "NUMERIC(12, 4)",
            "msp_fee": "NUMERIC(12, 4)",
            "margin": "NUMERIC(12, 4)",
            "remote": "VARCHAR(20)",
            "work_location": "VARCHAR(255)",
            "candidate_location": "VARCHAR(255)",
            "work_authorization": "VARCHAR(100)",
            "candidate_source": "VARCHAR(255)",
            "team_lead": "VARCHAR(255)",
            "crm": "VARCHAR(255)",
            "manager": "VARCHAR(255)",
            "head_of_department": "VARCHAR(255)",
            "senior_manager": "VARCHAR(255)",
            "associate_director": "VARCHAR(255)",
            "director": "VARCHAR(255)",
            "center_head": "VARCHAR(255)",
            "avp": "VARCHAR(255)",
            "organization": "VARCHAR(255)",
            "user_email": "VARCHAR(255)",
            "recruiter_location": "VARCHAR(255)",
            "recruiter": "VARCHAR(255)",
            "status": "VARCHAR(100)",
            "markup_percent": "NUMERIC(12, 4)",
            "approved_markup_percentage": "NUMERIC(12, 4)",
            "ownership_confirmed": f"{bool_type} DEFAULT FALSE NOT NULL",
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
    _add_missing(
        "cycle_payment_statuses",
        {
            "payment_received_date": "DATE",
            "payment_reference": "VARCHAR(255)",
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
    _add_missing(
        "vlookup_upload_batches",
        {
            "file_type": "VARCHAR(40)",
            "filename": "VARCHAR(255)",
            "total_records": "INTEGER",
            "status": "VARCHAR(20)",
            "error_message": "TEXT",
            "matched_count": "INTEGER DEFAULT 0",
            "needs_review_count": "INTEGER DEFAULT 0",
            "unmatched_count": "INTEGER DEFAULT 0",
            "duplicate_count": "INTEGER DEFAULT 0",
            "conflicting_count": "INTEGER DEFAULT 0",
            "target_month": "VARCHAR(20)",
            "client_file_format": "VARCHAR(50)",
            "parser_warnings": json_type,
            "uploaded_by": "VARCHAR(255)",
            "stage": "VARCHAR(40)",
            "cycle_id": "INTEGER",
            "cancelled_by": "VARCHAR(255)",
            "cancelled_at": ts,
            "resume_state": json_type,
            "completed_at": ts,
        },
    )

    def _sync_mapped_columns() -> None:
        """Add any other model columns that create_all skipped on existing tables."""
        inspector.clear_cache()
        existing_tables = set(inspector.get_table_names())
        with engine.begin() as connection:
            for table in Base.metadata.sorted_tables:
                if table.name not in existing_tables:
                    continue
                present = {column["name"] for column in inspector.get_columns(table.name)}
                for column in table.columns:
                    if column.name in present or column.primary_key:
                        continue
                    compiled = column.type.compile(dialect=engine.dialect)
                    if_not_exists = "IF NOT EXISTS " if is_pg else ""
                    connection.execute(
                        text(
                            f"ALTER TABLE {table.name} ADD COLUMN {if_not_exists}{column.name} {compiled}"
                        )
                    )
                    present.add(column.name)

    _sync_mapped_columns()
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

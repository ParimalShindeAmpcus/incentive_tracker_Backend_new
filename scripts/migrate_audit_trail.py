"""One-time migration for audit_logs frontend alignment."""

from sqlalchemy import text

from app.core.db import get_engine


MIGRATION_STATEMENTS = [
    "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS title VARCHAR(255) NOT NULL DEFAULT ''",
    "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS user_display VARCHAR(255) NOT NULL DEFAULT ''",
    "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS username VARCHAR(255) NOT NULL DEFAULT ''",
    "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS metadata JSONB",
    """
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'audit_logs'
              AND column_name = 'action'
              AND udt_name = 'audit_action_enum'
        ) THEN
            ALTER TABLE audit_logs ALTER COLUMN action TYPE VARCHAR(50) USING action::text;
            DROP TYPE IF EXISTS audit_action_enum;
        END IF;
    END $$;
    """,
]


def migrate() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        for statement in MIGRATION_STATEMENTS:
            conn.execute(text(statement))
    print("Audit trail migration completed.")


if __name__ == "__main__":
    migrate()

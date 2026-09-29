"""Create the initial MIS schema without replacing an existing schema."""
from pathlib import Path

from alembic import op
from sqlalchemy import inspect

revision = "20260730_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This project predates Alembic. Existing installations already have the
    # core tables and must be adopted without recreating or clearing them.
    if inspect(op.get_bind()).has_table("organizations"):
        return
    schema = Path(__file__).resolve().parents[2] / "sql" / "001_schema.sql"
    op.execute(schema.read_text(encoding="utf-8"))


def downgrade() -> None:
    # Deliberately non-destructive: the baseline may represent an adopted DB.
    pass

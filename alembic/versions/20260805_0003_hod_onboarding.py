"""Add HOD/onboarding workflow schema and mappings."""
from pathlib import Path

from alembic import op

revision = "20260805_0003"
down_revision = "20260731_0002"
branch_labels = None
depends_on = None


def _run_sql_file(name: str) -> None:
    path = Path(__file__).resolve().parents[2] / "sql" / name
    op.execute(path.read_text(encoding="utf-8"))


def upgrade() -> None:
    _run_sql_file("005_hod_onboarding.sql")
    _run_sql_file("006_onboarding_org_aliases.sql")


def downgrade() -> None:
    # Preserve user assignments, mappings, and onboarding records.
    pass

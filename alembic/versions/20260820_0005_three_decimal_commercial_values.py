"""Allow three decimal places for candidate-start commercial values."""

from alembic import op


revision = "20260820_0005"
down_revision = "20260806_0004"
branch_labels = None
depends_on = None


_COLUMNS = (
    "salary",
    "pay_rate",
    "taxes",
    "benefits",
    "referral_fee",
    "gross_bill_rate",
    "msp_fee",
    "margin",
)


def upgrade() -> None:
    for column in _COLUMNS:
        op.execute(
            f"ALTER TABLE candidate_start ALTER COLUMN {column} TYPE NUMERIC(15,3)"
        )


def downgrade() -> None:
    for column in _COLUMNS:
        op.execute(
            f"ALTER TABLE candidate_start ALTER COLUMN {column} TYPE NUMERIC(14,2)"
        )

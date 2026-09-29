"""Add Taxes/Admin/Payroll Charges master-data values."""

from alembic import op


revision = "20260806_0004"
down_revision = "20260805_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO dropdown_master (category, value, display_order, is_active)
        VALUES
            ('TAXES_ADMIN_PAYROLL_CHARGES', '0', 1, TRUE),
            ('TAXES_ADMIN_PAYROLL_CHARGES', '5', 2, TRUE),
            ('TAXES_ADMIN_PAYROLL_CHARGES', '15.4', 3, TRUE),
            ('TAXES_ADMIN_PAYROLL_CHARGES', '20.4', 4, TRUE)
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM dropdown_master
        WHERE category = 'TAXES_ADMIN_PAYROLL_CHARGES'
          AND value IN ('0', '5', '15.4', '20.4')
        """
    )

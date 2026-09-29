"""make submission_manager_id nullable

Revision ID: e9a4d1979cab
Revises: 20260820_0005
Create Date: 2026-09-21 13:48:53.268495
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e9a4d1979cab'
down_revision: Union[str, None] = '20260820_0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('candidate_start', 'submission_manager_id',
               existing_type=sa.BIGINT(),
               nullable=True)


def downgrade() -> None:
    op.alter_column('candidate_start', 'submission_manager_id',
               existing_type=sa.BIGINT(),
               nullable=False)

"""add arch rule status and source

Revision ID: 0a9f2d6d5c31
Revises: 6e4e84c5c8b8
Create Date: 2026-06-01 23:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0a9f2d6d5c31"
down_revision: Union[str, Sequence[str], None] = "6e4e84c5c8b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("arch_rules", sa.Column("status", sa.String(), nullable=True))
    op.add_column("arch_rules", sa.Column("source", sa.String(), nullable=True))
    op.execute("UPDATE arch_rules SET status = 'approved' WHERE status IS NULL")
    op.execute("UPDATE arch_rules SET source = 'manual' WHERE source IS NULL")
    op.alter_column("arch_rules", "status", existing_type=sa.String(), nullable=False)
    op.alter_column("arch_rules", "source", existing_type=sa.String(), nullable=False)


def downgrade() -> None:
    op.drop_column("arch_rules", "source")
    op.drop_column("arch_rules", "status")
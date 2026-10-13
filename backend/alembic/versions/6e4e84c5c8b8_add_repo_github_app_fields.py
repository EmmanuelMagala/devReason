"""add repo github app fields

Revision ID: 6e4e84c5c8b8
Revises: 1e50b9ac80eb
Create Date: 2026-05-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6e4e84c5c8b8"
down_revision: Union[str, Sequence[str], None] = "1e50b9ac80eb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("repos", sa.Column("github_installation_id", sa.BigInteger(), nullable=True))
    op.add_column("repos", sa.Column("github_repo_id", sa.BigInteger(), nullable=True))
    op.alter_column("repos", "github_token_enc", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    op.alter_column("repos", "github_token_enc", existing_type=sa.Text(), nullable=False)
    op.drop_column("repos", "github_repo_id")
    op.drop_column("repos", "github_installation_id")
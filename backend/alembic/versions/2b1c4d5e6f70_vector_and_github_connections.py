"""Reproducible vectors and verified GitHub connections."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '2b1c4d5e6f70'
down_revision = '0a9f2d6d5c31'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.execute('ALTER TABLE arch_rules ADD COLUMN IF NOT EXISTS embedding vector(1536)')
    op.create_table('github_connections',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('clerk_user_id', sa.String(), sa.ForeignKey('users.clerk_user_id', ondelete='CASCADE'), nullable=False),
        sa.Column('github_user_id', sa.BigInteger(), nullable=False),
        sa.Column('login', sa.String(), nullable=False),
        sa.Column('avatar_url', sa.Text()),
        sa.Column('access_token_enc', sa.Text(), nullable=False),
        sa.Column('refresh_token_enc', sa.Text()),
        sa.Column('expires_at', sa.DateTime(timezone=True)),
        sa.Column('refresh_expires_at', sa.DateTime(timezone=True)),
        sa.Column('status', sa.String(), nullable=False, server_default='connected'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('clerk_user_id', 'github_user_id'))
    op.create_table('github_installations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('connection_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('github_connections.id', ondelete='CASCADE'), nullable=False),
        sa.Column('installation_id', sa.BigInteger(), nullable=False),
        sa.Column('account_login', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='connected'),
        sa.UniqueConstraint('connection_id', 'installation_id'))


def downgrade():
    op.drop_table('github_installations')
    op.drop_table('github_connections')
    # Keep the vector column: it may predate this migration and contain user data.

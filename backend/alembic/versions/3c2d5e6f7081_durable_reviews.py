"""Durable jobs, immutable targets and recoverable results."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision='3c2d5e6f7081'
down_revision='2b1c4d5e6f70'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('repos',sa.Column('details',postgresql.JSONB(),nullable=True))
    op.alter_column('reviews','pr_url',nullable=True)
    op.alter_column('reviews','pr_number',nullable=True)
    op.alter_column('findings','pr_number',nullable=True)
    for name,type_,default in [('mode',sa.String(),'pr'),('branch',sa.String(),None),('commit_sha',sa.String(),None),('title',sa.String(),None),('scope',postgresql.JSONB(),None),('coverage',postgresql.JSONB(),None),('check_outcomes',postgresql.JSONB(),None),('recommendation',sa.String(),None),('posting_status',sa.String(),'not_requested')]:
        op.add_column('reviews',sa.Column(name,type_,nullable=default is None,server_default=default))
    op.create_table('review_jobs',
        sa.Column('id',postgresql.UUID(as_uuid=True),primary_key=True),
        sa.Column('review_id',postgresql.UUID(as_uuid=True),sa.ForeignKey('reviews.id',ondelete='CASCADE'),nullable=False,unique=True),
        sa.Column('clerk_user_id',sa.String(),sa.ForeignKey('users.clerk_user_id'),nullable=False),
        sa.Column('request_key',sa.String(),nullable=False),
        sa.Column('status',sa.String(),nullable=False,server_default='pending'),
        sa.Column('attempts',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('lease_token',sa.String()),sa.Column('lease_until',sa.DateTime(timezone=True)),
        sa.Column('cancel_requested',sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now()),
        sa.UniqueConstraint('clerk_user_id','request_key'))
    op.create_index('ix_review_jobs_status','review_jobs',['status'])
    op.create_table('review_cache',sa.Column('key',sa.String(),primary_key=True),sa.Column('repo_id',postgresql.UUID(as_uuid=True),sa.ForeignKey('repos.id',ondelete='CASCADE'),nullable=False),sa.Column('payload',postgresql.JSONB(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now()))


def downgrade():
    op.drop_table('review_cache'); op.drop_table('review_jobs')
    for name in ('mode','branch','commit_sha','title','scope','coverage','check_outcomes','recommendation','posting_status'): op.drop_column('reviews',name)
    # Nullable legacy columns remain nullable to preserve existing snapshot records.

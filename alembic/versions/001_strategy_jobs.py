from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '001_strategy_jobs'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'strategy_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default='queued'),
        sa.Column('current_step', sa.Text()),
        sa.Column('last_completed_step', sa.Text()),
        sa.Column('lock_key', postgresql.UUID(as_uuid=True)),
        sa.Column('is_locked', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_retries', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('error_message', sa.Text()),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
        sa.Column('started_at', sa.TIMESTAMP()),
        sa.Column('completed_at', sa.TIMESTAMP()),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_strategy_jobs_project', 'strategy_jobs', ['project_id'])
    op.create_index('idx_strategy_jobs_status', 'strategy_jobs', ['status'])


def downgrade():
    op.drop_index('idx_strategy_jobs_status', table_name='strategy_jobs')
    op.drop_index('idx_strategy_jobs_project', table_name='strategy_jobs')
    op.drop_table('strategy_jobs')

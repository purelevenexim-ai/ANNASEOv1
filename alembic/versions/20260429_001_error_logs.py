"""Add error_logs table

Revision ID: 20260429_001
Revises: 20260403_001
Create Date: 2026-04-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260429_001'
down_revision = '20260403_001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'error_logs',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('trace_id', sa.String(length=64), nullable=True),
        sa.Column('job_id', sa.String(length=64), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('level', sa.String(length=20), nullable=False, default='error'),
        sa.Column('source', sa.String(length=20), nullable=True),
        sa.Column('type', sa.String(length=50), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('stack_trace', sa.Text(), nullable=True),
        sa.Column('status_code', sa.Integer(), nullable=True),
        sa.Column('endpoint', sa.String(length=255), nullable=True),
        sa.Column('method', sa.String(length=12), nullable=True),
        sa.Column('user_id', sa.String(length=128), nullable=True),
        sa.Column('session_id', sa.String(length=128), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('error_hash', sa.String(length=128), nullable=False, index=True),
        sa.Column('occurrences', sa.Integer(), nullable=False, default=1),
        sa.Column('first_seen', sa.DateTime(), nullable=False),
        sa.Column('last_seen', sa.DateTime(), nullable=False),
        sa.Column('resolved', sa.Boolean(), nullable=False, default=False),
    )


def downgrade():
    op.drop_table('error_logs')

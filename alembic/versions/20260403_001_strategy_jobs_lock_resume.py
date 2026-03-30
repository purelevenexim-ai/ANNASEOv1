"""Add lock and resume columns to strategy_jobs

Revision ID: 20260403_001
Revises: 20260402_001
Create Date: 2026-03-27
"""
from alembic import op
import sqlalchemy as sa

revision = "20260403_001"
down_revision = "20260402_001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("strategy_jobs", sa.Column("lock_key", sa.String(), nullable=True))
    op.add_column("strategy_jobs", sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.sql.expression.false()))
    op.add_column("strategy_jobs", sa.Column("last_completed_step", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("strategy_jobs", "last_completed_step")
    op.drop_column("strategy_jobs", "is_locked")
    op.drop_column("strategy_jobs", "lock_key")

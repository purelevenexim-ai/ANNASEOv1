"""Add strategy_jobs and serp_cache tables

Revision ID: 20260402_001
Revises: 20260401_001
Create Date: 2026-04-02
"""
from alembic import op
import sqlalchemy as sa

revision = "20260402_001"
down_revision = "20260401_001"
branch_labels = None
depends_on = None


def upgrade():
    # strategy_jobs: core orchestration table
    op.create_table(
        "strategy_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("progress", sa.Integer, nullable=False, server_default="0"),
        sa.Column("current_step", sa.String(), nullable=True),
        sa.Column("input_payload", sa.JSON(), nullable=True),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
    )

    op.create_index("ix_strategy_jobs_project", "strategy_jobs", ["project_id"])
    op.create_index("ix_strategy_jobs_status", "strategy_jobs", ["status"])

    # serp_cache: cache of SERP responses (JSONB/JSON)
    op.create_table(
        "serp_cache",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("device", sa.String(), nullable=True),
        sa.Column("results", sa.JSON(), nullable=True),
        sa.Column("hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    # indexes and uniqueness
    op.create_index("ix_serp_cache_query", "serp_cache", ["query"])
    op.create_index("ix_serp_cache_hash", "serp_cache", ["hash"], unique=True)


def downgrade():
    op.drop_index("ix_serp_cache_hash", table_name="serp_cache")
    op.drop_index("ix_serp_cache_query", table_name="serp_cache")
    op.drop_table("serp_cache")

    op.drop_index("ix_strategy_jobs_status", table_name="strategy_jobs")
    op.drop_index("ix_strategy_jobs_project", table_name="strategy_jobs")
    op.drop_table("strategy_jobs")

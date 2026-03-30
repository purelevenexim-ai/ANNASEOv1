"""Full schema — all 35+ tables from DATA_MODELS.md

Revision ID: 20260401_001
Revises: 0001
Create Date: 2026-04-01
"""
from alembic import op

revision = "20260401_001"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    # Schema already created by 0001 migration; no-op for compatibility.
    pass


def downgrade():
    # No-op; downgrade is handled by 0001 migrations.
    pass

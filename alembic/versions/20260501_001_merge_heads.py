"""Merge Alembic heads: 002_serp_cache_keyword_rankings & 20260429_001

Revision ID: 20260501_001
Revises: 002_serp_cache_keyword_rankings, 20260429_001
Create Date: 2026-05-01
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260501_001"
down_revision = ("002_serp_cache_keyword_rankings", "20260429_001")
branch_labels = None
depends_on = None


def upgrade():
    # This is a merge-only revision; no schema changes required.
    pass


def downgrade():
    # No-op downgrade for merge revision.
    pass

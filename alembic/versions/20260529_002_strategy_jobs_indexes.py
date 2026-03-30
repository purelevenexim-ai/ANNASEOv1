"""create missing strategy_jobs ix_ indexes

Revision ID: 20260529_002
Revises: 20260529_001
Create Date: 2026-03-29
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260529_002"
down_revision = "20260529_001"
branch_labels = None
depends_on = None


def upgrade():
    # create canonical ix_ indexes expected by tests (non-fatal if already present)
    op.execute("CREATE INDEX IF NOT EXISTS ix_strategy_jobs_project ON strategy_jobs(project_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_strategy_jobs_status ON strategy_jobs(status)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_strategy_jobs_project")
    op.execute("DROP INDEX IF EXISTS ix_strategy_jobs_status")

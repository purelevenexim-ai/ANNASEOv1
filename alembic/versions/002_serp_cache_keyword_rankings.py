from alembic import op
import sqlalchemy as sa

tip_revision = '001_strategy_jobs'
revision = '002_serp_cache_keyword_rankings'
down_revision = '001_strategy_jobs'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'serp_cache',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('keyword', sa.Text, nullable=False),
        sa.Column('location', sa.Text),
        sa.Column('device', sa.Text, server_default='desktop'),
        sa.Column('results_json', sa.JSON, nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.UniqueConstraint('keyword', 'location', 'device', name='uq_serp_cache_keyword_location_device')
    )

    op.create_table(
        'keyword_rankings',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('project_id', sa.String, nullable=False),
        sa.Column('keyword', sa.Text, nullable=False),
        sa.Column('current_rank', sa.Integer),
        sa.Column('predicted_rank', sa.Integer),
        sa.Column('probability_score', sa.Float),
        sa.Column('difficulty_score', sa.Float),
        sa.Column('opportunity_score', sa.Float),
        sa.Column('last_updated', sa.TIMESTAMP(), server_default=sa.func.now()),
    )
    op.create_index('idx_keyword_project', 'keyword_rankings', ['project_id'])


def downgrade():
    op.drop_index('idx_keyword_project', table_name='keyword_rankings')
    op.drop_table('keyword_rankings')
    op.drop_table('serp_cache')

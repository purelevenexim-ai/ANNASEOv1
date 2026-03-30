"""create serp_cache table

Revision ID: 20260529_001
Revises: 20260501_001
Create Date: 2026-03-29
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260529_001"
down_revision = "20260501_001"
branch_labels = None
depends_on = None


def upgrade():
    # Use IF NOT EXISTS to be safe when the table may have been created manually
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS serp_cache (
            id VARCHAR(36) PRIMARY KEY,
            query TEXT NOT NULL,
            results JSONB NOT NULL,
            hash TEXT,
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL
        )
        """
    )
    # Ensure compatibility with older table shapes: add missing columns and
    # backfill `query` from legacy `keyword` column if present, then create
    # indexes only when the target columns exist.
    op.execute(
        """
        DO $$
        BEGIN
            -- add query column and backfill from keyword if necessary
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='serp_cache' AND column_name='query'
            ) THEN
                ALTER TABLE serp_cache ADD COLUMN query TEXT;
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='serp_cache' AND column_name='keyword'
                ) THEN
                    UPDATE serp_cache SET query = keyword WHERE query IS NULL;
                END IF;
            END IF;

            -- add id column if missing (non-intrusive backfill for tests)
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='serp_cache' AND column_name='id'
            ) THEN
                ALTER TABLE serp_cache ADD COLUMN id VARCHAR(36);
                -- attempt a simple backfill using md5 of query/results
                UPDATE serp_cache SET id = substring(md5(coalesce(query, results::text)) from 1 for 36) WHERE id IS NULL;
            END IF;

            -- add results column if missing
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='serp_cache' AND column_name='results'
            ) THEN
                ALTER TABLE serp_cache ADD COLUMN results JSONB;
            END IF;

            -- add hash column if missing
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='serp_cache' AND column_name='hash'
            ) THEN
                ALTER TABLE serp_cache ADD COLUMN hash TEXT;
            END IF;

            -- create indexes only when columns exist
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='serp_cache' AND column_name='query'
            ) THEN
                IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE tablename='serp_cache' AND indexname='ix_serp_cache_query') THEN
                    CREATE INDEX ix_serp_cache_query ON serp_cache(query);
                END IF;
            END IF;

            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='serp_cache' AND column_name='hash'
            ) THEN
                IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE tablename='serp_cache' AND indexname='ix_serp_cache_hash') THEN
                    CREATE INDEX ix_serp_cache_hash ON serp_cache(hash);
                END IF;
            END IF;
        END$$;
        """
    )


def downgrade():
    op.drop_index("ix_serp_cache_hash", table_name="serp_cache")
    op.drop_index("ix_serp_cache_query", table_name="serp_cache")
    op.drop_table("serp_cache")

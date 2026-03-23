"""Initial AnnaSEO schema — all tables

Revision ID: 0001
Revises: 
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None

def upgrade():
    # Auth
    op.create_table("users",
        sa.Column("user_id",    sa.String, primary_key=True),
        sa.Column("email",      sa.String, nullable=False, unique=True),
        sa.Column("name",       sa.String, default=""),
        sa.Column("role",       sa.String, default="user"),
        sa.Column("pw_hash",    sa.String, nullable=False),
        sa.Column("created_at", sa.String, default=sa.func.now()),
    )
    op.create_table("user_projects",
        sa.Column("user_id",    sa.String),
        sa.Column("project_id", sa.String),
        sa.Column("role",       sa.String, default="owner"),
        sa.PrimaryKeyConstraint("user_id","project_id"),
    )
    # Projects
    op.create_table("projects",
        sa.Column("project_id",    sa.String, primary_key=True),
        sa.Column("name",          sa.String, nullable=False),
        sa.Column("industry",      sa.String, nullable=False),
        sa.Column("description",   sa.String, default=""),
        sa.Column("seed_keywords", sa.String, default="[]"),
        sa.Column("wp_url",        sa.String, default=""),
        sa.Column("wp_user",       sa.String, default=""),
        sa.Column("wp_pass_enc",   sa.String, default=""),
        sa.Column("shopify_store", sa.String, default=""),
        sa.Column("shopify_token_enc", sa.String, default=""),
        sa.Column("language",      sa.String, default="english"),
        sa.Column("region",        sa.String, default="india"),
        sa.Column("religion",      sa.String, default="general"),
        sa.Column("status",        sa.String, default="active"),
        sa.Column("owner_id",      sa.String, default=""),
        sa.Column("created_at",    sa.String, default=sa.func.now()),
        sa.Column("updated_at",    sa.String, default=sa.func.now()),
    )
    # Runs + events
    op.create_table("runs",
        sa.Column("run_id",         sa.String, primary_key=True),
        sa.Column("project_id",     sa.String, nullable=False),
        sa.Column("seed",           sa.String, nullable=False),
        sa.Column("status",         sa.String, default="queued"),
        sa.Column("current_phase",  sa.String, default=""),
        sa.Column("phases_done",    sa.String, default="[]"),
        sa.Column("result",         sa.String, default="{}"),
        sa.Column("error",          sa.String, default=""),
        sa.Column("cost_usd",       sa.Float,  default=0),
        sa.Column("started_at",     sa.String, default=sa.func.now()),
        sa.Column("completed_at",   sa.String, default=""),
    )
    op.create_table("run_events",
        sa.Column("id",          sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("run_id",      sa.String,  nullable=False),
        sa.Column("event_type",  sa.String,  nullable=False),
        sa.Column("payload",     sa.String,  default="{}"),
        sa.Column("created_at",  sa.String,  default=sa.func.now()),
    )
    # Content
    op.create_table("content_articles",
        sa.Column("article_id",     sa.String,  primary_key=True),
        sa.Column("project_id",     sa.String,  nullable=False),
        sa.Column("run_id",         sa.String,  default=""),
        sa.Column("keyword",        sa.String,  nullable=False),
        sa.Column("title",          sa.String,  default=""),
        sa.Column("body",           sa.Text,    default=""),
        sa.Column("meta_title",     sa.String,  default=""),
        sa.Column("meta_desc",      sa.String,  default=""),
        sa.Column("seo_score",      sa.Float,   default=0),
        sa.Column("eeat_score",     sa.Float,   default=0),
        sa.Column("geo_score",      sa.Float,   default=0),
        sa.Column("readability",    sa.Float,   default=0),
        sa.Column("word_count",     sa.Integer, default=0),
        sa.Column("status",         sa.String,  default="draft"),
        sa.Column("published_url",  sa.String,  default=""),
        sa.Column("published_at",   sa.String,  default=""),
        sa.Column("schema_json",    sa.Text,    default=""),
        sa.Column("frozen",         sa.Integer, default=0),
        sa.Column("created_at",     sa.String,  default=sa.func.now()),
        sa.Column("updated_at",     sa.String,  default=sa.func.now()),
    )
    # Rankings + costs
    op.create_table("rankings",
        sa.Column("id",          sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("project_id",  sa.String,  nullable=False),
        sa.Column("keyword",     sa.String,  nullable=False),
        sa.Column("position",    sa.Float,   default=0),
        sa.Column("ctr",         sa.Float,   default=0),
        sa.Column("impressions", sa.Integer, default=0),
        sa.Column("clicks",      sa.Integer, default=0),
        sa.Column("recorded_at", sa.String,  default=sa.func.now()),
    )
    op.create_table("ai_usage",
        sa.Column("id",            sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("project_id",    sa.String,  nullable=False),
        sa.Column("run_id",        sa.String,  default=""),
        sa.Column("model",         sa.String,  nullable=False),
        sa.Column("input_tokens",  sa.Integer, default=0),
        sa.Column("output_tokens", sa.Integer, default=0),
        sa.Column("cost_usd",      sa.Float,   default=0),
        sa.Column("purpose",       sa.String,  default=""),
        sa.Column("created_at",    sa.String,  default=sa.func.now()),
    )
    # Indexes
    op.create_index("ix_runs_project",    "runs",             ["project_id"])
    op.create_index("ix_articles_project","content_articles", ["project_id"])
    op.create_index("ix_articles_status", "content_articles", ["status"])
    op.create_index("ix_rankings_project","rankings",         ["project_id"])
    op.create_index("ix_events_run",      "run_events",       ["run_id"])

def downgrade():
    for table in ["ai_usage","rankings","content_articles","run_events",
                   "runs","projects","user_projects","users"]:
        op.drop_table(table)

"""
================================================================================
ANNASEO — WIRING PACK  (annaseo_wiring.py)
================================================================================
GSC OAuth connector, database migrations, and Ruflo scheduler configuration.
This is the primary wiring module for AnnaSEO system integration.
================================================================================
"""

from __future__ import annotations

import os, json, logging, sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger("annaseo.wiring")
DB_PATH = Path(os.getenv("ANNASEO_DB", "./annaseo.db"))


# ─────────────────────────────────────────────────────────────────────────────
# PART 1 — GSC CONNECTOR
# ─────────────────────────────────────────────────────────────────────────────

class GSCConnector:
    """
    Google Search Console OAuth2 flow + daily rank import.
    Feeds P20_RankingFeedback and all ranking-dependent engines.

    Setup:
      1. Create a Google Cloud project
      2. Enable Search Console API
      3. Download OAuth2 credentials JSON
      4. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env
      5. Call get_auth_url() → user authorises → call exchange_code(code)
    """
    SCOPES     = ["https://www.googleapis.com/auth/webmasters.readonly"]
    AUTH_URL   = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL  = "https://oauth2.googleapis.com/token"
    GSC_API    = "https://www.googleapis.com/webmasters/v3"

    def __init__(self):
        self.client_id     = os.getenv("GOOGLE_CLIENT_ID","")
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET","")
        self.redirect_uri  = os.getenv("GOOGLE_REDIRECT_URI",
                                        "http://localhost:8000/api/gsc/callback")
        self._db = self._get_db()

    def _get_db(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.executescript("""
        CREATE TABLE IF NOT EXISTS gsc_connections (
            project_id    TEXT PRIMARY KEY,
            site_url      TEXT NOT NULL,
            access_token  TEXT DEFAULT '',
            refresh_token TEXT DEFAULT '',
            expires_at    TEXT DEFAULT '',
            connected     INTEGER DEFAULT 0,
            last_sync     TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS gsc_ranking_data (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  TEXT NOT NULL,
            keyword     TEXT NOT NULL,
            page        TEXT DEFAULT '',
            position    REAL DEFAULT 0,
            clicks      INTEGER DEFAULT 0,
            impressions INTEGER DEFAULT 0,
            ctr         REAL DEFAULT 0,
            date        TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_gsc_project_kw ON gsc_ranking_data(project_id, keyword);
        """)
        con.commit()
        return con

    def get_auth_url(self, project_id: str) -> str:
        """Return OAuth2 authorisation URL for the user to visit."""
        import urllib.parse
        params = {
            "client_id":     self.client_id,
            "redirect_uri":  self.redirect_uri,
            "response_type": "code",
            "scope":         " ".join(self.SCOPES),
            "access_type":   "offline",
            "state":         project_id,   # pass project_id through OAuth flow
            "prompt":        "consent",
        }
        return f"{self.AUTH_URL}?{urllib.parse.urlencode(params)}"

    def exchange_code(self, code: str, project_id: str, site_url: str) -> dict:
        """Exchange auth code for access + refresh tokens."""
        import requests as _req
        r = _req.post(self.TOKEN_URL, data={
            "code":          code,
            "client_id":     self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri":  self.redirect_uri,
            "grant_type":    "authorization_code",
        })
        if not r.ok:
            return {"error": r.text[:200]}
        data    = r.json()
        expires = (datetime.utcnow() + timedelta(seconds=data.get("expires_in",3600))).isoformat()
        self._db.execute("""
            INSERT OR REPLACE INTO gsc_connections
            (project_id,site_url,access_token,refresh_token,expires_at,connected)
            VALUES (?,?,?,?,?,1)
        """, (project_id, site_url, data.get("access_token",""),
               data.get("refresh_token",""), expires))
        self._db.commit()
        return {"connected": True, "project_id": project_id, "site_url": site_url}

    def _refresh_token(self, project_id: str) -> Optional[str]:
        import requests as _req
        row = self._db.execute("SELECT * FROM gsc_connections WHERE project_id=?",
                                (project_id,)).fetchone()
        if not row: return None
        conn = dict(row)
        expires = conn.get("expires_at","")
        if expires and datetime.fromisoformat(expires) > datetime.utcnow():
            return conn["access_token"]   # still valid
        # Refresh
        r = _req.post(self.TOKEN_URL, data={
            "refresh_token": conn["refresh_token"],
            "client_id":     self.client_id,
            "client_secret": self.client_secret,
            "grant_type":    "refresh_token",
        })
        if r.ok:
            data    = r.json()
            expires = (datetime.utcnow() + timedelta(seconds=data.get("expires_in",3600))).isoformat()
            token   = data.get("access_token","")
            self._db.execute(
                "UPDATE gsc_connections SET access_token=?, expires_at=? WHERE project_id=?",
                (token, expires, project_id))
            self._db.commit()
            return token
        return None

    def import_rankings(self, project_id: str, days: int = 7) -> dict:
        """
        Pull ranking data from GSC for the last N days.
        Stores to gsc_ranking_data + rankings tables (for all ranking engines).
        """
        import requests as _req
        token = self._refresh_token(project_id)
        if not token:
            return {"error": "Not connected to GSC. Run get_auth_url() first."}
        conn    = dict(self._db.execute("SELECT * FROM gsc_connections WHERE project_id=?",
                                         (project_id,)).fetchone())
        site_url= conn["site_url"]
        end_dt  = datetime.utcnow().strftime("%Y-%m-%d")
        start_dt= (datetime.utcnow()-timedelta(days=days)).strftime("%Y-%m-%d")
        headers = {"Authorization":f"Bearer {token}","Content-Type":"application/json"}
        r = _req.post(
            f"{self.GSC_API}/sites/{site_url}/searchAnalytics/query",
            headers=headers,
            json={
                "startDate": start_dt, "endDate": end_dt,
                "dimensions": ["query","page"],
                "rowLimit": 1000,
            }
        )
        if not r.ok:
            return {"error": f"GSC API error: {r.status_code} {r.text[:100]}"}
        rows   = r.json().get("rows",[])
        today  = datetime.utcnow().strftime("%Y-%m-%d")
        for row in rows:
            kw     = row["keys"][0]
            page   = row["keys"][1]
            pos    = row.get("position", 0)
            clicks = row.get("clicks", 0)
            impr   = row.get("impressions", 0)
            ctr    = row.get("ctr", 0)
            self._db.execute("""
                INSERT INTO gsc_ranking_data
                (project_id,keyword,page,position,clicks,impressions,ctr,date)
                VALUES (?,?,?,?,?,?,?,?)
            """, (project_id, kw, page, pos, clicks, impr, ctr, today))
            # Also write to the main rankings table (used by all engines)
            self._db.execute("""
                INSERT INTO rankings (project_id,keyword,position,ctr,impressions,clicks)
                VALUES (?,?,?,?,?,?)
            """, (project_id, kw, pos, ctr, impr, clicks))
        self._db.commit()
        self._db.execute("UPDATE gsc_connections SET last_sync=? WHERE project_id=?",
                          (datetime.utcnow().isoformat(), project_id))
        self._db.commit()
        log.info(f"[GSC] Imported {len(rows)} keywords for {project_id}")
        return {"imported": len(rows), "period": f"{start_dt} to {end_dt}"}

    def top_keywords(self, project_id: str, limit: int = 50) -> List[dict]:
        """Latest rankings sorted by position."""
        return [dict(r) for r in self._db.execute("""
            SELECT keyword, MIN(position) as position, SUM(clicks) as clicks,
                   SUM(impressions) as impressions, MAX(ctr) as ctr
            FROM gsc_ranking_data WHERE project_id=?
            GROUP BY keyword ORDER BY position ASC LIMIT ?
        """, (project_id, limit)).fetchall()]


# ─────────────────────────────────────────────────────────────────────────────
# PART 2 — ALEMBIC MIGRATIONS
# All 35+ tables, ready for Alembic to manage
# ─────────────────────────────────────────────────────────────────────────────

ALEMBIC_ENV_PY = '''
import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

config = context.config
fileConfig(config.config_file_name)

# Use ANNASEO_DB env var or sqlite default
db_url = os.getenv("DATABASE_URL",
                    f"sqlite:///{os.getenv('ANNASEO_DB','./annaseo.db')}")
config.set_main_option("sqlalchemy.url", db_url)

def run_migrations_offline():
    context.configure(url=db_url, target_metadata=None,
                       literal_binds=True, dialect_opts={"paramstyle":"named"})
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
'''

INITIAL_MIGRATION = '''"""Initial AnnaSEO schema — all tables

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
'''


def write_migrations(target_dir: str = "."):
    """Write Alembic migration files to disk."""
    base = Path(target_dir)
    # Create directory structure
    (base / "alembic" / "versions").mkdir(parents=True, exist_ok=True)
    (base / "alembic" / "env.py").write_text(ALEMBIC_ENV_PY)
    (base / "alembic" / "versions" / "0001_initial.py").write_text(INITIAL_MIGRATION)
    # alembic.ini
    ini = f"""[alembic]
script_location = alembic
sqlalchemy.url = sqlite:///{os.getenv('ANNASEO_DB','./annaseo.db')}

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = [sys.stderr]
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
"""
    (base / "alembic.ini").write_text(ini)
    log.info(f"[Alembic] Migration files written to {base}")
    print(f"Migrations written. Run:\n  alembic upgrade head")
    return str(base / "alembic")


# ─────────────────────────────────────────────────────────────────────────────
# PART 3 — RUFLO SCHEDULER CONFIG
# All cron jobs that need to run automatically
# ─────────────────────────────────────────────────────────────────────────────

RUFLO_JOBS = {
    # Keyword & content pipeline
    "keyword_universe_run": {
        "description": "Run 20-phase keyword universe for a seed",
        "trigger":     "manual + scheduled",
        "module":      "ruflo_20phase_engine",
        "class":       "RufloOrchestrator",
        "method":      "run_seed",
        "params":      ["keyword", "project_id", "pace"],
    },
    "content_generation": {
        "description": "Generate 7-pass article for a keyword",
        "trigger":     "manual + after_keyword_approval",
        "module":      "ruflo_content_engine",
        "class":       "ContentGenerationEngine",
        "method":      "generate",
        "params":      ["keyword", "title", "project_id"],
    },
    # GSC daily import
    "gsc_daily_import": {
        "description": "Import rankings from Google Search Console",
        "trigger":     "daily 06:00 UTC",
        "module":      "annaseo_wiring",
        "class":       "GSCConnector",
        "method":      "import_rankings",
        "params":      ["project_id", "days=7"],
    },
    # Quality intelligence
    "qi_score_run": {
        "description": "Score all new outputs from a run",
        "trigger":     "after_run_complete",
        "module":      "annaseo_qi_engine",
        "class":       "QIEngine",
        "method":      "job_score_run",
        "params":      ["run_id", "seed"],
    },
    # AI citation monitoring
    "citation_weekly_scan": {
        "description": "Check AI search citations for all tracked keywords",
        "trigger":     "weekly Monday 08:00 UTC",
        "module":      "annaseo_ai_citation_monitor",
        "class":       "AICitationMonitor",
        "method":      "job_scan",
        "params":      ["project_id", "our_domain"],
    },
    # Competitor monitoring
    "competitor_weekly_scan": {
        "description": "Scan competitor domains for new content",
        "trigger":     "weekly Sunday 06:00 UTC",
        "module":      "annaseo_advanced_engines",
        "class":       "CompetitorMonitor",
        "method":      "weekly_scan",
        "params":      ["project_id", "competitor_domains"],
    },
    # Content refresh
    "refresh_scan": {
        "description": "Detect declining articles needing refresh",
        "trigger":     "weekly Wednesday 09:00 UTC",
        "module":      "annaseo_content_refresh",
        "class":       "ContentRefreshEngine",
        "method":      "job_scan",
        "params":      ["project_id"],
    },
    # Seasonal refresh alerts
    "seasonal_refresh_check": {
        "description": "Check for articles with approaching seasonal peaks",
        "trigger":     "weekly Friday 07:00 UTC",
        "module":      "annaseo_intelligence_engines",
        "class":       "SeasonalKeywordCalendar",
        "method":      "refresh_alerts",
        "params":      ["project_id"],
    },
    # Intent shift detection
    "intent_shift_weekly": {
        "description": "Re-check intent for all published keywords",
        "trigger":     "weekly Tuesday 08:00 UTC",
        "module":      "annaseo_intelligence_engines",
        "class":       "SearchIntentShiftDetector",
        "method":      "detect_shifts",
        "params":      ["project_id"],
    },
    # Algorithm update detection
    "algo_volatility_check": {
        "description": "Detect algorithm updates from ranking volatility",
        "trigger":     "daily 10:00 UTC",
        "module":      "annaseo_advanced_engines",
        "class":       "AlgorithmUpdateAssessor",
        "method":      "detect_from_serp_volatility",
        "params":      ["project_id"],
    },
    # SEO intelligence crawling
    "sd_crawl_google_official": {
        "description": "Crawl Google Search Central + web.dev",
        "trigger":     "daily 08:00 UTC",
        "module":      "annaseo_self_dev",
        "class":       "SelfDevelopmentEngine",
        "method":      "job_crawl_category",
        "params":      ["category=google_official"],
    },
    "sd_crawl_ai_search": {
        "description": "Crawl AI search sources (Perplexity, OpenAI, Anthropic, llmstxt)",
        "trigger":     "daily 10:00 UTC",
        "module":      "annaseo_self_dev",
        "class":       "SelfDevelopmentEngine",
        "method":      "job_crawl_category",
        "params":      ["category=ai_search"],
    },
    "sd_crawl_research": {
        "description": "Crawl arXiv + Google Research papers",
        "trigger":     "weekly Sunday 07:00 UTC",
        "module":      "annaseo_self_dev",
        "class":       "SelfDevelopmentEngine",
        "method":      "job_crawl_category",
        "params":      ["category=research"],
    },
    # RSD engine health scan
    "rsd_daily_scan": {
        "description": "Score all engine health metrics",
        "trigger":     "daily 08:00 UTC",
        "module":      "annaseo_rsd_engine",
        "class":       "ResearchAndSelfDevelopment",
        "method":      "job_scan_all",
        "params":      [],
    },
    # PDF reports
    "monthly_report_generate": {
        "description": "Generate monthly client PDF reports",
        "trigger":     "monthly 1st 09:00 UTC",
        "module":      "annaseo_product_growth",
        "class":       "PDFReportEngine",
        "method":      "generate",
        "params":      ["project_id"],
    },
    # Webhooks for events
    "webhook_article_published": {
        "description": "Fire webhook when article publishes",
        "trigger":     "event: article.published",
        "module":      "annaseo_product_growth",
        "class":       "WebhookEngine",
        "method":      "emit",
        "params":      ["project_id", "event_type", "payload"],
    },
    "webhook_ranking_drop": {
        "description": "Fire webhook when ranking drops >5",
        "trigger":     "event: ranking.drop",
        "module":      "annaseo_product_growth",
        "class":       "WebhookEngine",
        "method":      "emit",
        "params":      ["project_id", "ranking.drop", "payload"],
    },
}

# Ruflo crontab format for auto-scheduling
RUFLO_CRONTAB = """
# AnnaSEO — Ruflo Scheduler Configuration
# Format: cron_expression | job_type | description

# Daily jobs (UTC)
0 6 * * *   | gsc_daily_import          | Import GSC rankings
0 8 * * *   | rsd_daily_scan            | Engine health scan
0 8 * * *   | sd_crawl_google_official  | Crawl Google sources
0 10 * * *  | sd_crawl_ai_search        | Crawl AI search sources
0 10 * * *  | algo_volatility_check     | Detect algorithm updates

# Weekly jobs
0 6 * * 0   | competitor_weekly_scan    | Scan competitor domains
0 7 * * 0   | sd_crawl_research         | Crawl research papers
0 8 * * 1   | citation_weekly_scan      | AI citation monitoring
0 8 * * 2   | intent_shift_weekly       | Intent shift detection
0 9 * * 3   | refresh_scan              | Content refresh scan
0 7 * * 5   | seasonal_refresh_check    | Seasonal peak alerts

# Monthly jobs
0 9 1 * *   | monthly_report_generate   | Generate PDF reports

# Event-driven (not cron — triggered by other jobs completing)
# event:run_complete         → qi_score_run
# event:article.published    → webhook_article_published
# event:ranking.drop         → webhook_ranking_drop
"""


# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI ENDPOINTS — GSC + scheduling
# ─────────────────────────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI, BackgroundTasks
    from pydantic import BaseModel as PM
    from typing import Optional as Opt

    app = FastAPI(title="AnnaSEO Wiring Pack — GSC + Scheduler")
    gsc = GSCConnector()

    class ExchangeBody(PM):
        code:      str
        site_url:  str

    @app.get("/api/gsc/{project_id}/auth-url", tags=["GSC"])
    def gsc_auth_url(project_id: str):
        """Step 1: Get OAuth URL for the user to visit."""
        url = gsc.get_auth_url(project_id)
        return {"auth_url": url, "instructions":
                "Visit this URL, authorise, then POST the code to /api/gsc/{project_id}/connect"}

    @app.get("/api/gsc/callback", tags=["GSC"])
    def gsc_callback(code: str, state: str):
        """OAuth callback — Google redirects here. state = project_id."""
        return {"code": code, "project_id": state,
                "next": f"POST /api/gsc/{state}/connect with this code and your site_url"}

    @app.post("/api/gsc/{project_id}/connect", tags=["GSC"])
    def gsc_connect(project_id: str, body: ExchangeBody):
        """Step 2: Exchange code for tokens."""
        return gsc.exchange_code(body.code, project_id, body.site_url)

    @app.post("/api/gsc/{project_id}/sync", tags=["GSC"])
    async def gsc_sync(project_id: str, days: int = 7, bg: BackgroundTasks = None):
        """Step 3: Import rankings from GSC."""
        if bg:
            bg.add_task(gsc.import_rankings, project_id, days)
            return {"status": "started", "days": days}
        return gsc.import_rankings(project_id, days)

    @app.get("/api/gsc/{project_id}/rankings", tags=["GSC"])
    def gsc_rankings(project_id: str, limit: int = 50):
        return gsc.top_keywords(project_id, limit)

    @app.get("/api/gsc/{project_id}/status", tags=["GSC"])
    def gsc_status(project_id: str):
        row = gsc._db.execute("SELECT * FROM gsc_connections WHERE project_id=?",
                               (project_id,)).fetchone()
        if not row: return {"connected": False}
        conn = dict(row)
        conn.pop("access_token",""); conn.pop("refresh_token","")
        return conn

    @app.get("/api/scheduler/jobs", tags=["Scheduler"])
    def list_jobs():
        return RUFLO_JOBS

    @app.get("/api/scheduler/crontab", tags=["Scheduler"])
    def get_crontab():
        return {"crontab": RUFLO_CRONTAB}

    @app.get("/api/migrations/status", tags=["Migrations"])
    def migration_status():
        try:
            import alembic.config as aconfig
            return {"alembic": "installed", "hint": "run: alembic upgrade head"}
        except ImportError:
            return {"alembic": "not installed", "hint": "pip install alembic"}

    @app.post("/api/migrations/write", tags=["Migrations"])
    def write_migration_files(target_dir: str = "."):
        path = write_migrations(target_dir)
        return {"written": path, "next": "alembic upgrade head"}

except ImportError:
    pass


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "write-migrations":
        d = sys.argv[2] if len(sys.argv) > 2 else "."
        write_migrations(d)
    elif len(sys.argv) > 1 and sys.argv[1] == "gsc-url":
        pid = sys.argv[2] if len(sys.argv) > 2 else "proj_001"
        g   = GSCConnector()
        if not g.client_id:
            print("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env first")
        else:
            print(g.get_auth_url(pid))
    elif len(sys.argv) > 1 and sys.argv[1] == "jobs":
        for job, info in RUFLO_JOBS.items():
            print(f"  {job:<35} | {info['trigger']:<30} | {info['description']}")
    else:
        print("Usage:")
        print("  python annaseo_wiring.py write-migrations [dir]")
        print("  python annaseo_wiring.py gsc-url <project_id>")
        print("  python annaseo_wiring.py jobs")
        print(f"\n  Scheduler: {len(RUFLO_JOBS)} job types configured")
        print(f"  Crontab: Run 'jobs' to see all scheduled tasks")

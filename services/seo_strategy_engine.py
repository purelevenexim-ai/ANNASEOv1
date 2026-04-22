"""
================================================================================
SEO STRATEGY ENGINE — Master Strategy Orchestrator
================================================================================
Implements the complete SEO strategy workflow derived from industry best practices
(Semrush, Ahrefs Orchard Strategy, Backlinko 2026 framework).

7-Phase Strategy Pipeline:
  Phase 1: Goal Setting & Benchmarking (SMART goals, business outcomes)
  Phase 2: Multi-Platform Research (Google, YouTube, Reddit, AI, competitors)
  Phase 3: Search Intent & Competition Analysis (SERP study, gap finding)
  Phase 4: Content Strategy (briefs, authority-driven, E-E-A-T)
  Phase 5: On-Page Optimization (titles, internal links, semantic relevance)
  Phase 6: Link Building & Citations (competitor links, middleman, outreach)
  Phase 7: Tracking & Content Updates (low-hanging fruit, update hierarchy)

Integration:
  Called from /api/strategy-intelligence/ endpoints
  Stores strategy_context per project in strategy_intelligence table
  Feeds into existing keyword pipeline (P1-P8) and content engines
================================================================================
"""

from __future__ import annotations
import json
import logging
import sqlite3
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

log = logging.getLogger("annaseo.seo_strategy_engine")


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY CONTEXT — Single source of truth for all strategy data
# ─────────────────────────────────────────────────────────────────────────────

def create_strategy_context(project_id: str, business_info: Dict = None) -> Dict[str, Any]:
    """Create a fresh strategy context for a project."""
    return {
        "project_id": project_id,
        "strategy_id": f"strat_{uuid.uuid4().hex[:12]}",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "status": "draft",  # draft | in_progress | finalized | locked

        # Phase 1: Goals & Benchmarks
        "goals": {
            "business_outcome": "",        # e.g. "50 new customers/month from organic"
            "smart_goal": "",              # SMART formatted goal string
            "goal_type": "",               # traffic | leads | revenue | local_visibility
            "target_metric": 0,            # numeric target
            "target_timeframe_months": 6,
            "current_benchmark": {
                "organic_clicks_28d": 0,
                "organic_impressions_28d": 0,
                "avg_position": 0,
                "indexed_pages": 0,
                "domain_authority": 0,
            },
            "seo_focus_areas": [],         # e.g. ["bottom_funnel_commercial", "product_pages"]
        },

        # Phase 2: Research
        "business": {
            "website_url": "",
            "products": [],
            "business_type": "",           # B2C | B2B | D2C | Local
            "target_market": [],
            "usp": "",
            "topics": [],
            "allowed_topics": [],
            "blocked_topics": [],
        },
        "audiences": [],                   # [{name, intents, confidence}]
        "competitors": {
            "urls": [],
            "top_keywords": [],
            "gap_keywords": [],
            "top_pages": [],               # [{url, traffic, keywords_count}]
            "link_profile": [],            # [{domain, backlinks, authority}]
        },
        "research": {
            "google_suggestions": [],
            "youtube_topics": [],
            "reddit_topics": [],
            "ai_topics": [],
            "customer_insights": [],
        },

        # Phase 3: Intent & Competition
        "keyword_map": [],                 # [{keyword, page_url, intent, status, business_potential}]
        "seo_briefs": [],                  # [{keyword, format, depth, gaps, angle}]
        "serp_cache": {},                  # {keyword: {intent, content_type, difficulty, feasibility}}

        # Phase 4: Content Strategy
        "content_plan": [],                # [{keyword, format, priority, status, assigned_to}]
        "topic_clusters": [],              # [{pillar, subtopics: [...]}]

        # Phase 5: On-Page Optimization
        "optimization_queue": [],          # [{page_url, keyword, issues: [...], priority}]
        "internal_link_opportunities": [], # [{source_url, target_url, anchor_text, context}]

        # Phase 6: Link Building
        "link_building": {
            "competitor_links": [],        # [{source_domain, target_competitor, link_type}]
            "opportunities": [],           # [{prospect_url, strategy, priority, status}]
            "middleman_pages": [],         # [{money_page, middleman_page, internal_link_added}]
            "outreach_queue": [],          # [{prospect, contact, template, status}]
        },

        # Phase 7: Tracking & Updates
        "low_hanging_fruit": [],           # [{keyword, current_rank, traffic_potential, page_url}]
        "content_updates": [],             # [{page_url, update_type, priority, status}]
        "consolidation_candidates": [],    # [{pages: [url1, url2], reason, target_url}]

        # Scoring
        "scored_keywords": [],             # [{keyword, score, priority, business_potential, ...}]
        "keywords": [],                    # flat list of all target keywords
    }


# ─────────────────────────────────────────────────────────────────────────────
# DB OPERATIONS — Persist strategy context
# ─────────────────────────────────────────────────────────────────────────────

STRATEGY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS strategy_intelligence (
    strategy_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    context_json TEXT DEFAULT '{}',
    status TEXT DEFAULT 'draft',
    phase TEXT DEFAULT 'goals',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_si_project ON strategy_intelligence(project_id);
"""


def ensure_strategy_table(db: sqlite3.Connection):
    """Create strategy_intelligence table if it doesn't exist."""
    db.executescript(STRATEGY_TABLE_SQL)


def save_strategy(db: sqlite3.Connection, ctx: Dict[str, Any]):
    """Persist strategy context to DB."""
    ensure_strategy_table(db)
    ctx["updated_at"] = datetime.utcnow().isoformat()
    db.execute(
        """INSERT OR REPLACE INTO strategy_intelligence
           (strategy_id, project_id, context_json, status, phase, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            ctx["strategy_id"],
            ctx["project_id"],
            json.dumps(ctx),
            ctx.get("status", "draft"),
            _detect_phase(ctx),
            ctx.get("created_at", datetime.utcnow().isoformat()),
            ctx["updated_at"],
        ),
    )
    db.commit()


def load_strategy(db: sqlite3.Connection, project_id: str) -> Optional[Dict[str, Any]]:
    """Load the latest strategy context for a project."""
    ensure_strategy_table(db)
    row = db.execute(
        "SELECT context_json FROM strategy_intelligence WHERE project_id=? ORDER BY updated_at DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    if row:
        return json.loads(row[0] if isinstance(row, (tuple, list)) else row["context_json"])
    return None


def load_strategy_by_id(db: sqlite3.Connection, strategy_id: str) -> Optional[Dict[str, Any]]:
    """Load a specific strategy context by ID."""
    ensure_strategy_table(db)
    row = db.execute(
        "SELECT context_json FROM strategy_intelligence WHERE strategy_id=?",
        (strategy_id,),
    ).fetchone()
    if row:
        return json.loads(row[0] if isinstance(row, (tuple, list)) else row["context_json"])
    return None


def list_strategies(db: sqlite3.Connection, project_id: str) -> List[Dict]:
    """List all strategies for a project (summary only)."""
    ensure_strategy_table(db)
    rows = db.execute(
        "SELECT strategy_id, status, phase, created_at, updated_at FROM strategy_intelligence WHERE project_id=? ORDER BY updated_at DESC",
        (project_id,),
    ).fetchall()
    return [
        {"strategy_id": r[0], "status": r[1], "phase": r[2], "created_at": r[3], "updated_at": r[4]}
        for r in rows
    ]


def _detect_phase(ctx: Dict) -> str:
    """Detect current strategy phase based on filled sections."""
    if ctx.get("scored_keywords"):
        return "scoring"
    if ctx.get("content_plan"):
        return "content_planning"
    if ctx.get("seo_briefs"):
        return "brief_creation"
    if ctx.get("keyword_map"):
        return "intent_analysis"
    if ctx.get("competitors", {}).get("top_keywords"):
        return "research"
    if ctx.get("goals", {}).get("business_outcome"):
        return "goals"
    return "setup"


# ─────────────────────────────────────────────────────────────────────────────
# PHASE ORCHESTRATOR — Run individual phases
# ─────────────────────────────────────────────────────────────────────────────

class SEOStrategyEngine:
    """Master orchestrator for the 7-phase SEO strategy."""

    def __init__(self, db_getter):
        """
        Args:
            db_getter: callable that returns a sqlite3.Connection
        """
        self._get_db = db_getter

    def init_strategy(self, project_id: str, business_info: Dict = None) -> Dict:
        """Phase 0: Initialize a new strategy context."""
        ctx = create_strategy_context(project_id, business_info)
        if business_info:
            ctx["business"].update({
                k: v for k, v in business_info.items()
                if k in ctx["business"]
            })
        db = self._get_db()
        try:
            save_strategy(db, ctx)
            log.info("[Strategy] Initialized strategy %s for project %s", ctx["strategy_id"], project_id)
            return ctx
        finally:
            db.close()

    def get_strategy(self, project_id: str) -> Optional[Dict]:
        """Load the current strategy for a project."""
        db = self._get_db()
        try:
            return load_strategy(db, project_id)
        finally:
            db.close()

    def update_strategy(self, project_id: str, updates: Dict) -> Dict:
        """Merge updates into the strategy context and save."""
        db = self._get_db()
        try:
            ctx = load_strategy(db, project_id)
            if not ctx:
                raise ValueError(f"No strategy found for project {project_id}")
            if ctx.get("status") == "locked":
                raise ValueError("Strategy is locked. Create a new one or unlock first.")
            _deep_merge(ctx, updates)
            save_strategy(db, ctx)
            return ctx
        finally:
            db.close()

    def finalize_strategy(self, project_id: str) -> Dict:
        """Lock the strategy and prepare for execution."""
        db = self._get_db()
        try:
            ctx = load_strategy(db, project_id)
            if not ctx:
                raise ValueError(f"No strategy found for project {project_id}")

            # Readiness check
            issues = _check_readiness(ctx)
            if issues:
                return {"status": "not_ready", "issues": issues}

            ctx["status"] = "finalized"
            save_strategy(db, ctx)
            log.info("[Strategy] Finalized strategy for project %s", project_id)
            return {"status": "finalized", "strategy_id": ctx["strategy_id"]}
        finally:
            db.close()

    def get_strategy_summary(self, project_id: str) -> Dict:
        """Return a compact summary of the strategy state."""
        ctx = self.get_strategy(project_id)
        if not ctx:
            return {"exists": False}

        return {
            "exists": True,
            "strategy_id": ctx["strategy_id"],
            "status": ctx["status"],
            "phase": _detect_phase(ctx),
            "goals_set": bool(ctx.get("goals", {}).get("business_outcome")),
            "keywords_count": len(ctx.get("keywords", [])),
            "scored_count": len(ctx.get("scored_keywords", [])),
            "competitors_count": len(ctx.get("competitors", {}).get("urls", [])),
            "audiences_count": len(ctx.get("audiences", [])),
            "briefs_count": len(ctx.get("seo_briefs", [])),
            "content_plan_count": len(ctx.get("content_plan", [])),
            "low_hanging_fruit_count": len(ctx.get("low_hanging_fruit", [])),
            "link_opportunities_count": len(ctx.get("link_building", {}).get("opportunities", [])),
        }


# ─────────────────────────────────────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

def _deep_merge(base: Dict, updates: Dict):
    """Recursively merge updates into base dict."""
    for key, val in updates.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val


def _check_readiness(ctx: Dict) -> List[str]:
    """Check if strategy is ready for finalization."""
    issues = []
    if not ctx.get("goals", {}).get("business_outcome"):
        issues.append("No business outcome goal defined")
    if not ctx.get("business", {}).get("topics"):
        issues.append("No business topics defined")
    if not ctx.get("audiences"):
        issues.append("No audience groups defined")
    if not ctx.get("keywords"):
        issues.append("No target keywords defined")
    return issues

"""
================================================================================
GOAL SETTING & BENCHMARKING SERVICE
================================================================================
Phase 1 of the SEO Strategy (Backlinko Step 1, Ahrefs "Plan" step).

Implements:
- SMART goal framework (Specific, Measurable, Attainable, Relevant, Time-bound)
- Business outcome mapping (not just SEO metrics)
- Current performance benchmarking from GSC/rankings data
- SEO focus area detection based on business type
- Goal tracking and progress measurement

Reference: Backlinko "Define Your SEO Goals" + Ahrefs "Benchmark and set a goal"
================================================================================
"""

from __future__ import annotations
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

log = logging.getLogger("annaseo.goal_setting")


# ─────────────────────────────────────────────────────────────────────────────
# BUSINESS TYPE → SEO FOCUS AREA MAPPING
# ─────────────────────────────────────────────────────────────────────────────
# From Backlinko: "Map Goals to SEO Focus Areas"

BUSINESS_FOCUS_MAP = {
    "lead_generation": {
        "description": "Consulting, SaaS, professional services",
        "primary_focus": "bottom_funnel_commercial_keywords",
        "content_priority": ["problem_solution", "case_studies", "comparison_pages"],
        "success_metrics": ["qualified_leads", "conversion_rate", "cost_per_acquisition"],
    },
    "ecommerce": {
        "description": "E-commerce, affiliate, revenue-focused",
        "primary_focus": "product_and_money_keywords",
        "content_priority": ["product_guides", "reviews", "buying_intent_content"],
        "success_metrics": ["organic_revenue", "transaction_value", "product_page_traffic"],
    },
    "local": {
        "description": "Restaurant, dental, home services",
        "primary_focus": "local_search_visibility",
        "content_priority": ["local_content", "service_pages", "location_guides"],
        "success_metrics": ["store_visits", "local_leads", "brand_searches"],
    },
    "content": {
        "description": "Blog, media, content creator",
        "primary_focus": "informational_keyword_coverage",
        "content_priority": ["tutorials", "guides", "listicles", "thought_leadership"],
        "success_metrics": ["organic_traffic", "engagement", "newsletter_signups"],
    },
    "saas": {
        "description": "SaaS, software products",
        "primary_focus": "product_led_seo",
        "content_priority": ["comparison_pages", "integration_guides", "use_case_content"],
        "success_metrics": ["demo_requests", "trial_signups", "activation_rate"],
    },
}


def get_focus_areas(business_type: str) -> Dict[str, Any]:
    """Map business type to recommended SEO focus areas."""
    btype = business_type.lower().replace(" ", "_")
    # Try direct match first
    if btype in BUSINESS_FOCUS_MAP:
        return BUSINESS_FOCUS_MAP[btype]
    # Fuzzy match
    for key, val in BUSINESS_FOCUS_MAP.items():
        if btype in key or key in btype:
            return val
    # Default to content
    return BUSINESS_FOCUS_MAP["content"]


# ─────────────────────────────────────────────────────────────────────────────
# SMART GOAL GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def generate_smart_goal(
    goal_type: str,
    target_metric: float,
    timeframe_months: int,
    current_benchmark: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Generate a SMART-formatted SEO goal.

    Args:
        goal_type: traffic | leads | revenue | local_visibility
        target_metric: numeric improvement target (e.g., 10 for 10% increase)
        timeframe_months: goal timeframe
        current_benchmark: current performance numbers
    """
    current_clicks = current_benchmark.get("organic_clicks_28d", 0)
    current_impressions = current_benchmark.get("organic_impressions_28d", 0)

    # Determine attainability based on current traffic level
    # Per Ahrefs: low traffic = easy 100%+, high traffic = hard 50%+
    if current_clicks < 1000:
        attainability = "highly_achievable" if target_metric <= 100 else "ambitious"
    elif current_clicks < 10000:
        attainability = "achievable" if target_metric <= 50 else "ambitious"
    else:
        attainability = "achievable" if target_metric <= 20 else "ambitious"

    goal_templates = {
        "traffic": f"Increase organic search traffic by {target_metric}% within {timeframe_months} months, from {current_clicks} to {int(current_clicks * (1 + target_metric / 100))} monthly clicks",
        "leads": f"Generate {int(target_metric)} qualified leads per month from organic search within {timeframe_months} months",
        "revenue": f"Increase organic revenue by {target_metric}% within {timeframe_months} months",
        "local_visibility": f"Achieve top-3 rankings for {int(target_metric)} local keywords within {timeframe_months} months",
    }

    smart_text = goal_templates.get(goal_type, goal_templates["traffic"])

    return {
        "smart_goal": smart_text,
        "specific": f"{target_metric}{'%' if goal_type in ('traffic', 'revenue') else ''} improvement target",
        "measurable": f"Track via GSC clicks, rankings, and {'revenue' if goal_type == 'revenue' else 'traffic'} data",
        "attainable": attainability,
        "relevant": f"Drives {goal_type} which directly impacts business growth",
        "time_bound": f"{timeframe_months} months from {datetime.utcnow().strftime('%Y-%m-%d')}",
        "deadline": (datetime.utcnow() + timedelta(days=timeframe_months * 30)).isoformat(),
        "tracking_metrics": _get_tracking_metrics(goal_type),
    }


def _get_tracking_metrics(goal_type: str) -> List[str]:
    """Get recommended metrics to track for goal type."""
    base = ["organic_traffic", "keyword_rankings", "indexed_pages"]
    type_metrics = {
        "traffic": ["organic_clicks", "impressions", "avg_position", "new_keywords_ranking"],
        "leads": ["conversion_rate", "form_submissions", "cost_per_lead", "qualifying_keyword_traffic"],
        "revenue": ["organic_revenue", "transaction_value", "product_page_traffic", "commercial_keyword_rankings"],
        "local_visibility": ["local_pack_rankings", "gmb_views", "local_keyword_positions", "brand_searches"],
    }
    return base + type_metrics.get(goal_type, [])


# ─────────────────────────────────────────────────────────────────────────────
# PERFORMANCE BENCHMARKING
# ─────────────────────────────────────────────────────────────────────────────

def benchmark_current_performance(db: sqlite3.Connection, project_id: str) -> Dict[str, Any]:
    """
    Collect current SEO performance metrics from available data sources.
    Pulls from rankings, content_articles, and GSC data.
    """
    benchmark = {
        "organic_clicks_28d": 0,
        "organic_impressions_28d": 0,
        "avg_position": 0,
        "indexed_pages": 0,
        "domain_authority": 0,
        "total_keywords_ranking": 0,
        "top_3_keywords": 0,
        "top_10_keywords": 0,
        "top_20_keywords": 0,
        "content_articles": 0,
        "avg_content_score": 0,
        "collected_at": datetime.utcnow().isoformat(),
    }

    try:
        # Rankings data
        rows = db.execute(
            """SELECT position, impressions, clicks FROM rankings
               WHERE project_id = ? ORDER BY recorded_at DESC LIMIT 500""",
            (project_id,),
        ).fetchall()

        if rows:
            positions = [r[0] for r in rows if r[0] and r[0] > 0]
            benchmark["total_keywords_ranking"] = len(positions)
            benchmark["avg_position"] = round(sum(positions) / len(positions), 1) if positions else 0
            benchmark["top_3_keywords"] = sum(1 for p in positions if p <= 3)
            benchmark["top_10_keywords"] = sum(1 for p in positions if p <= 10)
            benchmark["top_20_keywords"] = sum(1 for p in positions if p <= 20)
            benchmark["organic_impressions_28d"] = sum(r[1] for r in rows if r[1])
            benchmark["organic_clicks_28d"] = sum(r[2] for r in rows if r[2])

        # Content articles
        art_row = db.execute(
            "SELECT COUNT(*), AVG(seo_score) FROM content_articles WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if art_row:
            benchmark["content_articles"] = art_row[0] or 0
            benchmark["avg_content_score"] = round(art_row[1] or 0, 1)

        # Indexed pages estimate
        benchmark["indexed_pages"] = benchmark["content_articles"]

    except Exception as e:
        log.warning("[GoalSetting] Benchmark collection error: %s", e)

    return benchmark


# ─────────────────────────────────────────────────────────────────────────────
# GOAL PROGRESS TRACKER
# ─────────────────────────────────────────────────────────────────────────────

def calculate_goal_progress(
    goal: Dict[str, Any],
    current_benchmark: Dict[str, Any],
    original_benchmark: Dict[str, Any],
) -> Dict[str, Any]:
    """Calculate progress towards the SMART goal."""
    goal_type = goal.get("goal_type", "traffic")
    target = goal.get("target_metric", 0)

    if goal_type in ("traffic", "revenue"):
        original_val = original_benchmark.get("organic_clicks_28d", 1)
        current_val = current_benchmark.get("organic_clicks_28d", 0)
        if original_val > 0:
            actual_change_pct = ((current_val - original_val) / original_val) * 100
            progress_pct = min(100, (actual_change_pct / target) * 100) if target > 0 else 0
        else:
            actual_change_pct = 100 if current_val > 0 else 0
            progress_pct = 100 if current_val > 0 else 0
    elif goal_type == "leads":
        # Track conversion events
        actual_change_pct = 0
        progress_pct = 0
    elif goal_type == "local_visibility":
        top3 = current_benchmark.get("top_3_keywords", 0)
        progress_pct = min(100, (top3 / max(target, 1)) * 100)
        actual_change_pct = top3
    else:
        actual_change_pct = 0
        progress_pct = 0

    # Time progress
    deadline_str = goal.get("deadline", "")
    if deadline_str:
        try:
            deadline = datetime.fromisoformat(deadline_str)
            created = datetime.fromisoformat(goal.get("created_at", datetime.utcnow().isoformat()))
            total_days = (deadline - created).days or 1
            elapsed_days = (datetime.utcnow() - created).days
            time_pct = min(100, (elapsed_days / total_days) * 100)
        except (ValueError, TypeError):
            time_pct = 0
    else:
        time_pct = 0

    # On track?
    on_track = progress_pct >= time_pct * 0.8  # within 80% of expected pace

    return {
        "progress_percent": round(progress_pct, 1),
        "time_elapsed_percent": round(time_pct, 1),
        "actual_change": round(actual_change_pct, 1),
        "on_track": on_track,
        "status": "ahead" if progress_pct > time_pct else ("on_track" if on_track else "behind"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# RECOMMENDED METRICS (from Backlinko's "Track What You Can Measure")
# ─────────────────────────────────────────────────────────────────────────────

TRACK_RELIABLY = [
    "brand_search_volume_trends",
    "direct_traffic_increases",
    "share_of_voice_vs_competitors",
    "organic_traffic_to_converting_pages",
    "customer_lifetime_value_trends",
]

QUALITATIVE_DATA = [
    "customer_survey_how_heard",
    "industry_discussion_mentions",
    "assisted_conversions_longer_windows",
]

SKIP_VANITY = [
    "total_keyword_rankings",
    "domain_authority_scores",
    "traffic_to_non_converting_blog_posts",
]


def get_tracking_recommendations(business_type: str) -> Dict[str, List[str]]:
    """Get metric tracking recommendations based on business type."""
    focus = get_focus_areas(business_type)
    return {
        "track_reliably": TRACK_RELIABLY,
        "qualitative": QUALITATIVE_DATA,
        "skip_vanity": SKIP_VANITY,
        "business_kpis": focus.get("success_metrics", []),
    }

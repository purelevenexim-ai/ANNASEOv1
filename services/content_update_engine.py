"""
================================================================================
CONTENT UPDATE HIERARCHY ENGINE
================================================================================
Phase 7 — Improve and update existing content (Backlinko Step 7).

From Backlinko: "Often, updating what you already have delivers faster results
than starting from scratch with new content."

Three-Tier Update System (from Backlinko):
  1. Optimizations: Small on-page tweaks (internal links, images, meta tags, CTAs)
  2. Upgrades: 15-70% changes (update examples, refresh stats, add sections)
  3. Rewrites: 70%+ changes (rethink structure, angle, approach)

Also implements:
- Content consolidation detection (merge overlapping pages)
- Content freshness scoring
- Update priority queue

Reference: Backlinko "Improve and Update Your Content"
           Backlinko "The Hierarchy of Updates"
           Backlinko "Consolidate Your Content"
================================================================================
"""

from __future__ import annotations
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List

log = logging.getLogger("annaseo.content_updater")


# ─────────────────────────────────────────────────────────────────────────────
# CONTENT FRESHNESS SCORING
# ─────────────────────────────────────────────────────────────────────────────

def score_content_freshness(
    updated_at: str,
    industry: str = "general",
) -> Dict[str, Any]:
    """
    Score content freshness. Content naturally ages and loses relevance,
    especially in marketing and tech where tools/strategies evolve rapidly.
    """
    try:
        updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00").replace("+00:00", ""))
    except (ValueError, TypeError):
        updated = datetime.utcnow() - timedelta(days=365)

    days_old = (datetime.utcnow() - updated).days

    # Industry-specific decay rates
    decay_rates = {
        "tech": 90,       # Tech content stales fast
        "marketing": 120,
        "seo": 120,
        "finance": 180,
        "health": 180,
        "general": 270,
        "legal": 365,
        "evergreen": 730,
    }

    half_life = decay_rates.get(industry.lower(), 270)

    # Freshness score: 1.0 = just updated, 0.0 = very stale
    import math
    freshness = max(0, math.exp(-0.693 * days_old / half_life))  # exponential decay

    if freshness >= 0.8:
        status = "fresh"
    elif freshness >= 0.5:
        status = "aging"
    elif freshness >= 0.2:
        status = "stale"
    else:
        status = "outdated"

    return {
        "freshness_score": round(freshness, 2),
        "days_since_update": days_old,
        "status": status,
        "industry_half_life_days": half_life,
        "recommended_update": _recommend_update_schedule(status, days_old),
    }


def _recommend_update_schedule(status: str, days_old: int) -> str:
    if status == "outdated":
        return "Immediate: Content is severely outdated. Upgrade or rewrite."
    elif status == "stale":
        return "Priority: Schedule upgrade within 2 weeks."
    elif status == "aging":
        return "Plan: Schedule optimization within 1 month."
    else:
        return "OK: Content is fresh. Check again in 3 months."


# ─────────────────────────────────────────────────────────────────────────────
# UPDATE TYPE CLASSIFIER
# ─────────────────────────────────────────────────────────────────────────────

def classify_update_type(
    content_score: float,
    freshness_score: float,
    ranking_trend: str,      # "improving" | "stable" | "declining" | "lost"
    traffic_trend: str,       # "growing" | "stable" | "declining" | "minimal"
    competitive_pressure: str, # "low" | "medium" | "high"
) -> Dict[str, Any]:
    """
    Classify what type of update is needed based on content signals.

    Returns one of three tiers:
    - optimization: Small tweaks (low effort, moderate impact)
    - upgrade: Significant refresh (medium effort, high impact)
    - rewrite: Complete overhaul (high effort, highest impact)
    """
    signals = []
    score = 0.0  # 0-1: higher = more intensive update needed

    # Freshness factor
    if freshness_score < 0.2:
        score += 0.4
        signals.append("severely_outdated")
    elif freshness_score < 0.5:
        score += 0.2
        signals.append("stale_content")

    # Content quality factor
    if content_score < 40:
        score += 0.3
        signals.append("low_quality_score")
    elif content_score < 60:
        score += 0.15
        signals.append("moderate_quality")

    # Ranking trend
    if ranking_trend == "lost":
        score += 0.3
        signals.append("lost_rankings")
    elif ranking_trend == "declining":
        score += 0.2
        signals.append("declining_rankings")

    # Traffic trend
    if traffic_trend == "minimal":
        score += 0.2
        signals.append("minimal_traffic")
    elif traffic_trend == "declining":
        score += 0.15
        signals.append("traffic_declining")

    # Competitive pressure
    if competitive_pressure == "high":
        score += 0.15
        signals.append("high_competition")

    # Classify update type
    if score >= 0.6:
        update_type = "rewrite"
        description = "70%+ content overhaul. Rethink structure, angle, and approach."
        effort = "high"
        expected_impact = "high"
        timeline = "1-2 weeks"
    elif score >= 0.3:
        update_type = "upgrade"
        description = "15-70% content refresh. Update examples, stats, add new sections."
        effort = "medium"
        expected_impact = "high"
        timeline = "3-5 days"
    else:
        update_type = "optimization"
        description = "Small tweaks: internal links, meta tags, images, CTAs."
        effort = "low"
        expected_impact = "moderate"
        timeline = "1-2 hours"

    return {
        "update_type": update_type,
        "description": description,
        "effort": effort,
        "expected_impact": expected_impact,
        "timeline": timeline,
        "urgency_score": round(score, 2),
        "signals": signals,
        "actions": _get_update_actions(update_type, signals),
    }


def _get_update_actions(update_type: str, signals: List[str]) -> List[Dict[str, str]]:
    """Get specific actions for the update type."""
    actions = []

    if update_type == "optimization":
        actions = [
            {"action": "Add 3-5 internal links to/from this page", "effort": "5 min"},
            {"action": "Update meta title and description for better CTR", "effort": "10 min"},
            {"action": "Add/update hero image and section images", "effort": "15 min"},
            {"action": "Add or improve CTAs", "effort": "10 min"},
            {"action": "Fix any broken links", "effort": "5 min"},
        ]
    elif update_type == "upgrade":
        actions = [
            {"action": "Replace outdated screenshots with current interfaces", "effort": "30 min"},
            {"action": "Update all statistics and data points", "effort": "45 min"},
            {"action": "Add 2-3 new sections covering missed subtopics", "effort": "2 hours"},
            {"action": "Improve visual hierarchy and scannability", "effort": "30 min"},
            {"action": "Add fresh examples and case studies", "effort": "1 hour"},
            {"action": "Strengthen E-E-A-T signals (author bio, methodology)", "effort": "20 min"},
        ]
    elif update_type == "rewrite":
        actions = [
            {"action": "Re-analyze search intent and top competitors", "effort": "1 hour"},
            {"action": "Create new content outline from scratch", "effort": "1 hour"},
            {"action": "Write new comprehensive content", "effort": "4-8 hours"},
            {"action": "Create original graphics, charts, or data", "effort": "2 hours"},
            {"action": "Set up proper internal linking structure", "effort": "30 min"},
            {"action": "Implement schema markup", "effort": "15 min"},
        ]

    # Add signal-specific actions
    if "lost_rankings" in signals:
        actions.append({"action": "Analyze SERP changes and competitor updates", "effort": "30 min"})
    if "high_competition" in signals:
        actions.append({"action": "Build 5-10 quality backlinks to this page", "effort": "ongoing"})

    return actions


# ─────────────────────────────────────────────────────────────────────────────
# CONTENT AUDIT — Scan all articles for update needs
# ─────────────────────────────────────────────────────────────────────────────

def audit_content_for_updates(
    db: sqlite3.Connection,
    project_id: str,
    industry: str = "general",
) -> Dict[str, Any]:
    """
    Audit all content articles for a project and classify update needs.
    Returns prioritized update queue.
    """
    rows = db.execute(
        """SELECT article_id, keyword, title, seo_score, word_count,
                  status, updated_at, published_at
           FROM content_articles
           WHERE project_id = ? AND status IN ('published', 'draft', 'approved')
           ORDER BY updated_at ASC""",
        (project_id,),
    ).fetchall()

    updates_needed = []
    stats = {"total": 0, "optimizations": 0, "upgrades": 0, "rewrites": 0, "fresh": 0}

    for row in rows:
        stats["total"] += 1
        article_id = row[0]
        keyword = row[1]
        title = row[2]
        seo_score = row[3] or 0
        word_count = row[4] or 0
        status = row[5]
        updated_at = row[6] or row[7] or ""

        # Score freshness
        freshness = score_content_freshness(updated_at, industry)

        # Get ranking trend (simplified — check if ranking exists and direction)
        ranking_trend = _get_ranking_trend(db, project_id, keyword)
        traffic_trend = "stable"  # Would need GSC data for real trend

        # Classify competitive pressure based on word count vs typical
        competitive_pressure = "medium"
        if word_count < 800:
            competitive_pressure = "high"

        update = classify_update_type(
            content_score=seo_score,
            freshness_score=freshness["freshness_score"],
            ranking_trend=ranking_trend,
            traffic_trend=traffic_trend,
            competitive_pressure=competitive_pressure,
        )

        if update["update_type"] != "optimization" or freshness["status"] != "fresh":
            updates_needed.append({
                "article_id": article_id,
                "keyword": keyword,
                "title": title,
                "seo_score": seo_score,
                "freshness": freshness,
                "update": update,
            })
            stats[update["update_type"] + "s"] += 1
        else:
            stats["fresh"] += 1

    # Sort by urgency
    updates_needed.sort(key=lambda x: x["update"]["urgency_score"], reverse=True)

    return {
        "updates_needed": updates_needed,
        "stats": stats,
        "summary": f"{stats['rewrites']} rewrites, {stats['upgrades']} upgrades, {stats['optimizations']} optimizations needed",
    }


def _get_ranking_trend(db: sqlite3.Connection, project_id: str, keyword: str) -> str:
    """Get ranking trend for a keyword."""
    try:
        rows = db.execute(
            "SELECT position FROM rankings WHERE project_id=? AND keyword=? ORDER BY recorded_at DESC LIMIT 5",
            (project_id, keyword),
        ).fetchall()
        if not rows:
            return "lost"
        positions = [r[0] for r in rows if r[0]]
        if not positions:
            return "lost"
        if len(positions) >= 2:
            if positions[0] < positions[-1]:
                return "improving"
            elif positions[0] > positions[-1] + 5:
                return "declining"
        return "stable"
    except Exception:
        return "stable"


# ─────────────────────────────────────────────────────────────────────────────
# CONTENT CONSOLIDATION DETECTOR
# ─────────────────────────────────────────────────────────────────────────────
# From Backlinko: "Sometimes the best update is a strategic merger."

def find_consolidation_candidates(
    db: sqlite3.Connection,
    project_id: str,
) -> List[Dict[str, Any]]:
    """
    Find content pages that could be consolidated (merged).

    Consolidation works when:
    - Multiple pages target similar keywords
    - Some pages no longer perform well
    - A single comprehensive resource better serves user intent
    """
    rows = db.execute(
        """SELECT article_id, keyword, title, seo_score, word_count
           FROM content_articles
           WHERE project_id = ?
           ORDER BY keyword""",
        (project_id,),
    ).fetchall()

    if not rows:
        return []

    # Group by keyword similarity
    from collections import defaultdict
    keyword_groups = defaultdict(list)

    for row in rows:
        article_id, keyword, title, seo_score, word_count = row
        # Normalize keyword for grouping
        base_words = set(keyword.lower().split())

        # Find matching group
        matched = False
        for group_key in list(keyword_groups.keys()):
            group_words = set(group_key.split())
            overlap = base_words & group_words
            # If significant word overlap, group together
            if len(overlap) >= max(1, min(len(base_words), len(group_words)) - 1):
                keyword_groups[group_key].append({
                    "article_id": article_id,
                    "keyword": keyword,
                    "title": title,
                    "seo_score": seo_score or 0,
                    "word_count": word_count or 0,
                })
                matched = True
                break

        if not matched:
            keyword_groups[keyword.lower()].append({
                "article_id": article_id,
                "keyword": keyword,
                "title": title,
                "seo_score": seo_score or 0,
                "word_count": word_count or 0,
            })

    # Find groups with 2+ pages (consolidation candidates)
    candidates = []
    for group_keyword, pages in keyword_groups.items():
        if len(pages) >= 2:
            # Sort by score — best page becomes the target
            pages.sort(key=lambda x: x["seo_score"], reverse=True)
            target = pages[0]
            merge_sources = pages[1:]

            candidates.append({
                "group_keyword": group_keyword,
                "target_page": target,
                "merge_sources": merge_sources,
                "total_pages": len(pages),
                "combined_word_count": sum(p["word_count"] for p in pages),
                "reason": f"{len(pages)} pages targeting similar keyword '{group_keyword}'",
                "expected_benefit": "Combined ranking signals → stronger single page",
            })

    candidates.sort(key=lambda x: x["total_pages"], reverse=True)
    return candidates

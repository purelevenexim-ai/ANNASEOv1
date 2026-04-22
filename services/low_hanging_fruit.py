"""
================================================================================
LOW-HANGING FRUIT FINDER
================================================================================
Phase 7 / Ahrefs "Pick" step — Find keywords ranking 2-10 that can be quickly
boosted to get significantly more traffic.

From Ahrefs: "Two-thirds of clicks go to the top two results. Those ranking at
or near the bottom of page one are lucky to get even 1% of clicks."

Implements:
- Identify keywords in positions 2-10 (already on page 1 but not top spots)
- Score by traffic potential uplift
- Filter by business potential
- Generate optimization recommendations for each
- Separate quick-wins from longer-term improvements

Reference: Ahrefs "Pick: Find low-hanging fruit keywords to optimize for"
           Backlinko "Improve and Update Your Content"
================================================================================
"""

from __future__ import annotations
import logging
import sqlite3
from typing import Any, Dict, List

log = logging.getLogger("annaseo.low_hanging_fruit")


# ─────────────────────────────────────────────────────────────────────────────
# CTR MODEL — Estimated CTR by position (industry averages)
# ─────────────────────────────────────────────────────────────────────────────

POSITION_CTR = {
    1: 0.316,    # ~31.6%
    2: 0.241,    # ~24.1%
    3: 0.186,    # ~18.6%
    4: 0.105,    # ~10.5%
    5: 0.075,    # ~7.5%
    6: 0.050,    # ~5.0%
    7: 0.035,    # ~3.5%
    8: 0.025,    # ~2.5%
    9: 0.019,    # ~1.9%
    10: 0.015,   # ~1.5%
}


def _estimate_ctr(position: int) -> float:
    """Estimate CTR for a given SERP position."""
    if position <= 0:
        return 0
    return POSITION_CTR.get(min(position, 10), max(0.005, 0.316 / position))


def _traffic_uplift(current_pos: int, target_pos: int, monthly_searches: int) -> int:
    """Calculate estimated monthly traffic gain from position improvement."""
    current_ctr = _estimate_ctr(current_pos)
    target_ctr = _estimate_ctr(target_pos)
    gain = (target_ctr - current_ctr) * monthly_searches
    return max(0, int(gain))


# ─────────────────────────────────────────────────────────────────────────────
# LOW-HANGING FRUIT DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def find_low_hanging_fruit(
    db: sqlite3.Connection,
    project_id: str,
    min_position: int = 2,
    max_position: int = 10,
    min_impressions: int = 10,
) -> List[Dict[str, Any]]:
    """
    Find keywords already ranking on page 1 (positions 2-10) that could
    be boosted for significantly more traffic.

    Returns sorted list of opportunities with uplift estimates.
    """
    # Get latest rankings for each keyword
    rows = db.execute(
        """SELECT keyword, position, impressions, clicks,
                  COALESCE(
                    (SELECT ca.title FROM content_articles ca
                     WHERE ca.project_id = r.project_id AND ca.keyword = r.keyword
                     LIMIT 1), ''
                  ) as page_title
           FROM rankings r
           WHERE project_id = ?
             AND position >= ? AND position <= ?
             AND impressions >= ?
           ORDER BY position ASC""",
        (project_id, min_position, max_position, min_impressions),
    ).fetchall()

    opportunities = []
    seen_keywords = set()

    for row in rows:
        kw = row[0]
        if kw in seen_keywords:
            continue
        seen_keywords.add(kw)

        current_pos = int(row[1])
        impressions = row[2] or 0
        clicks = row[3] or 0
        page_title = row[4] or ""

        # Estimate monthly searches from impressions (rough: impressions ≈ searches if ranking well)
        est_monthly_searches = max(impressions, clicks * 10)

        # Calculate uplift to top 3 and top 1
        uplift_to_3 = _traffic_uplift(current_pos, 3, est_monthly_searches)
        uplift_to_1 = _traffic_uplift(current_pos, 1, est_monthly_searches)

        # Effort estimate: closer to top = easier to improve
        if current_pos <= 3:
            effort = "low"
            target_position = max(1, current_pos - 1)
        elif current_pos <= 5:
            effort = "low"
            target_position = 3
        elif current_pos <= 7:
            effort = "medium"
            target_position = 3
        else:
            effort = "medium_high"
            target_position = 5

        # Calculate opportunity score (higher = better opportunity)
        opp_score = round(
            (uplift_to_3 * 0.5) +
            (impressions * 0.003) +  # volume indicator
            ((11 - current_pos) * 5) +  # proximity to top
            (clicks * 0.1),  # proven engagement
            1,
        )

        recommendations = _get_optimization_recommendations(current_pos, impressions, clicks)

        opportunities.append({
            "keyword": kw,
            "current_position": current_pos,
            "target_position": target_position,
            "impressions": impressions,
            "clicks": clicks,
            "current_ctr": round(_estimate_ctr(current_pos) * 100, 1),
            "est_monthly_searches": est_monthly_searches,
            "uplift_to_top_3": uplift_to_3,
            "uplift_to_top_1": uplift_to_1,
            "opportunity_score": opp_score,
            "effort": effort,
            "page_title": page_title,
            "recommendations": recommendations,
        })

    # Sort by opportunity score (descending)
    opportunities.sort(key=lambda x: x["opportunity_score"], reverse=True)

    log.info("[LHF] Found %d low-hanging fruit keywords for project %s", len(opportunities), project_id)
    return opportunities


# ─────────────────────────────────────────────────────────────────────────────
# OPTIMIZATION RECOMMENDATIONS (Ahrefs "Press" step)
# ─────────────────────────────────────────────────────────────────────────────

def _get_optimization_recommendations(position: int, impressions: int, clicks: int) -> List[Dict[str, str]]:
    """
    Generate optimization recommendations based on position.
    Order: easy things first, then harder tasks (per Ahrefs methodology).

    Ahrefs Press order:
    a) Cover topic fully
    b) On-page SEO (title, meta)
    c) Internal links
    d) Backlink profile
    """
    recs = []

    # a) Content completeness — always check first
    recs.append({
        "type": "content_completeness",
        "action": "Review competing pages and add missing subtopics",
        "detail": "Use competitive analysis to find keywords competitors rank for that you don't. Add those subtopics.",
        "effort": "medium",
        "impact": "high",
    })

    # b) On-page SEO — quick wins
    actual_ctr = (clicks / max(impressions, 1)) * 100
    expected_ctr = _estimate_ctr(position) * 100
    if actual_ctr < expected_ctr * 0.7:
        recs.append({
            "type": "title_meta_optimization",
            "action": "Improve title tag and meta description for higher CTR",
            "detail": f"Current CTR ({actual_ctr:.1f}%) is below expected ({expected_ctr:.1f}%). Make title more compelling and add 'examples' or specific numbers.",
            "effort": "low",
            "impact": "medium",
        })
    else:
        recs.append({
            "type": "title_meta_optimization",
            "action": "Check title tag alignment with search intent",
            "detail": "Review top-ranking titles. Ensure yours includes the key angle searchers want.",
            "effort": "low",
            "impact": "medium",
        })

    # c) Internal links — quick win
    recs.append({
        "type": "internal_links",
        "action": "Add relevant internal links pointing to this page",
        "detail": "Find pages on your site that mention this topic but don't link to this page. Add contextual internal links.",
        "effort": "low",
        "impact": "medium",
    })

    # d) Backlinks — higher effort
    if position > 5:
        recs.append({
            "type": "backlink_acquisition",
            "action": "Build quality backlinks to close the gap with top-ranking pages",
            "detail": "Analyze backlink profiles of pages ranking above you. Identify link sources you can replicate.",
            "effort": "high",
            "impact": "high",
        })

    # Bonus: Content freshness
    recs.append({
        "type": "content_freshness",
        "action": "Update content with latest examples and data",
        "detail": "Replace outdated screenshots, update statistics, and add recent examples.",
        "effort": "low",
        "impact": "medium",
    })

    return recs


# ─────────────────────────────────────────────────────────────────────────────
# QUICK WINS vs LONG-TERM OPPORTUNITIES
# ─────────────────────────────────────────────────────────────────────────────

def categorize_opportunities(opportunities: List[Dict]) -> Dict[str, List[Dict]]:
    """Split opportunities into quick wins and longer-term projects."""
    quick_wins = []     # positions 2-5, low effort
    medium_term = []    # positions 4-7, medium effort
    long_term = []      # positions 7-10, higher effort

    for opp in opportunities:
        pos = opp["current_position"]
        if pos <= 5:
            quick_wins.append(opp)
        elif pos <= 7:
            medium_term.append(opp)
        else:
            long_term.append(opp)

    return {
        "quick_wins": quick_wins,
        "quick_wins_count": len(quick_wins),
        "medium_term": medium_term,
        "medium_term_count": len(medium_term),
        "long_term": long_term,
        "long_term_count": len(long_term),
        "total_potential_uplift": sum(o["uplift_to_top_3"] for o in opportunities),
    }

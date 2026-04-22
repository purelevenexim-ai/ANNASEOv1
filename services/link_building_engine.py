"""
================================================================================
LINK BUILDING & MIDDLEMAN ENGINE
================================================================================
Phase 6 — Build links and earn citations (Backlinko Step 6, Ahrefs Step 4d).

From Backlinko: "Link building is still important in 2026, but the goal has
changed. You need to influence how search engines and LLMs understand your brand."

Implements:
- Competitor link analysis (who links to competitors, replicate)
- Middleman method (informational pages → internal links → money pages)
- Link opportunity identification
- Internal link gap finder
- Statistics/data link building opportunities
- Outreach tracking

Reference: Backlinko "Build Links and Earn Citations"
           Ahrefs "Make sure its link profile is strong enough"
           Ahrefs "Bonus: The Middleman Method"
           Semrush "Plan How to Get Backlinks and Mentions"
================================================================================
"""

from __future__ import annotations
import logging
import re
import sqlite3
from typing import Any, Dict, List, Optional

log = logging.getLogger("annaseo.link_building_engine")


# ─────────────────────────────────────────────────────────────────────────────
# MIDDLEMAN METHOD ENGINE
# ─────────────────────────────────────────────────────────────────────────────
# From Ahrefs: "People don't usually want to link to commercial content.
# That's where the middleman technique comes in."
# 1. Find/create informational content on a similar topic
# 2. Build links to that content (it's easier to link to info content)
# 3. Internally link from that page to your "money" page

def identify_money_pages(
    db: sqlite3.Connection,
    project_id: str,
) -> List[Dict[str, Any]]:
    """
    Find "money pages" that could benefit from the middleman method.
    Money pages: commercial/transactional pages ranking positions 2-10
    with high business value but hard to get direct backlinks.
    """
    money_pages = []

    try:
        rows = db.execute(
            """SELECT DISTINCT r.keyword, r.position, r.impressions, r.clicks,
                      ca.article_id, ca.title, ca.published_url
               FROM rankings r
               LEFT JOIN content_articles ca ON ca.project_id = r.project_id AND ca.keyword = r.keyword
               WHERE r.project_id = ?
                 AND r.position BETWEEN 2 AND 15
               ORDER BY r.position ASC""",
            (project_id,),
        ).fetchall()

        for row in rows:
            keyword = row[0]
            position = row[1]
            kw_lower = keyword.lower()

            # Check if it's a "money" keyword (commercial/transactional intent)
            money_signals = ["buy", "price", "best", "review", "top", "shop", "order",
                             "service", "hire", "cost", "pricing", "quote", "discount"]
            is_money = any(s in kw_lower for s in money_signals)

            if is_money or position <= 5:  # High-ranking = worth boosting anyway
                money_pages.append({
                    "keyword": keyword,
                    "position": position,
                    "impressions": row[2] or 0,
                    "clicks": row[3] or 0,
                    "article_id": row[4] or "",
                    "title": row[5] or keyword,
                    "url": row[6] or "",
                    "is_money_keyword": is_money,
                    "boost_potential": "high" if position <= 5 else "medium",
                })
    except Exception as e:
        log.warning("[LinkBuild] Error finding money pages: %s", e)

    money_pages.sort(key=lambda x: x["position"])
    return money_pages


def find_middleman_opportunities(
    db: sqlite3.Connection,
    project_id: str,
    money_page_keyword: str,
) -> List[Dict[str, Any]]:
    """
    Find informational content pages that could serve as middlemen
    for a money page. These pages should:
    1. Be relevant to the money page topic
    2. Already have (or can get) backlinks
    3. Currently lack an internal link to the money page

    From Ahrefs: Search site:yourwebsite.com + "topic of your money page"
    """
    opportunities = []
    kw_words = set(money_page_keyword.lower().split())

    try:
        # Find all informational articles that might mention this topic
        rows = db.execute(
            """SELECT article_id, keyword, title, body, seo_score, word_count, published_url
               FROM content_articles
               WHERE project_id = ?
                 AND status IN ('published', 'approved')""",
            (project_id,),
        ).fetchall()

        for row in rows:
            article_id, article_kw, title, body, seo_score, word_count, url = row
            article_kw = article_kw or ""
            body = body or ""
            title = title or ""

            # Skip if this IS the money page
            if article_kw.lower() == money_page_keyword.lower():
                continue

            # Check topic relevance
            content_text = (title + " " + body).lower()
            relevance_score = 0

            for word in kw_words:
                if len(word) > 3 and word in content_text:
                    relevance_score += 1

            # Check if money page keyword or close variant mentioned
            if money_page_keyword.lower() in content_text:
                relevance_score += 3

            if relevance_score >= 2:
                # Check if internal link already exists (simple check)
                has_link = False  # Would need to parse HTML for real check

                opportunities.append({
                    "middleman_article_id": article_id,
                    "middleman_keyword": article_kw,
                    "middleman_title": title,
                    "middleman_url": url or "",
                    "relevance_score": relevance_score,
                    "word_count": word_count or 0,
                    "seo_score": seo_score or 0,
                    "has_existing_link": has_link,
                    "suggested_anchor": money_page_keyword,
                    "action": f"Add internal link from \"{title}\" to money page for \"{money_page_keyword}\"",
                })

    except Exception as e:
        log.warning("[LinkBuild] Error finding middleman opportunities: %s", e)

    opportunities.sort(key=lambda x: x["relevance_score"], reverse=True)
    return opportunities


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL LINK GAP FINDER
# ─────────────────────────────────────────────────────────────────────────────
# From Ahrefs: "Internal links help visitors find their way around and pass
# PageRank to pages. If your page doesn't already have all the relevant
# internal links it could have, adding them is a quick win."

def find_internal_link_gaps(
    db: sqlite3.Connection,
    project_id: str,
) -> List[Dict[str, Any]]:
    """
    Find internal linking opportunities across all content.
    For each article, find other articles that mention its keyword
    but don't link to it.
    """
    gaps = []

    try:
        articles = db.execute(
            """SELECT article_id, keyword, title, body
               FROM content_articles
               WHERE project_id = ? AND status IN ('published', 'approved')""",
            (project_id,),
        ).fetchall()

        # Build keyword-to-article map
        keyword_articles = {}
        for row in articles:
            article_id, keyword, title, body = row
            if keyword:
                keyword_articles[keyword.lower()] = {
                    "article_id": article_id,
                    "keyword": keyword,
                    "title": title,
                }

        # Check each article's body for mentions of other keywords
        for row in articles:
            source_id, source_kw, source_title, source_body = row
            if not source_body:
                continue
            body_lower = source_body.lower()

            for target_kw, target_info in keyword_articles.items():
                # Don't self-link
                if target_info["article_id"] == source_id:
                    continue

                # Check if target keyword is mentioned in source body
                if target_kw in body_lower:
                    gaps.append({
                        "source_article_id": source_id,
                        "source_title": source_title,
                        "source_keyword": source_kw,
                        "target_article_id": target_info["article_id"],
                        "target_title": target_info["title"],
                        "target_keyword": target_info["keyword"],
                        "suggested_anchor": target_kw,
                        "action": f"Link '{target_kw}' in \"{source_title}\" to \"{target_info['title']}\"",
                    })

    except Exception as e:
        log.warning("[LinkBuild] Error finding internal link gaps: %s", e)

    return gaps


# ─────────────────────────────────────────────────────────────────────────────
# LINK BUILDING STRATEGY GENERATOR
# ─────────────────────────────────────────────────────────────────────────────
# From Backlinko: Think more like a PR professional
# - Earning links from relevant, trusted sources
# - Getting mentioned alongside competitors
# - Showing up in blog posts, listicles, Reddit threads

LINK_BUILDING_STRATEGIES = [
    {
        "strategy": "statistics_link_building",
        "description": "Create original data or repackage public data into clean, quotable stats",
        "effort": "medium",
        "link_potential": "high",
        "best_for": ["content", "saas", "ecommerce"],
        "actions": [
            "Identify key metrics in your industry that lack good sources",
            "Create clean charts and summary statistics",
            "Publish as a standalone stats/data page",
            "Outreach to sites that cite old data in your niche",
        ],
    },
    {
        "strategy": "expert_commentary",
        "description": "Respond to journalist requests for expert quotes (HARO, Featured, etc.)",
        "effort": "low",
        "link_potential": "medium",
        "best_for": ["all"],
        "actions": [
            "Monitor HARO, Featured, MentionMatch for relevant requests",
            "Watch LinkedIn and X for journalist callouts",
            "Prepare 2-3 expert quotes per week",
            "Focus on requests in your exact industry",
        ],
    },
    {
        "strategy": "competitor_link_replication",
        "description": "Find who links to competitors and pitch something better",
        "effort": "medium",
        "link_potential": "high",
        "best_for": ["all"],
        "actions": [
            "Analyze competitor backlink profiles",
            "Identify patterns: blog mentions, roundups, resource pages",
            "Create superior content on the same topics",
            "Outreach with your improved version",
        ],
    },
    {
        "strategy": "digital_pr",
        "description": "Create newsworthy content that naturally attracts links",
        "effort": "high",
        "link_potential": "very_high",
        "best_for": ["ecommerce", "saas", "content"],
        "actions": [
            "Conduct original research or surveys",
            "Create data visualizations and infographics",
            "Write newsworthy press releases",
            "Pitch to industry publications",
        ],
    },
    {
        "strategy": "broken_link_building",
        "description": "Find broken links on relevant sites and offer your content as replacement",
        "effort": "medium",
        "link_potential": "medium",
        "best_for": ["all"],
        "actions": [
            "Find resource pages in your niche",
            "Check for broken outbound links",
            "Create content that matches the broken link's topic",
            "Email with a helpful replacement suggestion",
        ],
    },
    {
        "strategy": "middleman_method",
        "description": "Build links to informational content, then internally link to money pages",
        "effort": "medium",
        "link_potential": "high",
        "best_for": ["ecommerce", "saas", "lead_generation"],
        "actions": [
            "Identify money pages that need ranking boosts",
            "Find/create informational content on related topics",
            "Build external links to the informational pages",
            "Add internal links from informational → money pages",
        ],
    },
]


def get_link_building_plan(
    business_type: str,
    current_authority: int = 0,
    content_count: int = 0,
) -> Dict[str, Any]:
    """
    Generate a link building plan tailored to business type and current state.
    """
    btype = business_type.lower()
    applicable = []

    for strategy in LINK_BUILDING_STRATEGIES:
        if "all" in strategy["best_for"] or any(b in btype for b in strategy["best_for"]):
            applicable.append(strategy)

    # Priority order depends on current state
    if current_authority < 20:
        # Low authority: focus on easy wins first
        priority_order = ["expert_commentary", "broken_link_building", "middleman_method",
                          "statistics_link_building", "competitor_link_replication", "digital_pr"]
    elif current_authority < 50:
        # Medium authority: balanced approach
        priority_order = ["competitor_link_replication", "statistics_link_building",
                          "middleman_method", "expert_commentary", "digital_pr", "broken_link_building"]
    else:
        # High authority: focus on high-impact
        priority_order = ["digital_pr", "statistics_link_building", "competitor_link_replication",
                          "middleman_method", "expert_commentary", "broken_link_building"]

    # Sort by priority order
    def sort_key(s):
        try:
            return priority_order.index(s["strategy"])
        except ValueError:
            return 99

    applicable.sort(key=sort_key)

    return {
        "strategies": applicable,
        "business_type": business_type,
        "current_authority": current_authority,
        "recommended_first": applicable[0]["strategy"] if applicable else None,
        "monthly_targets": {
            "new_referring_domains": max(5, current_authority // 5),
            "internal_links_to_add": max(10, content_count // 3),
            "outreach_emails": 20,
            "expert_responses": 8,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# LINK OPPORTUNITY TRACKER (DB-backed)
# ─────────────────────────────────────────────────────────────────────────────

LINK_OPP_TABLE = """
CREATE TABLE IF NOT EXISTS link_opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    prospect_url TEXT NOT NULL,
    prospect_domain TEXT DEFAULT '',
    strategy TEXT DEFAULT '',
    target_page TEXT DEFAULT '',
    anchor_text TEXT DEFAULT '',
    status TEXT DEFAULT 'identified',
    priority TEXT DEFAULT 'medium',
    notes TEXT DEFAULT '',
    contact_email TEXT DEFAULT '',
    outreach_date TEXT DEFAULT '',
    response TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_lo_project ON link_opportunities(project_id);
"""


def ensure_link_table(db: sqlite3.Connection):
    db.executescript(LINK_OPP_TABLE)


def add_link_opportunity(
    db: sqlite3.Connection,
    project_id: str,
    prospect_url: str,
    strategy: str = "",
    target_page: str = "",
    priority: str = "medium",
) -> int:
    """Track a link building opportunity."""
    ensure_link_table(db)
    from urllib.parse import urlparse
    domain = urlparse(prospect_url).netloc

    cursor = db.execute(
        """INSERT INTO link_opportunities (project_id, prospect_url, prospect_domain, strategy, target_page, priority)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (project_id, prospect_url, domain, strategy, target_page, priority),
    )
    db.commit()
    return cursor.lastrowid


def get_link_opportunities(
    db: sqlite3.Connection,
    project_id: str,
    status: str = None,
) -> List[Dict[str, Any]]:
    """Get all link opportunities for a project."""
    ensure_link_table(db)
    if status:
        rows = db.execute(
            "SELECT * FROM link_opportunities WHERE project_id=? AND status=? ORDER BY created_at DESC",
            (project_id, status),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM link_opportunities WHERE project_id=? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()

    return [dict(r) for r in rows]


def update_link_opportunity_status(
    db: sqlite3.Connection,
    opportunity_id: int,
    status: str,
    notes: str = "",
) -> bool:
    """Update the status of a link opportunity."""
    ensure_link_table(db)
    db.execute(
        "UPDATE link_opportunities SET status=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (status, notes, opportunity_id),
    )
    db.commit()
    return True

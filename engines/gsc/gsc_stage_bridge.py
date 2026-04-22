"""
GSC Engine — Stage Bridge (Phase 3)
Bridges data from kw2 Stage 1 (Business Profile) and Stage 2 (Keywords)
into the GSC Intelligence pipeline.

This allows the GSC module to work WITHOUT requiring a live GSC OAuth
connection — it uses keyword data already collected in earlier stages.
"""
import json as _json
import logging
import os
import sqlite3
from datetime import datetime

from . import gsc_db

log = logging.getLogger(__name__)

_DB_PATH = os.getenv("ANNASEO_DB", "./annaseo.db")


def _conn():
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


# ─── Data Collectors ─────────────────────────────────────────────────────────

def get_business_profile(project_id: str) -> dict | None:
    """Load business profile from kw2 Stage 1."""
    try:
        with _conn() as conn:
            row = conn.execute(
                "SELECT * FROM kw2_business_profile WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            for key in ("pillars", "product_catalog", "modifiers", "audience",
                        "intent_signals", "negative_scope", "raw_ai_json", "manual_input"):
                if isinstance(d.get(key), str):
                    try:
                        d[key] = _json.loads(d[key])
                    except (ValueError, TypeError):
                        pass
            return d
    except Exception as e:
        log.warning(f"[StageBridge] Profile read error: {e}")
        return None


def get_kw2_session(project_id: str) -> dict | None:
    """Get the most recent kw2 session for a project."""
    try:
        with _conn() as conn:
            row = conn.execute(
                "SELECT * FROM kw2_sessions WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                (project_id,),
            ).fetchone()
            return dict(row) if row else None
    except Exception as e:
        log.warning(f"[StageBridge] Session read error: {e}")
        return None


def get_universe_keywords(session_id: str) -> list[dict]:
    """Load keyword universe from kw2 Stage 2."""
    try:
        with _conn() as conn:
            rows = conn.execute(
                "SELECT * FROM kw2_universe_items WHERE session_id = ?",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        log.warning(f"[StageBridge] Universe read error: {e}")
        return []


def get_validated_keywords(session_id: str) -> list[dict]:
    """Load validated keywords from kw2 Stage 3."""
    try:
        with _conn() as conn:
            rows = conn.execute(
                "SELECT * FROM kw2_validated_keywords WHERE session_id = ?",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        log.warning(f"[StageBridge] Validated read error: {e}")
        return []


def get_competitors(session_id: str) -> list[dict]:
    """Load competitor data from kw2 BI stage."""
    try:
        with _conn() as conn:
            rows = conn.execute(
                "SELECT * FROM kw2_biz_competitors WHERE session_id = ?",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        log.warning(f"[StageBridge] Competitor read error: {e}")
        return []


def get_competitor_keywords(session_id: str) -> list[dict]:
    """Load competitor keywords from kw2 BI stage."""
    try:
        with _conn() as conn:
            rows = conn.execute(
                "SELECT * FROM kw2_biz_competitor_keywords WHERE session_id = ?",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        log.warning(f"[StageBridge] Competitor keywords read error: {e}")
        return []


def get_ki_keywords(project_id: str) -> list[dict]:
    """Load keywords from the older KI crawl engine (pillar_keywords + keyword_universe_items)."""
    result = []
    try:
        with _conn() as conn:
            # Pillar keywords from crawl
            rows = conn.execute(
                "SELECT keyword, intent, priority, source FROM pillar_keywords WHERE project_id = ?",
                (project_id,),
            ).fetchall()
            for r in rows:
                d = dict(r)
                d["_source"] = "ki_pillar"
                result.append(d)

            # Find latest session for KI universe
            sess = conn.execute(
                "SELECT id FROM keyword_input_sessions WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                (project_id,),
            ).fetchone()
            if sess:
                rows = conn.execute(
                    "SELECT keyword, pillar, intent, score, source, status FROM keyword_universe_items "
                    "WHERE session_id = ? AND status != 'deleted'",
                    (sess["id"],),
                ).fetchall()
                for r in rows:
                    d = dict(r)
                    d["_source"] = "ki_universe"
                    result.append(d)
    except Exception as e:
        log.warning(f"[StageBridge] KI keywords read error: {e}")
    return result


# ─── Stage Data Aggregator ────────────────────────────────────────────────────

def get_stage_data(project_id: str) -> dict:
    """
    Collect ALL available data from Stage 1 + Stage 2 for a project.
    Returns a comprehensive dict with profile, keywords, competitors.
    """
    profile = get_business_profile(project_id)
    session = get_kw2_session(project_id)
    session_id = session["id"] if session else None

    universe = get_universe_keywords(session_id) if session_id else []
    validated = get_validated_keywords(session_id) if session_id else []
    competitors = get_competitors(session_id) if session_id else []
    comp_keywords = get_competitor_keywords(session_id) if session_id else []
    ki_keywords = get_ki_keywords(project_id)

    # Extract proper pillars (manual > AI product names)
    raw_pillars = []
    manual_pillars = []
    products = []
    if profile:
        manual_input = profile.get("manual_input") or {}
        if isinstance(manual_input, str):
            try:
                manual_input = _json.loads(manual_input)
            except (ValueError, TypeError):
                manual_input = {}
        manual_pillars = manual_input.get("pillars", [])
        products = profile.get("product_catalog", [])
        if isinstance(products, str):
            try:
                products = _json.loads(products)
            except (ValueError, TypeError):
                products = []
        raw_pillars = profile.get("pillars", [])
        if isinstance(raw_pillars, str):
            try:
                raw_pillars = _json.loads(raw_pillars)
            except (ValueError, TypeError):
                raw_pillars = []

    return {
        "profile": profile,
        "session": session,
        "manual_pillars": manual_pillars,
        "ai_pillars": raw_pillars,
        "products": products,
        "universe_keywords": universe,
        "validated_keywords": validated,
        "ki_keywords": ki_keywords,
        "competitors": competitors,
        "competitor_keywords": comp_keywords,
        "stats": {
            "has_profile": profile is not None,
            "manual_pillar_count": len(manual_pillars),
            "ai_pillar_count": len(raw_pillars),
            "product_count": len(products),
            "universe_count": len(universe),
            "validated_count": len(validated),
            "ki_keyword_count": len(ki_keywords),
            "competitor_count": len(competitors),
            "competitor_keyword_count": len(comp_keywords),
        },
    }


# ─── Import to GSC ───────────────────────────────────────────────────────────

def import_keywords_to_gsc(project_id: str) -> dict:
    """
    Import all keyword data from Stage 1+2 into the GSC raw keywords table.
    Converts kw2/KI keyword formats to GSC raw format.
    Returns import stats.
    """
    stage = get_stage_data(project_id)
    gsc_db.init_tables()

    imported = []
    seen = set()

    def _add(keyword: str, clicks=0, impressions=0, ctr=0.0, position=0.0, source="stage"):
        kw_clean = keyword.strip().lower()
        if not kw_clean or kw_clean in seen:
            return
        seen.add(kw_clean)
        imported.append({
            "keys": [keyword.strip()],
            "clicks": clicks,
            "impressions": max(impressions, 10),  # give imported keywords a base impression
            "ctr": ctr,
            "position": position or 50.0,  # default position for non-GSC data
        })

    # From validated keywords (highest quality)
    for kw in stage["validated_keywords"]:
        _add(
            kw.get("keyword", ""),
            impressions=kw.get("impressions", 50),
            clicks=kw.get("clicks", 0),
            position=kw.get("position", 30.0),
        )

    # From universe keywords
    for kw in stage["universe_keywords"]:
        _add(
            kw.get("keyword", ""),
            impressions=kw.get("impressions", 20),
        )

    # From KI keywords
    for kw in stage["ki_keywords"]:
        _add(
            kw.get("keyword", ""),
            impressions=50 if kw.get("_source") == "ki_pillar" else 20,
        )

    # From competitor keywords
    for kw in stage["competitor_keywords"]:
        _add(
            kw.get("keyword", ""),
            impressions=kw.get("impressions", 30),
        )

    # From product catalog (expand into search terms)
    for product in stage["products"]:
        if isinstance(product, str):
            _add(product, impressions=10)

    if not imported:
        return {"imported": 0, "message": "No keyword data found in Stage 1+2. Run earlier stages first."}

    # Store as GSC raw keywords
    now = datetime.utcnow()
    gsc_db.upsert_raw_keywords(
        project_id,
        imported,
        date_start=now.strftime("%Y-%m-%d"),
        date_end=now.strftime("%Y-%m-%d"),
    )

    # Mark as connected via stage import
    gsc_db.upsert_integration(
        project_id,
        status="connected_stages",
        site_url="stage-import",
    )

    stats = gsc_db.get_stats(project_id)
    log.info(f"[StageBridge] Imported {len(imported)} keywords for {project_id}")
    return {
        "imported": len(imported),
        "total_in_db": stats["raw_count"],
        "sources": {
            "validated": len(stage["validated_keywords"]),
            "universe": len(stage["universe_keywords"]),
            "ki": len(stage["ki_keywords"]),
            "competitors": len(stage["competitor_keywords"]),
            "products": len(stage["products"]),
        },
    }


# ─── AI Intelligence Summary ─────────────────────────────────────────────────

def generate_intelligence_summary(project_id: str) -> dict:
    """
    Use AI to generate an intelligence summary from all available Stage 1+2 data.
    This replaces static pillar tags with dynamic AI analysis.
    """
    from core.ai_config import AIRouter

    stage = get_stage_data(project_id)
    profile = stage["profile"]

    if not profile:
        return {"error": "No business profile found. Complete Stage 1 first."}

    # Prepare context for AI
    manual_pillars = stage["manual_pillars"]
    products = stage["products"][:20]  # limit for prompt size
    modifiers = profile.get("modifiers", [])
    business_type = profile.get("business_type", "unknown")
    geo = profile.get("geo_scope", "")
    audience = profile.get("audience", [])
    universe = profile.get("universe", "")

    # Keyword stats
    kw_count = stage["stats"]["universe_count"] + stage["stats"]["ki_keyword_count"]
    comp_count = stage["stats"]["competitor_count"]

    # Sample keywords for context
    sample_kws = []
    for kw in stage["ki_keywords"][:30]:
        sample_kws.append(kw.get("keyword", ""))
    for kw in stage["universe_keywords"][:20]:
        sample_kws.append(kw.get("keyword", ""))
    for kw in stage["validated_keywords"][:20]:
        sample_kws.append(kw.get("keyword", ""))
    sample_kws = list(set(filter(None, sample_kws)))[:40]

    # Competitor info
    comp_info = []
    for c in stage["competitors"][:5]:
        comp_info.append(c.get("domain", c.get("url", "")))

    prompt = f"""Analyze this SEO project and provide a comprehensive intelligence summary.

BUSINESS PROFILE:
- Type: {business_type}
- Market: {universe}
- Geography: {geo}
- Audience: {_json.dumps(audience) if audience else 'Not specified'}
- User-defined pillars: {_json.dumps(manual_pillars)}
- Products/services: {_json.dumps(products[:15])}
- Modifiers: {_json.dumps(modifiers)}

KEYWORD DATA:
- Total keywords collected: {kw_count}
- Sample keywords: {_json.dumps(sample_kws[:30])}

COMPETITORS: {_json.dumps(comp_info) if comp_info else 'None analyzed yet'}

Return a JSON object with EXACTLY this structure:
{{
  "business_summary": "One paragraph describing the business and its SEO position",
  "recommended_pillars": ["pillar1", "pillar2", "pillar3"],
  "pillar_analysis": [
    {{"name": "pillar_name", "opportunity": "high/medium/low", "reason": "brief reason", "keyword_focus": ["example keywords"]}}
  ],
  "intent_strategy": {{
    "primary_intent": "purchase/informational/commercial",
    "reasoning": "why this intent should be prioritized",
    "purchase_signals": ["buy", "price", "etc"],
    "supporting_angles": ["benefits", "guide", "etc"]
  }},
  "competitor_gaps": ["opportunity 1", "opportunity 2"],
  "quick_recommendations": ["recommendation 1", "recommendation 2", "recommendation 3"],
  "target_keywords_estimate": {kw_count or 'unknown'},
  "confidence": 0.8
}}

IMPORTANT:
- recommended_pillars should be PROPER SEO topic pillars (like "Black Pepper", "Cardamom", "Cinnamon"), NOT product SKU names with weights
- Analyze the products list to extract the real topic categories
- Be specific to this business, not generic
- Return ONLY valid JSON, no markdown"""

    try:
        router = AIRouter()
        raw = router.call(prompt)
        # Parse JSON from response
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
        summary = _json.loads(text)
    except _json.JSONDecodeError:
        # Try to extract JSON from response
        import re
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                summary = _json.loads(match.group())
            except _json.JSONDecodeError:
                summary = {
                    "business_summary": f"{business_type} business in {geo or 'unspecified'} market",
                    "recommended_pillars": manual_pillars or [p.split(" - ")[0].strip() for p in products[:5]],
                    "pillar_analysis": [],
                    "intent_strategy": {"primary_intent": "purchase", "reasoning": "Default"},
                    "competitor_gaps": [],
                    "quick_recommendations": ["Complete earlier analysis stages for better recommendations"],
                    "confidence": 0.3,
                }
        else:
            summary = {
                "business_summary": f"{business_type} business in {geo or 'unspecified'} market",
                "recommended_pillars": manual_pillars or [p.split(" - ")[0].strip() for p in products[:5]],
                "pillar_analysis": [],
                "intent_strategy": {"primary_intent": "purchase"},
                "competitor_gaps": [],
                "quick_recommendations": ["Run AI analysis stages first"],
                "confidence": 0.2,
            }
    except Exception as e:
        log.error(f"[StageBridge] AI summary error: {e}")
        summary = {
            "business_summary": f"{business_type} business",
            "recommended_pillars": manual_pillars or [],
            "error": str(e),
            "confidence": 0.1,
        }

    # Enrich with stats
    summary["stage_stats"] = stage["stats"]
    summary["profile_source"] = "ai" if not manual_pillars else "manual+ai"

    # Save to DB
    gsc_db.save_intelligence_summary(project_id, summary)

    return summary

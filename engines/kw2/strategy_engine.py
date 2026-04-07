"""
kw2 Phase 9 — Strategy Engine.

Generates an AI-powered SEO strategy document based on
the full keyword research pipeline results (profile, tree,
clusters, graph, links, calendar).
"""
import json
import logging

from engines.kw2.prompts import STRATEGY_SYSTEM, STRATEGY_USER
from engines.kw2.ai_caller import kw2_ai_call, kw2_extract_json
from engines.kw2 import db

log = logging.getLogger("kw2.strategy")


class StrategyEngine:
    """Phase 9: Generate SEO strategy from pipeline data."""

    def generate(
        self,
        project_id: str,
        session_id: str,
        ai_provider: str = "auto",
    ) -> dict:
        """
        Generate strategy document by aggregating all kw2 pipeline data
        and asking AI for a comprehensive strategy.

        Returns strategy dict with sections:
        - executive_summary
        - pillar_strategies (per-pillar action plan)
        - quick_wins (top 10 low-effort high-impact keywords)
        - content_priorities (what to publish first)
        - link_building_plan (internal linking priorities)
        - competitive_gaps (areas competitors cover that we don't)
        - timeline (recommended execution timeline)
        """
        profile = db.load_business_profile(project_id)
        if not profile:
            raise ValueError("No business profile. Run Phase 1 first.")

        session = db.get_session(session_id)
        if not session:
            raise ValueError("Session not found.")

        keywords = db.load_validated_keywords(session_id)

        conn = db.get_conn()
        try:
            cluster_rows = conn.execute(
                "SELECT * FROM kw2_clusters WHERE session_id=?", (session_id,)
            ).fetchall()
            link_rows = conn.execute(
                "SELECT link_type, COUNT(*) as cnt FROM kw2_internal_links WHERE session_id=? GROUP BY link_type",
                (session_id,),
            ).fetchall()
            calendar_rows = conn.execute(
                "SELECT COUNT(*) as cnt, MIN(scheduled_date) as first_date, MAX(scheduled_date) as last_date FROM kw2_calendar WHERE session_id=?",
                (session_id,),
            ).fetchone()
        finally:
            conn.close()

        # Build context for AI
        top_keywords = keywords[:30]
        kw_summary = "\n".join(
            f"- {kw['keyword']} (score={kw.get('final_score',0):.1f}, intent={kw.get('intent','')}, pillar={kw.get('pillar','')})"
            for kw in top_keywords
        )

        cluster_summary = "\n".join(
            f"- {dict(cr).get('cluster_name','')}: {dict(cr).get('top_keyword','')}"
            for cr in cluster_rows[:20]
        )

        link_summary = "\n".join(
            f"- {dict(lr)['link_type']}: {dict(lr)['cnt']} links"
            for lr in link_rows
        )

        cal_dict = dict(calendar_rows) if calendar_rows else {}
        calendar_summary = (
            f"Calendar: {cal_dict.get('cnt', 0)} articles from {cal_dict.get('first_date', 'N/A')} to {cal_dict.get('last_date', 'N/A')}"
        )

        pillars_str = ", ".join(profile.get("pillars", []))
        audience = profile.get("audience", [])
        audience_str = ", ".join(audience) if isinstance(audience, list) else str(audience)

        prompt = STRATEGY_USER.format(
            universe=profile.get("universe", "Business"),
            business_type=profile.get("business_type", "unknown"),
            pillars=pillars_str,
            count=len(top_keywords),
            top_keywords=kw_summary,
            clusters=cluster_summary,
            audience=audience_str,
            geo_scope=profile.get("geo_scope", "unknown"),
        )

        response = kw2_ai_call(prompt, STRATEGY_SYSTEM, provider=ai_provider, temperature=0.4)

        strategy = kw2_extract_json(response)
        if not strategy or not isinstance(strategy, dict):
            # Fallback: wrap raw text
            strategy = {
                "executive_summary": response[:2000],
                "pillar_strategies": [],
                "quick_wins": [kw["keyword"] for kw in top_keywords[:10]],
                "content_priorities": [],
                "link_building_plan": "",
                "competitive_gaps": [],
                "timeline": "See content calendar.",
            }

        # Ensure required keys
        defaults = {
            "executive_summary": "",
            "pillar_strategies": [],
            "quick_wins": [],
            "content_priorities": [],
            "link_building_plan": "",
            "competitive_gaps": [],
            "timeline": "",
        }
        for k, v in defaults.items():
            if k not in strategy:
                strategy[k] = v

        # Persist
        db.update_session(session_id, phase9_done=1, strategy_json=json.dumps(strategy))

        log.info(f"[Phase9] Strategy generated for {project_id}")
        return strategy

    def get_strategy(self, session_id: str) -> dict | None:
        """Load cached strategy from session."""
        session = db.get_session(session_id)
        if not session:
            return None
        raw = session.get("strategy_json", "")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

"""
kw2 Phase 9 — Strategy Engine v2.

Generates an AI-powered SEO strategy document using 4 sub-modules:
  2A — Business Analysis (profile + biz intel intelligence)
  2B — Keyword Intelligence (full dataset analysis)
  2C — Strategy Builder (full strategy from 2A + 2B)
  2D — Action Mapping (execution actions from strategy)

All outputs are versioned in kw2_strategy_versions.
"""
import json
import logging
import uuid
from datetime import datetime, timezone

from engines.kw2.prompts import (
    STRATEGY_SYSTEM, STRATEGY_USER,
    STRATEGY_V2_SYSTEM,
    STRATEGY_2A_USER, STRATEGY_2B_USER, STRATEGY_2C_USER, STRATEGY_2D_USER,
)
from concurrent.futures import ThreadPoolExecutor
from engines.kw2.ai_caller import kw2_ai_call, kw2_extract_json
from engines.kw2 import db

log = logging.getLogger("kw2.strategy")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid(prefix: str = "") -> str:
    short = uuid.uuid4().hex[:12]
    return f"{prefix}{short}" if prefix else short


def _safe_json(obj) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return "{}"


def _truncate(s: str, n: int) -> str:
    return s[:n] if s else ""


class StrategyEngine:
    """Phase 9: Generate SEO strategy from pipeline data — v2 with sub-modules."""

    # ── Public entry point ────────────────────────────────────────────────

    def generate(
        self,
        project_id: str,
        session_id: str,
        ai_provider: str = "auto",
        content_params: dict | None = None,
    ) -> dict:
        """
        Run 4 sub-modules sequentially and save a versioned strategy.
        Returns the final strategy dict (Module 2C output).
        """
        content_params = content_params or {}

        profile = db.load_business_profile(project_id)
        if not profile:
            raise ValueError("No business profile. Run Phase 1 first.")
        session = db.get_session(session_id)
        if not session:
            raise ValueError("Session not found.")

        # ── Load all data sources ─────────────────────────────────────────
        biz_intel = db.get_biz_intel(session_id) or {}
        biz_pages = db.get_biz_pages(session_id) or []
        biz_competitors = db.get_biz_competitors(session_id) or []
        keywords = db.load_validated_keywords(session_id)  # ALL keywords, no limit

        conn = db.get_conn()
        try:
            cluster_rows = conn.execute(
                "SELECT * FROM kw2_clusters WHERE session_id=?", (session_id,)
            ).fetchall()
            # Load intelligence questions if available
            question_rows = conn.execute(
                "SELECT question, content_type, intent, final_score FROM kw2_intelligence_questions WHERE session_id=? AND final_score > 0 AND is_duplicate=0 ORDER BY final_score DESC LIMIT 50",
                (session_id,),
            ).fetchall()
        except Exception:
            question_rows = []
        finally:
            conn.close()

        clusters = [dict(r) for r in cluster_rows]
        intelligence_questions = [dict(r) for r in question_rows] if question_rows else []

        # ── Modules 2A + 2B run in parallel (independent data sources) ───────────
        with ThreadPoolExecutor(max_workers=2) as _pool:
            _fut_2a = _pool.submit(
                self._run_module_2a,
                profile, biz_intel, biz_pages, biz_competitors,
                keywords, ai_provider, session_id, project_id,
            )
            _fut_2b = _pool.submit(
                self._run_module_2b,
                profile, keywords, clusters,
                ai_provider, session_id, project_id,
                intelligence_questions=intelligence_questions,
            )
            module_2a = _fut_2a.result()
            module_2b = _fut_2b.result()
        log.info("[Phase9/2A+2B] Business analysis + keyword intelligence complete (parallel)")

        # ── Module 2C — Strategy Builder ──────────────────────────────────
        strategy = self._run_module_2c(
            module_2a, module_2b, content_params,
            ai_provider, session_id, project_id,
        )
        log.info("[Phase9/2C] Strategy built")

        # ── B2: Pillar coverage guard ─────────────────────────────────────
        # Ensure every pillar from the business profile appears in priority_pillars.
        # Any gap is appended to content_gaps as an advisory note (no removal).
        _all_pillars = [str(p).strip() for p in profile.get("pillars", []) if p]
        _covered = {
            str(pp.get("pillar", "")).lower()
            for pp in strategy.get("priority_pillars", [])
            if isinstance(pp, dict)
        }
        _missing_pillars = [
            p for p in _all_pillars
            if p.lower() not in _covered
        ]
        if _missing_pillars:
            existing_gaps = strategy.setdefault("content_gaps", [])
            for mp in _missing_pillars:
                gap = f"[Pillar gap] '{mp}' pillar has no priority articles in the current strategy — add content coverage."
                if gap not in existing_gaps:
                    existing_gaps.append(gap)
            log.warning(
                "[Phase9/B2] %d pillar(s) missing from strategy: %s",
                len(_missing_pillars), _missing_pillars,
            )

        # ── Module 2D — Action Mapping ────────────────────────────────────
        module_2d = self._run_module_2d(
            strategy, keywords, clusters,
            ai_provider, session_id, project_id,
        )
        log.info("[Phase9/2D] Action mapping complete")

        # ── Persist versioned strategy ────────────────────────────────────
        version_id = self._save_version(
            session_id, project_id, strategy,
            module_2a, module_2b, module_2d,
            ai_provider, content_params,
        )
        log.info("[Phase9] Strategy version %s saved", version_id)

        # Keep backward-compat: also write to session.strategy_json
        db.update_session(
            session_id,
            phase9_done=1,
            strategy_json=_safe_json(strategy),
        )

        return strategy

    # ── Module 2A — Business Analysis ─────────────────────────────────────

    def _run_module_2a(
        self, profile, biz_intel, biz_pages, biz_competitors,
        keywords, provider, session_id, project_id,
    ) -> dict:
        pillars = profile.get("pillars", [])

        # Summarise pages
        page_lines = []
        for p in biz_pages[:20]:
            ptype = p.get("page_type", "")
            topic = p.get("primary_topic", "")
            intent = p.get("search_intent", "")
            if topic:
                page_lines.append(f"  [{ptype}] {topic} ({intent})")
        pages_summary = "\n".join(page_lines) if page_lines else "No pages crawled."

        prompt = STRATEGY_2A_USER.format(
            profile_json=_truncate(_safe_json(profile), 2000),
            biz_intel_json=_truncate(_safe_json({
                "goals": biz_intel.get("goals", []),
                "usps": biz_intel.get("usps", []),
                "audience_segments": biz_intel.get("audience_segments", []),
                "knowledge_summary": _truncate(biz_intel.get("knowledge_summary", ""), 800),
                "website_summary": _truncate(biz_intel.get("website_summary", ""), 600),
                "seo_strategy": _truncate(biz_intel.get("seo_strategy", ""), 500),
                "competitors": [
                    {
                        "domain": c.get("domain", ""),
                        "missed_opportunities": (
                            c.get("missed_opportunities", [])
                            if isinstance(c.get("missed_opportunities"), list)
                            else []
                        )[:3],
                        "weaknesses": (
                            c.get("weaknesses", [])
                            if isinstance(c.get("weaknesses"), list)
                            else []
                        )[:3],
                    }
                    for c in biz_competitors[:5]
                ],
            }), 3000),
            page_count=len(biz_pages),
            pages_summary=pages_summary,
            kw_count=len(keywords),
            pillars=", ".join(str(p) for p in pillars),
        )

        resp = kw2_ai_call(
            prompt, STRATEGY_V2_SYSTEM, provider=provider, temperature=0.3,
            session_id=session_id, project_id=project_id, task="strategy_2a",
        )
        result = kw2_extract_json(resp)
        return result if isinstance(result, dict) else {}

    # ── Module 2B — Keyword Intelligence ─────────────────────────────────

    def _run_module_2b(
        self, profile, keywords, clusters, provider, session_id, project_id,
        intelligence_questions=None,
    ) -> dict:
        universe = profile.get("universe", "Business")
        pillars = profile.get("pillars", [])

        # Full keyword analysis (no truncation)
        intent_counts: dict[str, int] = {}
        pillar_counts: dict[str, int] = {}
        for kw in keywords:
            intent = kw.get("intent", "unknown") or "unknown"
            pillar = kw.get("pillar", "unknown") or "unknown"
            intent_counts[intent] = intent_counts.get(intent, 0) + 1
            pillar_counts[pillar] = pillar_counts.get(pillar, 0) + 1

        intent_breakdown = "\n".join(
            f"  {intent}: {cnt}" for intent, cnt in sorted(intent_counts.items(), key=lambda x: -x[1])
        )
        pillar_breakdown = "\n".join(
            f"  {pillar}: {cnt}" for pillar, cnt in sorted(pillar_counts.items(), key=lambda x: -x[1])
        )

        # Top 50 by score
        sorted_kws = sorted(keywords, key=lambda k: k.get("final_score", 0), reverse=True)
        top_50 = "\n".join(
            f"  - {k['keyword']} (score={k.get('final_score',0):.1f}, intent={k.get('intent','')}, pillar={k.get('pillar','')})"
            for k in sorted_kws[:50]
        )

        # Cluster summary
        cluster_summary = "\n".join(
            f"  - {c.get('cluster_name','')}: {c.get('keyword_count',0)} kws, top={c.get('top_keyword','')}"
            for c in (clusters[:30])
        )

        prompt = STRATEGY_2B_USER.format(
            universe=universe,
            pillars=", ".join(str(p) for p in pillars),
            total_kw=len(keywords),
            intent_breakdown=intent_breakdown or "  (no intent data)",
            pillar_breakdown=pillar_breakdown or "  (no pillar data)",
            top_50_kws=top_50 or "  (no keywords found)",
            cluster_count=len(clusters),
            cluster_summary=cluster_summary or "  (no clusters)",
        )
        # Enrich with additional business context
        _locs = ", ".join(profile.get("target_locations", []))
        _cultural = ", ".join(profile.get("cultural_context", []))
        _langs = ", ".join(profile.get("languages", []))
        _usp = profile.get("usp", "")
        _reviews = (profile.get("customer_reviews", "") or "")[:200]
        if any([_locs, _cultural, _langs, _usp, _reviews]):
            prompt += "\n\nADDITIONAL BUSINESS CONTEXT:"
            if _usp:
                prompt += f"\nUSP: {_usp}"
            if _locs:
                prompt += f"\nTarget locations: {_locs}"
            if _langs:
                prompt += f"\nLanguages: {_langs}"
            if _cultural:
                prompt += f"\nCultural context: {_cultural}"
            if _reviews:
                prompt += f"\nCustomer voice: {_reviews}"
            prompt += "\nUse this context to identify location-specific, cultural, and customer language keyword opportunities."

        # Inject intelligence questions if available (from Intelligence tab pipeline)
        if intelligence_questions:
            q_lines = []
            for q in intelligence_questions[:30]:
                q_text = q.get("question", "")
                q_type = q.get("content_type", "") or q.get("intent", "")
                q_score = q.get("final_score")
                score_str = f", score={q_score:.1f}" if q_score is not None else ""
                q_lines.append(f"  - {q_text} (type={q_type}{score_str})")
            prompt += f"\n\nINTELLIGENCE QUESTIONS ({len(intelligence_questions)} scored questions from research pipeline):"
            prompt += "\n" + "\n".join(q_lines)
            prompt += "\nUse these questions to identify content angles, audience needs, and topic gaps for the strategy."

        resp = kw2_ai_call(
            prompt, STRATEGY_V2_SYSTEM, provider=provider, temperature=0.3,
            session_id=session_id, project_id=project_id, task="strategy_2b",
        )
        result = kw2_extract_json(resp)
        return result if isinstance(result, dict) else {}

    # ── Module 2C — Strategy Builder ─────────────────────────────────────

    def _run_module_2c(
        self, module_2a, module_2b, content_params,
        provider, session_id, project_id,
    ) -> dict:
        blogs_per_week = content_params.get("blogs_per_week") or 3
        duration_weeks = content_params.get("duration_weeks") or 12
        content_mix = content_params.get("content_mix") or {}
        publishing_cadence = content_params.get("publishing_cadence") or []
        extra_prompt = (content_params.get("extra_prompt") or "").strip()

        total_articles = blogs_per_week * duration_weeks
        mix_str = (
            f"{content_mix.get('informational', 60)}% informational, "
            f"{content_mix.get('transactional', 20)}% transactional, "
            f"{content_mix.get('commercial', 20)}% commercial"
        ) if content_mix else "60% informational, 20% transactional, 20% commercial"
        cadence_str = ", ".join(publishing_cadence) if publishing_cadence else "Mon/Wed/Fri"

        # Per-pillar article allocation (from Parameters tab)
        pillar_velocity = content_params.get("pillar_velocity") or {}
        pillar_vel_str = ""
        if pillar_velocity:
            pv_lines = [f"  - {pillar}: {count} articles" for pillar, count in pillar_velocity.items() if count]
            if pv_lines:
                pillar_vel_str = "\nPer-pillar article allocation:\n" + "\n".join(pv_lines)

        extra_guidance = ""
        if extra_prompt:
            extra_guidance += f"\nAdditional guidance: {extra_prompt}"
        if pillar_vel_str:
            extra_guidance += pillar_vel_str

        prompt = STRATEGY_2C_USER.format(
            module_2a_json=_truncate(_safe_json(module_2a), 2500),
            module_2b_json=_truncate(_safe_json(module_2b), 2500),
            blogs_per_week=blogs_per_week,
            duration_weeks=duration_weeks,
            total_articles=total_articles,
            content_mix=mix_str,
            cadence_str=cadence_str,
            extra_guidance=extra_guidance,
        )

        resp = kw2_ai_call(
            prompt, STRATEGY_V2_SYSTEM, provider=provider, temperature=0.4,
            session_id=session_id, project_id=project_id, task="strategy_2c",
        )
        result = kw2_extract_json(resp)
        if not isinstance(result, dict):
            result = {
                "strategy_summary": {"headline": resp[:300], "biggest_opportunity": "", "why_we_win": ""},
                "priority_pillars": [],
                "quick_wins": [],
                "weekly_plan": [],
                "link_building_plan": "",
                "competitive_gaps": [],
                "content_gaps": [],
                "timeline": {},
            }

        # Ensure required keys exist
        for key, default in [
            ("strategy_summary", {}),
            ("priority_pillars", []),
            ("quick_wins", []),
            ("weekly_plan", []),
            ("link_building_plan", ""),
            ("competitive_gaps", []),
            ("content_gaps", []),
            ("timeline", {}),
        ]:
            if key not in result:
                result[key] = default

        return result

    # ── Module 2D — Action Mapping ────────────────────────────────────────

    def _run_module_2d(
        self, strategy, keywords, clusters,
        provider, session_id, project_id,
    ) -> dict:
        # Sample of keyword scores for context
        sorted_kws = sorted(keywords, key=lambda k: k.get("final_score", 0), reverse=True)
        kw_sample = "\n".join(
            f"  - {k['keyword']}: score={k.get('final_score',0):.1f}, pillar={k.get('pillar','')}"
            for k in sorted_kws[:30]
        )
        cluster_list = "\n".join(
            f"  - {c.get('cluster_name','')}" for c in clusters[:20]
        )

        prompt = STRATEGY_2D_USER.format(
            module_2c_json=_truncate(_safe_json({
                "strategy_summary": strategy.get("strategy_summary", {}),
                "priority_pillars": strategy.get("priority_pillars", [])[:5],
                "quick_wins": strategy.get("quick_wins", [])[:10],
            }), 2000),
            kw_score_sample=kw_sample or "  (none)",
            cluster_list=cluster_list or "  (none)",
        )

        resp = kw2_ai_call(
            prompt, STRATEGY_V2_SYSTEM, provider=provider, temperature=0.2,
            session_id=session_id, project_id=project_id, task="strategy_2d",
        )
        result = kw2_extract_json(resp)
        return result if isinstance(result, dict) else {}

    # ── Version persistence ───────────────────────────────────────────────

    def _save_version(
        self, session_id, project_id, strategy,
        module_2a, module_2b, module_2d,
        ai_provider, content_params,
    ) -> str:
        conn = db.get_conn()
        try:
            # Deactivate all previous versions
            conn.execute(
                "UPDATE kw2_strategy_versions SET is_active=0 WHERE session_id=?",
                (session_id,),
            )
            # Get next version number
            row = conn.execute(
                "SELECT COALESCE(MAX(version_number),0) FROM kw2_strategy_versions WHERE session_id=?",
                (session_id,),
            ).fetchone()
            version_num = (row[0] or 0) + 1

            vid = _uid("sv_")
            conn.execute(
                """INSERT INTO kw2_strategy_versions
                   (id, session_id, project_id, version_number, strategy_json,
                    module_2a_json, module_2b_json, module_2d_json,
                    ai_provider, params_snapshot, is_active, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,1,?)""",
                (vid, session_id, project_id, version_num,
                 _safe_json(strategy),
                 _safe_json(module_2a),
                 _safe_json(module_2b),
                 _safe_json(module_2d),
                 ai_provider,
                 _safe_json(content_params),
                 _now()),
            )
            conn.commit()
        finally:
            conn.close()
        return vid

    # ── Version management ────────────────────────────────────────────────

    def list_versions(self, session_id: str) -> list[dict]:
        """Return all strategy versions for a session, newest first."""
        conn = db.get_conn()
        try:
            rows = conn.execute(
                """SELECT id, version_number, ai_provider, is_active, created_at, notes
                   FROM kw2_strategy_versions
                   WHERE session_id=?
                   ORDER BY version_number DESC""",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def activate_version(self, session_id: str, version_id: str) -> bool:
        """Set a specific version as active, deactivate others."""
        conn = db.get_conn()
        try:
            conn.execute(
                "UPDATE kw2_strategy_versions SET is_active=0 WHERE session_id=?",
                (session_id,),
            )
            conn.execute(
                "UPDATE kw2_strategy_versions SET is_active=1 WHERE id=? AND session_id=?",
                (version_id, session_id),
            )
            # Sync active strategy back to session
            row = conn.execute(
                "SELECT strategy_json FROM kw2_strategy_versions WHERE id=?",
                (version_id,),
            ).fetchone()
            conn.commit()
            if row:
                db.update_session(session_id, strategy_json=row["strategy_json"])
            return True
        finally:
            conn.close()

    def save_edit(
        self, session_id: str, version_id: str, field_path: str,
        old_value, new_value, edited_by: str = "user",
    ) -> str:
        """Record a user edit to a strategy field."""
        conn = db.get_conn()
        try:
            eid = _uid("se_")
            conn.execute(
                """INSERT INTO kw2_strategy_edits
                   (id, strategy_version_id, session_id, field_path, old_value, new_value, edited_by, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (eid, version_id, session_id, field_path,
                 _safe_json(old_value), _safe_json(new_value), edited_by, _now()),
            )
            conn.commit()
        finally:
            conn.close()
        return eid

    def get_version(self, version_id: str) -> dict | None:
        """Get a specific version with all module outputs."""
        conn = db.get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM kw2_strategy_versions WHERE id=?", (version_id,)
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            for field in ("strategy_json", "module_2a_json", "module_2b_json",
                          "module_2d_json", "params_snapshot"):
                raw = d.get(field, "")
                try:
                    d[field] = json.loads(raw) if raw else {}
                except (json.JSONDecodeError, TypeError):
                    d[field] = {}
            return d
        finally:
            conn.close()

    # ── Read strategy ─────────────────────────────────────────────────────

    def get_strategy(self, session_id: str) -> dict | None:
        """
        Load strategy: check active version first, fall back to session.strategy_json.
        """
        conn = db.get_conn()
        try:
            row = conn.execute(
                """SELECT strategy_json FROM kw2_strategy_versions
                   WHERE session_id=? AND is_active=1
                   ORDER BY version_number DESC LIMIT 1""",
                (session_id,),
            ).fetchone()
        finally:
            conn.close()

        if row and row["strategy_json"]:
            try:
                return json.loads(row["strategy_json"])
            except (json.JSONDecodeError, TypeError):
                pass

        # Fallback to legacy session.strategy_json
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

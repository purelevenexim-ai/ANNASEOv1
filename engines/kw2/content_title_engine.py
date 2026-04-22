"""
kw2 Content Title Engine — Phase 9.

Converts selected questions into SEO-optimised content titles.
Each title includes: title, slug, primary keyword, meta title, content type, word count target.

Output saved to kw2_content_titles table.
"""
import json
import logging
import re
import uuid
from datetime import datetime, timezone

from engines.kw2.ai_caller import kw2_ai_call, kw2_extract_json
from engines.kw2 import db

log = logging.getLogger("kw2.content_title_engine")

TITLE_SYSTEM = (
    "You are an expert SEO copywriter and content strategist. "
    "Output ONLY valid JSON with no markdown fences."
)

TITLE_PROMPT = """BUSINESS: {business_context}

Convert these questions into SEO-optimised content titles.

QUESTIONS (batch of {batch_size}):
{questions_json}

For each question, provide:
- title: High-CTR SEO content title (specific, not generic, 50-70 chars)
- slug: URL-friendly version (lowercase, hyphens, no stop words)
- primary_keyword: The main target keyword
- meta_title: SERP meta title variant (40-60 chars), include keyword naturally
- content_type: blog|guide|comparison|landing-page|faq|listicle
- word_count_target: Recommended article length (500/800/1200/1500/2000/2500)

Rules:
- Title must match search intent exactly
- No clickbait — clear, honest, specific
- Primary keyword must appear in title naturally
- Slug must be short (3-6 words max)
- Use business-specific terminology and location names where relevant
- Titles for geo-targeted questions should include the location naturally

Return ONLY this JSON:
{{
  "titles": [
    {{
      "question_id": "",
      "title": "",
      "slug": "",
      "primary_keyword": "",
      "meta_title": "",
      "content_type": "",
      "word_count_target": 1500
    }}
  ]
}}"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid(prefix: str = "") -> str:
    short = uuid.uuid4().hex[:12]
    return f"{prefix}{short}" if prefix else short


def _slugify(text: str) -> str:
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    return slug[:80]


class ContentTitleEngine:
    """Phase 9: Generate SEO titles from selected questions."""

    def generate(
        self,
        project_id: str,
        session_id: str,
        ai_provider: str = "auto",
        batch_size: int = 20,
        limit: int = 200,
    ) -> dict:
        """
        Generate titles for selected questions that don't yet have titles.
        Processes in batches to control token cost.
        """
        profile = db.load_business_profile(project_id)
        universe = (profile.get("universe", "") if profile else "") or "Business"

        # Build business context for title generation — richer with BI
        biz_ctx_parts = [universe]
        if profile:
            if profile.get("business_type"):
                biz_ctx_parts[0] = f"{universe} ({profile['business_type']})"
            _mi = profile.get("manual_input") or {}
            _locs = profile.get("target_locations") or _mi.get("target_locations") or []
            if _locs:
                biz_ctx_parts.append(f"Target locations: {', '.join(_locs[:5])}")
            _aud = profile.get("audience") or []
            if _aud:
                biz_ctx_parts.append(f"Audience: {', '.join(_aud[:3])}")
            _usp = profile.get("usp") or _mi.get("usp") or ""
            if _usp:
                biz_ctx_parts.append(f"USP: {_usp[:100]}")

        # Enrich with BI strategy + README
        try:
            biz_intel = db.get_biz_intel(session_id) or {}
            if biz_intel.get("seo_strategy"):
                import json as _json
                strategy = _json.loads(biz_intel["seo_strategy"])
                prio_kws = strategy.get("priority_keywords", [])[:8]
                if prio_kws:
                    prio_str = ", ".join(k if isinstance(k, str) else k.get("keyword", "") for k in prio_kws)
                    biz_ctx_parts.append(f"Priority keywords: {prio_str}")
            session = db.get_session(session_id) or {}
            readme = session.get("business_readme", "")
            if readme:
                biz_ctx_parts.append(f"Business overview: {readme[:400]}")
        except Exception:
            pass
        business_context = " | ".join(biz_ctx_parts)

        # Load selected questions without titles
        conn = db.get_conn()
        try:
            rows = conn.execute(
                """SELECT sq.question_id, sq.cluster_id,
                          iq.question, iq.intent, iq.funnel_stage,
                          iq.audience_segment, iq.content_type as enriched_type,
                          iq.module_code,
                          cc.pillar, cc.cluster_name
                   FROM kw2_selected_questions sq
                   JOIN kw2_intelligence_questions iq ON sq.question_id = iq.id
                   LEFT JOIN kw2_content_clusters cc ON sq.cluster_id = cc.id
                   LEFT JOIN kw2_content_titles ct ON ct.question_id = sq.question_id 
                             AND ct.session_id = sq.session_id
                   WHERE sq.session_id=? AND ct.id IS NULL
                   ORDER BY sq.selection_rank ASC
                   LIMIT ?""",
                (session_id, limit),
            ).fetchall()
        finally:
            conn.close()

        to_generate = [dict(r) for r in rows]
        if not to_generate:
            return {"generated": 0, "message": "No selected questions need titles"}

        total_generated = 0
        for i in range(0, len(to_generate), batch_size):
            batch = to_generate[i : i + batch_size]
            count = self._generate_batch(
                batch, business_context, ai_provider, session_id, project_id,
            )
            total_generated += count

        log.info("[ContentTitleEngine] Generated %d titles", total_generated)
        return {"generated": total_generated}

    def list_titles(
        self,
        session_id: str,
        pillar: str | None = None,
        content_type: str | None = None,
        status: str | None = None,
        intent: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        conn = db.get_conn()
        try:
            conds = ["session_id=?"]
            params: list = [session_id]
            if pillar:
                conds.append("pillar=?")
                params.append(pillar)
            if content_type:
                conds.append("content_type=?")
                params.append(content_type)
            if status:
                conds.append("status=?")
                params.append(status)
            if intent:
                conds.append("intent=?")
                params.append(intent)
            params.append(limit)
            rows = conn.execute(
                f"SELECT * FROM kw2_content_titles WHERE {' AND '.join(conds)} "
                f"ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def update_title(self, title_id: str, session_id: str, **kwargs) -> bool:
        """Edit a content title."""
        allowed = {"title", "slug", "primary_keyword", "meta_title",
                   "content_type", "word_count_target", "scheduled_date",
                   "status", "pillar", "cluster_name"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        conn = db.get_conn()
        try:
            set_clause = ", ".join(f"{k}=?" for k in updates)
            vals = list(updates.values()) + [title_id, session_id]
            conn.execute(
                f"UPDATE kw2_content_titles SET {set_clause} WHERE id=? AND session_id=?",
                vals,
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def get_stats(self, session_id: str) -> dict:
        conn = db.get_conn()
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM kw2_content_titles WHERE session_id=?",
                (session_id,),
            ).fetchone()[0]
            by_status = conn.execute(
                """SELECT status, COUNT(*) as cnt FROM kw2_content_titles
                   WHERE session_id=? GROUP BY status""",
                (session_id,),
            ).fetchall()
            by_pillar = conn.execute(
                """SELECT pillar, COUNT(*) as cnt FROM kw2_content_titles
                   WHERE session_id=? GROUP BY pillar""",
                (session_id,),
            ).fetchall()
            return {
                "total": total,
                "by_status": {r["status"]: r["cnt"] for r in by_status},
                "by_pillar": {r["pillar"]: r["cnt"] for r in by_pillar},
            }
        finally:
            conn.close()

    # ── Internal ────────────────────────────────────────────────────────────

    def _generate_batch(
        self,
        batch: list[dict],
        business_context: str,
        provider: str,
        session_id: str,
        project_id: str,
    ) -> int:
        questions_json = json.dumps(
            [{"id": q["question_id"], "question": q["question"]} for q in batch],
            ensure_ascii=False,
        )
        prompt = TITLE_PROMPT.format(
            business_context=business_context,
            batch_size=len(batch),
            questions_json=questions_json[:4000],
        )
        resp = kw2_ai_call(
            prompt, TITLE_SYSTEM, provider=provider, temperature=0.4,
            session_id=session_id, project_id=project_id, task="title_gen",
        )
        result = kw2_extract_json(resp)
        if not isinstance(result, dict):
            return 0

        titles = result.get("titles", [])
        if not isinstance(titles, list):
            return 0

        # Build question_id → metadata lookup
        q_meta: dict[str, dict] = {q["question_id"]: q for q in batch}

        to_insert = []
        now = _now()
        for item in titles:
            if not isinstance(item, dict):
                continue
            qid = item.get("question_id", "")
            meta = q_meta.get(qid, {})
            title_text = str(item.get("title", ""))[:500]
            if not title_text:
                continue
            slug = item.get("slug") or _slugify(title_text)
            to_insert.append((
                _uid("ct_"),
                session_id,
                project_id,
                qid,
                "",  # selected_question_id (set separately if needed)
                title_text,
                str(slug)[:200],
                str(item.get("primary_keyword", ""))[:200],
                str(item.get("meta_title", ""))[:200],
                str(item.get("content_type", "blog"))[:50],
                int(item.get("word_count_target", 1500) or 1500),
                str(meta.get("pillar", ""))[:100],
                str(meta.get("cluster_name", ""))[:200],
                str(meta.get("intent", ""))[:50],
                str(meta.get("funnel_stage", "TOFU"))[:20],
                "titled",
                now,
            ))

        if not to_insert:
            return 0

        conn = db.get_conn()
        try:
            conn.executemany(
                """INSERT OR IGNORE INTO kw2_content_titles
                   (id, session_id, project_id, question_id, selected_question_id,
                    title, slug, primary_keyword, meta_title, content_type,
                    word_count_target, pillar, cluster_name, intent, funnel_stage,
                    status, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                to_insert,
            )
            conn.commit()
        finally:
            conn.close()
        return len(to_insert)

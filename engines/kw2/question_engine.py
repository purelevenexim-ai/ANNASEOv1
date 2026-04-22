"""
kw2 Question Intelligence Engine — Phase 3.

Runs 7 intelligence modules (Q1–Q7) to generate structured questions
about the business, audience, intent, journey, products, content, and
competitive landscape. Questions are saved to kw2_intelligence_questions.

Enrichment (Phase 5) adds intent, funnel stage, geo relevance, etc.
"""
import json
import logging
import uuid
from datetime import datetime, timezone

from engines.kw2.prompts import (
    QUESTION_MODULE_SYSTEM,
    QUESTION_MODULE_USER,
    ENRICHMENT_SYSTEM,
    ENRICHMENT_USER,
)
from engines.kw2.ai_caller import kw2_ai_call, kw2_extract_json
from engines.kw2 import db

log = logging.getLogger("kw2.question_engine")


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


def _trunc(s: str, n: int) -> str:
    return (s or "")[:n]


# ── Question quality validation ───────────────────────────────────────────────

# Words that indicate a real search query
_QUERY_STARTERS = (
    "what", "how", "which", "where", "why", "best", "top", "can", "do",
    "is", "are", "buy", "who", "when", "price", "cost", "cheap",
)

# Patterns that indicate a business strategy statement, not a search query
_STRATEGY_PATTERNS = (
    "optimizing", "leveraging", "developing", "improving", "enhancing",
    "understanding", "maintaining", "addressing", "ensuring", "providing",
    "implementing", "establishing", "complying with", "investing in",
    "creating new and", "emphasizing key", "highlighting environmental",
)

# Minimum meaningful word count for a question
_MIN_WORDS = 4


def _is_valid_question(text: str) -> bool:
    """
    Return True only if `text` is a genuine user search query.
    Rejects business strategy statements and internal insights.
    """
    if not text:
        return False
    t = text.lower().strip()
    # Must be long enough
    if len(t.split()) < _MIN_WORDS:
        return False
    # Must start with a search-query word
    first = t.split()[0]
    if first not in _QUERY_STARTERS:
        return False
    # Reject known strategy statement patterns
    for pat in _STRATEGY_PATTERNS:
        if t.startswith(pat):
            return False
    return True


# ── Module definitions ────────────────────────────────────────────────────────

_MODULES = {
    "Q1": {
        "role": "product and origin search specialist",
        "focus": (
            "real Google search queries about this product's origin, quality, certifications — "
            "queries people type when researching, evaluating, or purchasing this product. "
            "Include geo-specific variants (e.g. 'best cardamom from Kerala', 'organic spices India certified')"
        ),
        "dimensions": (
            "product origin (farm/region), certifications (organic/fairtrade/FSSAI), "
            "quality grades, sourcing transparency, brand trust signals, "
            "geo combinations (product + region)"
        ),
        "max_questions": 15,
        "required_categories": {
            "buying": 4,        # e.g. "where to buy X from Y farm"
            "comparison": 3,    # e.g. "X from Kerala vs X from other regions"
            "informational": 4, # e.g. "what makes Kerala cardamom different"
            "regional": 4,      # e.g. "best cardamom in India by region"
        },
    },
    "Q2": {
        "role": "audience search behavior specialist",
        "focus": (
            "real search queries from each distinct buyer persona — what they actually type into Google. "
            "Home cooks, professional chefs, restaurant owners, health enthusiasts, exporters, bulk buyers. "
            "Each audience has different vocabulary: restaurants search 'wholesale', home cooks search 'how to use'"
        ),
        "dimensions": (
            "home cooks (recipe, how-to, usage), restaurant owners (wholesale, bulk, supplier), "
            "health buyers (organic, benefits, ayurvedic), exporters/B2B (FOB, trade, bulk kg), "
            "gift buyers (premium, gift pack, festival)"
        ),
        "max_questions": 15,
        "required_categories": {
            "buying": 5,
            "usage": 4,
            "comparison": 3,
            "regional": 3,
        },
    },
    "Q3": {
        "role": "commercial and transactional search query specialist",
        "focus": (
            "high-buying-intent search queries — price, buy, order, wholesale, supplier, delivery. "
            "These drive the most revenue. Include price queries, bulk queries, platform queries "
            "(Amazon/Flipkart), location-specific buying queries, and B2B procurement queries"
        ),
        "dimensions": (
            "buy/order/shop online, price/cost/rate/MRP, bulk/wholesale/kg-rate, "
            "supplier/manufacturer/distributor, online platforms (Amazon/Flipkart/website), "
            "delivery/shipping to major cities, geo-specific buying (buy X in Delhi/Mumbai)"
        ),
        "max_questions": 20,
        "required_categories": {
            "buying": 10,       # core: buy, order, shop
            "comparison": 5,    # price comparison, vs competitors
            "regional": 5,      # buy in specific cities
        },
    },
    "Q4": {
        "role": "customer journey search query specialist",
        "focus": (
            "search queries at each stage: awareness (what is X), consideration (best X for Y, X vs Y), "
            "decision (buy X, price of X), post-purchase (how to store X, how to use X). "
            "Map the full funnel from 'what is cardamom' to 'buy cardamom online India'"
        ),
        "dimensions": (
            "awareness (what is, why use), consideration (best X for, X vs Y, reviews), "
            "decision (buy, order online, price), post-purchase (store, use, recipes), "
            "retention (refill, reorder, subscribe)"
        ),
        "max_questions": 15,
        "required_categories": {
            "informational": 4,  # TOFU
            "comparison": 4,     # MOFU
            "buying": 5,         # BOFU
            "usage": 2,          # post-purchase
        },
    },
    "Q5": {
        "role": "product usage and how-to search query specialist",
        "focus": (
            "how-to queries, recipe queries, and beginner usage questions. These become high-traffic blog posts. "
            "Include cooking usage (biriyani, curry, tea), health usage (digestion, immunity), "
            "storage tips, beginner mistakes, substitution queries, and regional usage variations"
        ),
        "dimensions": (
            "cooking applications (biriyani, curry, chai, baking), health/wellness use, "
            "storage and freshness, beginner mistakes, regional cooking styles, "
            "product substitutions, quantities (how much X for Y)"
        ),
        "max_questions": 15,
        "required_categories": {
            "usage": 7,          # how-to, recipes
            "regional": 4,       # Kerala style, North India style
            "informational": 4,  # what is, why, when
        },
    },
    "Q6": {
        "role": "long-tail and regional search opportunity specialist",
        "focus": (
            "underserved long-tail queries, regional city/state variations, seasonal angles, "
            "and comparison content. Focus on queries with lower competition but high specificity. "
            "Include: product + city, product + occasion (Diwali, wedding), product + dish + region"
        ),
        "dimensions": (
            "state/city geo variants (X in Kerala/TN/Mumbai/Delhi), "
            "seasonal/festival (Onam, Diwali, Eid), dish + region combinations, "
            "niche audience (vegan, keto, diabetic), product grade variations, "
            "X vs Y comparisons"
        ),
        "max_questions": 20,
        "required_categories": {
            "regional": 8,       # state/city specific
            "comparison": 5,     # X vs Y
            "informational": 4,  # seasonal, occasion
            "buying": 3,         # geo-specific buying
        },
    },
    "Q7": {
        "role": "competitive gap and quick-win search query specialist",
        "focus": (
            "queries where competitors are weak or missing, niche product queries, "
            "B2B queries competitors ignore, and longtail queries with strong commercial intent. "
            "These are ranking opportunities — high value, lower competition"
        ),
        "dimensions": (
            "competitor keyword gaps (topics they don't cover), B2B/wholesale niches, "
            "specific product grades/varieties (GradeA, 8mm, bold), "
            "uncontested regions (tier-2 cities), niche use cases, "
            "export/international queries"
        ),
        "max_questions": 20,
        "required_categories": {
            "buying": 6,         # high-intent gaps
            "regional": 5,       # uncontested geo
            "comparison": 5,     # competitive comparisons
            "informational": 4,  # content competitors miss
        },
    },
}


class QuestionEngine:
    """Phase 3: Generate intelligence questions across 7 dimensions."""

    def run(
        self,
        project_id: str,
        session_id: str,
        ai_provider: str = "auto",
        modules: list[str] | None = None,
    ) -> dict:
        """
        Run selected question modules (default: all Q1–Q7).
        Returns summary with question count per module.
        """
        modules_to_run = modules or list(_MODULES.keys())

        profile = db.load_business_profile(project_id)
        if not profile:
            raise ValueError("No business profile. Run Phase 1 first.")

        biz_intel = db.get_biz_intel(session_id) or {}
        biz_pages = db.get_biz_pages(session_id) or []
        biz_competitors = db.get_biz_competitors(session_id) or []
        keywords = db.load_validated_keywords(session_id)

        # Build shared business context string
        business_context = self._build_business_context(
            profile, biz_intel, keywords,
        )

        results: dict[str, int] = {}
        for module_code in modules_to_run:
            if module_code not in _MODULES:
                log.warning("Unknown module %s — skipping", module_code)
                continue
            count = self._run_module(
                module_code, profile, biz_intel, biz_pages,
                biz_competitors, keywords, business_context,
                ai_provider, session_id, project_id,
            )
            results[module_code] = count
            log.info("[QuestionEngine] %s generated %d questions", module_code, count)

        # ── Seed questions from BI Strategy recommended_pages ────────────────
        # These are AI-curated page briefs that should feed directly into content creation.
        try:
            seo_strat_raw = biz_intel.get("seo_strategy", "")
            if seo_strat_raw:
                seo_strat = json.loads(seo_strat_raw) if isinstance(seo_strat_raw, str) else seo_strat_raw
                rec_pages = seo_strat.get("recommended_pages", [])
                strategy_questions = []
                for pg in rec_pages[:8]:
                    if not isinstance(pg, dict):
                        continue
                    topic = pg.get("topic", "").strip()
                    target_kw = pg.get("target_keyword", "").strip()
                    content_angle = pg.get("content_angle", "").strip()
                    page_type = pg.get("page_type", "blog")
                    funnel = pg.get("funnel", "MOFU")
                    if topic and target_kw:
                        # Format as a valid search query (must start with a _QUERY_STARTERS word)
                        _first = target_kw.lower().split()[0] if target_kw else ""
                        _starters = ("what", "how", "which", "where", "why", "best", "top",
                                     "can", "do", "is", "are", "buy", "who", "when", "price", "cost", "cheap")
                        if _first in _starters:
                            q_text = target_kw
                        elif page_type in ("landing", "product_page"):
                            q_text = f"buy {target_kw}" if len(target_kw.split()) >= 2 else f"best {target_kw} online"
                        else:
                            q_text = f"best {target_kw}"
                        strategy_questions.append({
                            "question": q_text,
                            "category": "buying" if "BOFU" in funnel else "informational",
                            "why_it_matters": content_angle or f"High-priority {page_type} page from BI strategy",
                            "data_source": "biz_intel",
                            "priority": "high" if pg.get("estimated_impact") == "high" else "medium",
                        })
                if strategy_questions:
                    self._save_questions(strategy_questions, "Q_BI", session_id, project_id)
                    results["Q_BI_strategy"] = len(strategy_questions)
                    log.info("[QuestionEngine] Seeded %d questions from BI recommended_pages", len(strategy_questions))
        except Exception as _ex:
            log.warning("[QuestionEngine] BI strategy seed failed (non-fatal): %s", _ex)

        total = sum(results.values())
        return {"modules_run": modules_to_run, "counts": results, "total": total}

    def run_enrichment(
        self,
        project_id: str,
        session_id: str,
        ai_provider: str = "auto",
        batch_size: int = 50,
    ) -> dict:
        """
        Phase 5: Enrich all unenriched questions with intent, funnel, geo, etc.
        Processes in batches to control token cost.
        """
        profile = db.load_business_profile(project_id)
        # Build rich context for enrichment — not just universe name
        if profile:
            mi = profile.get("manual_input") if isinstance(profile.get("manual_input"), dict) else {}
            universe = profile.get("universe", "") or "Business"
            btype = profile.get("business_type", "")
            pillars = ", ".join(str(p) for p in profile.get("pillars", [])[:8])
            target_locs = profile.get("target_locations") or mi.get("target_locations", [])
            cultural = profile.get("cultural_context") or mi.get("cultural_context", [])
            geo = profile.get("geo_scope", "")
            parts = [f"{universe} ({btype})" if btype else universe]
            if pillars:
                parts.append(f"Pillars: {pillars}")
            if target_locs:
                parts.append(f"Target locations: {', '.join(str(l) for l in target_locs[:6])}")
            if geo:
                parts.append(f"Geo: {geo}")
            if cultural:
                parts.append(f"Cultural context: {', '.join(str(c) for c in cultural[:4])}")
            business_context = " | ".join(parts)
        else:
            business_context = "Business"

        conn = db.get_conn()
        try:
            rows = conn.execute(
                """SELECT id, question FROM kw2_intelligence_questions
                   WHERE session_id=? AND (intent='' OR intent IS NULL)
                   AND is_duplicate=0""",
                (session_id,),
            ).fetchall()
        finally:
            conn.close()

        pending = [dict(r) for r in rows]
        if not pending:
            return {"enriched": 0}

        enriched_total = 0
        for i in range(0, len(pending), batch_size):
            batch = pending[i : i + batch_size]
            enriched_total += self._enrich_batch(
                batch, business_context, ai_provider, session_id, project_id,
            )

        return {"enriched": enriched_total}

    # ── Module runners ────────────────────────────────────────────────────────

    def _run_module(
        self,
        module_code: str,
        profile: dict,
        biz_intel: dict,
        biz_pages: list,
        biz_competitors: list,
        keywords: list,
        business_context: str,
        provider: str,
        session_id: str,
        project_id: str,
    ) -> int:
        module_def = _MODULES[module_code]
        module_data = self._build_module_data(
            module_code, profile, biz_intel, biz_pages, biz_competitors, keywords,
        )

        system_prompt = QUESTION_MODULE_SYSTEM.format(
            module_role=module_def["role"],
        )
        user_prompt = QUESTION_MODULE_USER.format(
            business_context=_trunc(business_context, 1500),
            module_specific_data=_trunc(module_data, 2000),
            module_focus=module_def["focus"],
            dimension_list=module_def["dimensions"],
            max_questions=module_def["max_questions"],
        )

        resp = kw2_ai_call(
            user_prompt, system_prompt,
            provider=provider, temperature=0.5,
            session_id=session_id, project_id=project_id,
            task=f"question_{module_code.lower()}",
        )
        result = kw2_extract_json(resp)
        if not isinstance(result, dict):
            return 0

        questions = result.get("questions", [])
        if not isinstance(questions, list):
            return 0

        self._save_questions(questions, module_code, session_id, project_id)
        return len(questions)

    def _build_module_data(
        self,
        module_code: str,
        profile: dict,
        biz_intel: dict,
        biz_pages: list,
        biz_competitors: list,
        keywords: list,
    ) -> str:
        if module_code == "Q1":
            return (
                f"Universe: {profile.get('universe','')}\n"
                f"Business type: {profile.get('business_type','')}\n"
                f"Pillars: {', '.join(str(p) for p in profile.get('pillars', []))}\n"
                f"USPs: {_safe_json(biz_intel.get('usps', [])[:5])}\n"
                f"Pricing: {biz_intel.get('pricing_model','')}\n"
                f"Knowledge summary: {_trunc(biz_intel.get('knowledge_summary',''), 600)}"
            )
        elif module_code == "Q2":
            segs = biz_intel.get("audience_segments", [])
            return (
                f"Audience: {profile.get('audience', [])}\n"
                f"Segments: {_safe_json(segs[:8])}\n"
                f"Intent distribution: {self._intent_distribution(keywords)}"
            )
        elif module_code == "Q3":
            sorted_kws = sorted(keywords, key=lambda k: k.get("final_score", 0), reverse=True)
            kw_lines = "\n".join(
                f"  {k['keyword']} | intent={k.get('intent','')} | score={k.get('final_score',0):.1f} | buyer={k.get('buyer_readiness',0):.1f}"
                for k in sorted_kws[:60]
            )
            return f"KEYWORDS ({len(keywords)} total):\n{kw_lines}"
        elif module_code == "Q4":
            sorted_kws = sorted(keywords, key=lambda k: k.get("buyer_readiness", 0), reverse=True)
            kw_lines = "\n".join(
                f"  {k['keyword']} | buyer_readiness={k.get('buyer_readiness',0):.1f} | intent={k.get('intent','')}"
                for k in sorted_kws[:40]
            )
            return f"KEYWORDS BY BUYER READINESS:\n{kw_lines}"
        elif module_code == "Q5":
            page_lines = "\n".join(
                f"  [{p.get('page_type','')}] {p.get('primary_topic','')} ({p.get('search_intent','')})"
                for p in biz_pages[:20]
                if p.get("primary_topic")
            )
            return (
                f"Products/Services: {_trunc(str(biz_intel.get('products_services','')), 400)}\n"
                f"WEBSITE PAGES:\n{page_lines or '(none crawled)'}"
            )
        elif module_code == "Q6":
            pillar_kw_counts = {}
            for k in keywords:
                p = k.get("pillar", "unknown")
                pillar_kw_counts[p] = pillar_kw_counts.get(p, 0) + 1
            pillar_str = "\n".join(f"  {p}: {c} keywords" for p, c in pillar_kw_counts.items())

            # Parse BI strategy to get priority keywords + recommended pages
            strategy_extra = ""
            try:
                seo_strat_raw = biz_intel.get("seo_strategy", "")
                if seo_strat_raw:
                    seo_strat = json.loads(seo_strat_raw) if isinstance(seo_strat_raw, str) else seo_strat_raw
                    prio_kws = seo_strat.get("priority_keywords", [])[:8]
                    if prio_kws:
                        prio_lines = []
                        for kw in prio_kws:
                            if isinstance(kw, dict):
                                prio_lines.append(f"  {kw.get('keyword','')} [{kw.get('intent','')}] ({kw.get('priority','')}) — {kw.get('why','')[:80]}")
                            elif isinstance(kw, str):
                                prio_lines.append(f"  {kw}")
                        strategy_extra += f"\nBI PRIORITY KEYWORDS:\n" + "\n".join(prio_lines)
                    rec_pages = seo_strat.get("recommended_pages", [])[:6]
                    if rec_pages:
                        page_lines = []
                        for pg in rec_pages:
                            if isinstance(pg, dict):
                                page_lines.append(
                                    f"  [{pg.get('page_type','')}] {pg.get('topic','')} | keyword: {pg.get('target_keyword','')} | {pg.get('content_angle','')[:80]}"
                                )
                        strategy_extra += f"\nRECOMMENDED PAGES:\n" + "\n".join(page_lines)
                    quick_wins = seo_strat.get("quick_wins", [])[:5]
                    if quick_wins:
                        strategy_extra += f"\nQUICK WIN KEYWORDS: {', '.join(str(q) for q in quick_wins)}"
            except Exception:
                pass

            return (
                f"PILLARS WITH KEYWORD COUNTS:\n{pillar_str}\n"
                f"Intent distribution: {self._intent_distribution(keywords)}\n"
                f"SEO strategy so far: {_trunc(biz_intel.get('seo_strategy',''), 300)}"
                f"{strategy_extra}"
            )
        elif module_code == "Q7":
            comp_lines = []
            for c in biz_competitors[:5]:
                domain = c.get("domain", "")
                missed = c.get("missed_opportunities", [])
                if isinstance(missed, str):
                    try: missed = json.loads(missed)
                    except: missed = []
                weaknesses = c.get("weaknesses", [])
                if isinstance(weaknesses, str):
                    try: weaknesses = json.loads(weaknesses)
                    except: weaknesses = []
                if domain:
                    comp_lines.append(
                        f"  {domain}: missed={', '.join(str(m) for m in missed[:3])}, "
                        f"weak={', '.join(str(w) for w in weaknesses[:3])}"
                    )
            return "COMPETITORS:\n" + "\n".join(comp_lines or ["(no competitor data)"])
        return ""

    def _build_business_context(
        self, profile: dict, biz_intel: dict, keywords: list
    ) -> str:
        pillars = ", ".join(str(p) for p in profile.get("pillars", []))
        universe = profile.get("universe", "")
        btype = profile.get("business_type", "")
        geo = profile.get("geo_scope", "")
        audience = profile.get("audience", [])
        aud_str = ", ".join(str(a) for a in audience[:4]) if isinstance(audience, list) else str(audience)
        website_sum = _trunc(biz_intel.get("website_summary", ""), 400)

        # Restore pass-through fields from manual_input if not top-level
        mi = profile.get("manual_input") if isinstance(profile.get("manual_input"), dict) else {}
        usp = profile.get("usp") or mi.get("usp", "")
        target_locs = profile.get("target_locations") or mi.get("target_locations", [])
        biz_locs = profile.get("business_locations") or mi.get("business_locations", [])
        languages = profile.get("languages") or mi.get("languages", [])
        cultural = profile.get("cultural_context") or mi.get("cultural_context", [])
        reviews = profile.get("customer_reviews") or mi.get("customer_reviews", "")
        products = profile.get("product_catalog", [])

        lines = [
            f"Business: {universe} ({btype})",
            f"Pillars: {pillars}",
            f"Products: {', '.join(str(p) for p in products[:10])}" if products else None,
            f"Audience: {aud_str}",
            f"Geo: {geo}",
            f"Target locations: {', '.join(str(l) for l in target_locs[:8])}" if target_locs else None,
            f"Business locations: {', '.join(str(l) for l in biz_locs[:6])}" if biz_locs else None,
            f"Languages: {', '.join(str(l) for l in languages[:5])}" if languages else None,
            f"Cultural context: {', '.join(str(c) for c in cultural[:5])}" if cultural else None,
            f"USP: {_trunc(usp, 200)}" if usp else None,
            f"Customer voice: {_trunc(reviews, 300)}" if reviews else None,
            f"Total validated keywords: {len(keywords)}",
            f"Website summary: {website_sum}",
        ]
        return "\n".join(l for l in lines if l)

    def _intent_distribution(self, keywords: list) -> str:
        counts: dict[str, int] = {}
        for k in keywords:
            intent = k.get("intent", "unknown") or "unknown"
            counts[intent] = counts.get(intent, 0) + 1
        return " | ".join(f"{i}: {c}" for i, c in sorted(counts.items(), key=lambda x: -x[1]))

    # ── DB operations ─────────────────────────────────────────────────────────

    def _save_questions(
        self, questions: list, module_code: str, session_id: str, project_id: str
    ) -> None:
        to_insert = []
        rejected = 0
        now = _now()
        for q in questions:
            if not isinstance(q, dict) or not q.get("question"):
                continue
            if not _is_valid_question(q["question"]):
                rejected += 1
                log.debug("Rejected strategy-statement: %s", q["question"][:80])
                continue
            to_insert.append((
                _uid("qi_"),
                session_id,
                project_id,
                module_code,
                str(q.get("question", ""))[:2000],
                str(q.get("category", ""))[:200],
                str(q.get("why_it_matters", ""))[:500],
                str(q.get("data_source", "ai_inference"))[:50],
                str(q.get("priority", "medium"))[:20],
                now,
            ))
        if not to_insert:
            _log.info("_save_questions: 0 saved, %d rejected as strategy-statements", rejected)
            return
        log.info("_save_questions: saving %d questions, rejected %d strategy-statements", len(to_insert), rejected)
        conn = db.get_conn()
        try:
            conn.executemany(
                """INSERT INTO kw2_intelligence_questions
                   (id, session_id, project_id, module_code, question,
                    content_type, score_breakdown, data_source, effort, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                to_insert,
            )
            conn.commit()
        finally:
            conn.close()

    def _enrich_batch(
        self, batch: list, business_context: str,
        provider: str, session_id: str, project_id: str,
    ) -> int:
        questions_json = _safe_json([
            {"id": q["id"], "question": q["question"]} for q in batch
        ])
        prompt = ENRICHMENT_USER.format(
            business_context=_trunc(business_context, 800),
            batch_size=len(batch),
            questions_json=questions_json,
        )
        resp = kw2_ai_call(
            prompt, ENRICHMENT_SYSTEM,
            provider=provider, temperature=0.2,
            session_id=session_id, project_id=project_id,
            task="question_enrich",
        )
        result = kw2_extract_json(resp)
        if not isinstance(result, dict):
            return 0

        enriched = result.get("enriched", [])
        if not isinstance(enriched, list):
            return 0

        now = _now()
        count = 0
        conn = db.get_conn()
        try:
            for item in enriched:
                if not isinstance(item, dict) or not item.get("id"):
                    continue
                conn.execute(
                    """UPDATE kw2_intelligence_questions SET
                       intent=?, funnel_stage=?, audience_segment=?,
                       geo_relevance=?, business_relevance=?,
                       content_type=?, effort=?
                       WHERE id=? AND session_id=?""",
                    (
                        str(item.get("intent", ""))[:50],
                        str(item.get("funnel_stage", ""))[:20],
                        str(item.get("audience_segment", ""))[:200],
                        str(item.get("geo_relevance", ""))[:50],
                        float(item.get("business_relevance", 0.0) or 0.0),
                        str(item.get("content_type", ""))[:50],
                        str(item.get("effort", "medium"))[:20],
                        item["id"],
                        session_id,
                    ),
                )
                count += 1
            conn.commit()
        finally:
            conn.close()
        return count

    # ── Query helpers ─────────────────────────────────────────────────────────

    # ── Pillar-specific question generation ──────────────────────────────────

    _PILLAR_SYSTEM = (
        "You are an expert SEO strategist specialising in product-specific search queries. "
        "Output ONLY valid JSON with no markdown fences or explanation text."
    )

    _PILLAR_USER = """BUSINESS CONTEXT:
{business_context}

FOCUS PRODUCT / PILLAR: {pillar}
KEYWORDS IN THIS PILLAR: {pillar_keywords}

TASK: Generate exactly {count} REAL user search queries that people actually type into Google,
specifically about "{pillar}".

Mix of query types:
- Buying (buy, price, where to buy, online, wholesale)
- Informational (what is, benefits, how to use, why)
- Comparison (vs, best, which is better)
- Regional (Kerala, India, Mumbai, from X)
- How-to (recipes, cooking, storage)

CRITICAL RULES — every question MUST:
1. Be a real search query someone types into Google
2. Start with: What, How, Which, Where, Why, Best, Top, Can, Do, Is, Are, Buy, Price
3. Be SPECIFICALLY about {pillar} — not a generic business question
4. Be at least 4 words long
5. Be content-creation-ready (can become a blog title or product page)

Return ONLY this JSON:
{{
  "questions": [
    {{
      "question": "real user search query about {pillar}",
      "category": "buying|informational|comparison|regional|how-to",
      "why_it_matters": "why users search this"
    }}
  ]
}}"""

    def generate_for_pillar(
        self,
        project_id: str,
        session_id: str,
        pillar: str,
        count: int = 5,
        ai_provider: str = "auto",
    ) -> dict:
        """Generate N questions specifically for a single product pillar.
        Saves with module_code='PE' and expansion_dimension_name=pillar.
        """
        profile = db.load_business_profile(project_id)
        if not profile:
            raise ValueError("No business profile. Run Phase 1 first.")

        keywords = db.load_validated_keywords(session_id)
        biz_intel = db.get_biz_intel(session_id) or {}
        pillar_kws = [k["keyword"] for k in keywords if k.get("pillar") == pillar][:30]
        business_context = self._build_business_context(profile, biz_intel, keywords)

        prompt = self._PILLAR_USER.format(
            business_context=_trunc(business_context, 800),
            pillar=pillar,
            pillar_keywords=", ".join(pillar_kws[:20]) if pillar_kws else "(no keywords yet)",
            count=count,
        )
        resp = kw2_ai_call(
            prompt, self._PILLAR_SYSTEM,
            provider=ai_provider, temperature=0.6,
            session_id=session_id, project_id=project_id,
            task="pillar_generate",
        )
        result = kw2_extract_json(resp)
        if not isinstance(result, dict):
            return {"questions_created": 0, "pillar": pillar}

        questions = result.get("questions", [])
        if not isinstance(questions, list):
            return {"questions_created": 0, "pillar": pillar}

        saved = self._save_pillar_questions(questions, pillar, session_id, project_id)
        return {"questions_created": saved, "pillar": pillar}

    def _save_pillar_questions(
        self, questions: list, pillar: str, session_id: str, project_id: str
    ) -> int:
        """Save pillar-generated questions with module_code=PE and pillar tag."""
        to_insert = []
        rejected = 0
        now = _now()
        for q in questions:
            if not isinstance(q, dict) or not q.get("question"):
                continue
            if not _is_valid_question(q["question"]):
                rejected += 1
                continue
            to_insert.append((
                _uid("pi_"),
                session_id,
                project_id,
                "PE",                          # module_code = Pillar Expand
                str(q.get("question", ""))[:2000],
                str(q.get("category", ""))[:200],
                str(q.get("why_it_matters", ""))[:500],
                "pillar_generate",             # data_source
                "medium",                      # effort
                pillar,                        # expansion_dimension_name = pillar name
                now,
            ))
        if not to_insert:
            log.info("_save_pillar_questions(%s): 0 saved, %d rejected", pillar, rejected)
            return 0
        conn = db.get_conn()
        try:
            conn.executemany(
                """INSERT INTO kw2_intelligence_questions
                   (id, session_id, project_id, module_code, question,
                    content_type, score_breakdown, data_source, effort,
                    expansion_dimension_name, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                to_insert,
            )
            conn.commit()
        finally:
            conn.close()
        log.info("_save_pillar_questions(%s): saved %d, rejected %d", pillar, len(to_insert), rejected)
        return len(to_insert)

    def list_questions(
        self,
        session_id: str,
        module_code: str | None = None,
        only_enriched: bool = False,
        limit: int = 500,
    ) -> list[dict]:
        conn = db.get_conn()
        try:
            conds = ["session_id=?", "is_duplicate=0"]
            params: list = [session_id]
            if module_code:
                conds.append("module_code=?")
                params.append(module_code)
            if only_enriched:
                conds.append("intent != ''")
            params.append(limit)
            rows = conn.execute(
                f"SELECT * FROM kw2_intelligence_questions WHERE {' AND '.join(conds)} "
                f"ORDER BY business_relevance DESC, final_score DESC LIMIT ?",
                params,
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                # Frontend expects question_text — alias the DB column
                d["question_text"] = d.get("question", "")
                d["cluster_id"] = d.get("content_cluster_id", "")
                d["module_id"] = d.get("module_code", "")
                d["audience"] = d.get("audience_segment", "")
                result.append(d)
            return result
        finally:
            conn.close()

    def get_summary(self, session_id: str) -> dict:
        conn = db.get_conn()
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM kw2_intelligence_questions WHERE session_id=? AND is_duplicate=0",
                (session_id,),
            ).fetchone()[0]
            by_module = conn.execute(
                """SELECT module_code, COUNT(*) as cnt
                   FROM kw2_intelligence_questions
                   WHERE session_id=? AND is_duplicate=0
                   GROUP BY module_code""",
                (session_id,),
            ).fetchall()
            enriched = conn.execute(
                "SELECT COUNT(*) FROM kw2_intelligence_questions WHERE session_id=? AND intent!='' AND is_duplicate=0",
                (session_id,),
            ).fetchone()[0]
            return {
                "total": total,
                "enriched": enriched,
                "by_module": {r["module_code"]: r["cnt"] for r in by_module},
            }
        finally:
            conn.close()

    def delete_question(self, question_id: str, session_id: str) -> bool:
        conn = db.get_conn()
        try:
            conn.execute(
                "DELETE FROM kw2_intelligence_questions WHERE id=? AND session_id=?",
                (question_id, session_id),
            )
            conn.commit()
            return True
        finally:
            conn.close()

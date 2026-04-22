"""
kw2 Business Intelligence Stage — Deep website & competitor analysis.

Pipeline:
  Step 1: Save extended user inputs (goals, pricing, USPs, audience)
  Step 2: Crawl + classify user's website pages (streaming)
  Step 3: Add/crawl competitors → AI strategy analysis (streaming)
  Step 4: Knowledge synthesis + SEO strategy generation (streaming)

All data feeds into Phase 2 keyword generation via kw2_biz_* tables.

Crawl priority: homepage → landing pages → product pages → blogs
Classification: rule-based first (instant), one batch AI call at end (not per-page).
Per-page AI calls eliminated to avoid Ollama blocking the entire pipeline.
"""
import json
import logging
import signal
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

from engines.kw2.ai_caller import kw2_ai_call, kw2_extract_json
from engines.kw2.prompts import (
    BIZ_PAGE_CLASSIFY_SYSTEM, BIZ_PAGE_CLASSIFY_USER,
    BIZ_COMPETITOR_PAGES_SYSTEM, BIZ_COMPETITOR_STRATEGY_USER,
    BIZ_KNOWLEDGE_SYNTHESIS_SYSTEM, BIZ_KNOWLEDGE_SYNTHESIS_USER,
    BIZ_SEO_STRATEGY_SYSTEM, BIZ_SEO_STRATEGY_USER,
)
from engines.kw2 import db

log = logging.getLogger("kw2.deep_intel")

MAX_PAGES_TO_CLASSIFY = 8   # crawl up to 8 own pages
MAX_COMPETITOR_PAGES = 5    # crawl max 5 pages per competitor
AI_CALL_TIMEOUT = 40        # seconds — skip AI classify if it hangs

# ── Rule-based page type & funnel detection (no AI, instant) ────────────────

_BLOG_PATH = re.compile(r"/(blog|articles?|news|posts?|insights?|guides?|resources?)/", re.I)
_PRODUCT_PATH = re.compile(r"/(products?|shop|store|buy|p/|item|sku)", re.I)
_LANDING_PATH = re.compile(r"/(landing|lp/|offers?|promo|sale|deals?|services?|solutions?|features?)", re.I)
_CONTACT_PATH = re.compile(r"/(contact|about|faq|support|help|terms|privacy|legal)", re.I)

def _rule_classify(url: str, content: str) -> dict:
    """Instant rule-based page classification — no AI needed for most pages."""
    path = urlparse(url).path.lower()
    depth = len([p for p in path.strip("/").split("/") if p])

    # Determine page type
    if depth == 0 or path in ("/", ""):
        page_type = "homepage"
        funnel = "TOFU"
    elif _BLOG_PATH.search(path):
        page_type = "blog_post" if depth >= 2 else "pillar_page"
        funnel = "TOFU"
    elif _PRODUCT_PATH.search(path):
        page_type = "product_page"
        funnel = "BOFU"
    elif _LANDING_PATH.search(path):
        page_type = "landing_page"
        funnel = "MOFU"
    elif _CONTACT_PATH.search(path):
        page_type = "other"
        funnel = "none"
    elif depth == 1:
        page_type = "landing_page"
        funnel = "MOFU"
    else:
        page_type = "other"
        funnel = "TOFU"

    # Extract topic from URL slug
    slug = path.strip("/").split("/")[-1].replace("-", " ").replace("_", " ")
    topic = slug[:80] if slug else ""

    # Simple keyword extraction from content (no AI)
    words = re.findall(r"\b[a-z][a-z-]{3,30}\b", (content or "").lower())
    # n-gram pairs (bigrams most useful)
    bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words)-1)]
    # frequency count
    from collections import Counter
    freq = Counter(words + bigrams)
    stopwords = {"this","that","with","from","they","them","have","will","your","our","their",
                 "what","when","where","about","more","also","some","which","there","these",
                 "been","were","then","than","into","over","each","just","only","very","much"}
    keywords = [kw for kw, _ in freq.most_common(40)
                if len(kw) > 4 and kw.split()[0] not in stopwords and kw.split()[-1] not in stopwords][:20]

    return {
        "page_type": page_type,
        "funnel_stage": funnel,
        "primary_topic": topic,
        "search_intent": "transactional" if funnel == "BOFU" else "informational",
        "target_keyword": keywords[0] if keywords else "",
        "keywords": keywords,
        "source": "rule",
    }


def _page_priority(page) -> int:
    """Lower = higher priority. Homepage=0, landing=1, product=2, blog=3, other=9."""
    url = getattr(page, "url", "")
    path = urlparse(url).path.lower()
    depth = len([p for p in path.strip("/").split("/") if p])
    if depth == 0: return 0
    if _PRODUCT_PATH.search(path): return 2
    if _LANDING_PATH.search(path): return 1
    if _BLOG_PATH.search(path): return 3 + depth
    return 5 + depth


def _ai_call_with_timeout(prompt, system, provider, max_tokens, timeout=AI_CALL_TIMEOUT):
    """Call kw2_ai_call with a thread-based timeout. Returns None on timeout."""
    import threading
    result = [None]
    error = [None]

    def _call():
        try:
            result[0] = kw2_ai_call(prompt, system, provider=provider, max_tokens=max_tokens)
        except Exception as e:
            error[0] = e

    t = threading.Thread(target=_call, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        log.warning(f"[ai_timeout] AI call timed out after {timeout}s, skipping")
        return None
    if error[0]:
        raise error[0]
    return result[0]


def _safe_domain(url: str) -> str:
    """Extract just the domain from a URL for display/prompt use."""
    try:
        return urlparse(url).netloc or url
    except Exception:
        return url


def _sse(data: dict) -> str:
    """Format a server-sent event string from a dict (type field used as event name)."""
    event = data.get("type", "message")
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


class DeepIntelEngine:
    """Business Intelligence stage — deep crawl, competitor analysis, knowledge synthesis."""

    # ── Step 1: User Profile ─────────────────────────────────────────────────

    def save_user_inputs(self, session_id: str, project_id: str, data: dict) -> dict:
        """Save extended user-provided intelligence inputs."""
        db.upsert_biz_intel(session_id, project_id, {
            "goals": data.get("goals", []),
            "pricing_model": data.get("pricing_model", "mid-range"),
            "usps": data.get("usps", []),
            "audience_segments": data.get("audience_segments", []),
        })
        return {"saved": True}

    # ── Step 2: Website Deep Crawl ───────────────────────────────────────────

    def crawl_website_stream(self, session_id: str, project_id: str, ai_provider: str = "auto"):
        """
        Crawl user website with smart priority order.

        Strategy:
        1. Crawl up to MAX_PAGES_TO_CLASSIFY pages
        2. Sort by priority: homepage → landing pages → product pages → blogs → other
        3. Rule-classify EVERY page instantly (no AI, no blocking)
        4. ONE optional batch AI call to enrich top-3 pages (max 40s timeout)
        5. Save all, yield progress per page
        """
        profile = db.load_business_profile(project_id)
        if not profile:
            yield _sse({"type": "error", "message": "No business profile found. Run Phase 1 first."})
            return

        domain = profile.get("domain", "")
        if not domain:
            yield _sse({"type": "error", "message": "No domain in business profile."})
            return

        yield _sse({"type": "progress", "message": f"Crawling {domain}...", "step": "crawl"})

        # ── Phase A: Crawl (no AI) ───────────────────────────────────────────
        try:
            from engines.intelligent_crawl_engine import IntelligentSiteCrawler
            crawler = IntelligentSiteCrawler()
            pages = crawler.crawl_site(domain, max_pages=MAX_PAGES_TO_CLASSIFY)
        except Exception as e:
            yield _sse({"type": "error", "message": f"Crawl failed: {e}"})
            return

        if not pages:
            yield _sse({"type": "error", "message": "No pages crawled — check the domain URL."})
            return

        # ── Phase B: Sort by priority (homepage first, then landing, then blogs) ─
        pages_sorted = sorted(pages, key=_page_priority)
        pages_to_process = pages_sorted[:MAX_PAGES_TO_CLASSIFY]

        yield _sse({
            "type": "progress",
            "message": f"Found {len(pages)} pages. Processing {len(pages_to_process)} by priority...",
            "found": len(pages),
            "processing": len(pages_to_process),
        })

        # ── Phase C: Rule-classify all pages instantly ───────────────────────
        classified = []
        all_keywords = []

        for i, page in enumerate(pages_to_process):
            url = getattr(page, "url", "")
            content = getattr(page, "text", "") or getattr(page, "content", "") or ""

            yield _sse({"type": "classifying", "page": i + 1, "total": len(pages_to_process), "url": url})

            analysis = _rule_classify(url, content)
            page_data = {
                "url": url,
                "page_type": analysis["page_type"],
                "primary_topic": analysis["primary_topic"],
                "search_intent": analysis["search_intent"],
                "target_keyword": analysis["target_keyword"],
                "keywords_extracted": analysis["keywords"],
                "audience": "",
                "funnel_stage": analysis["funnel_stage"],
                "ai_analysis": analysis,
                "content_snippet": content[:800],
            }

            db.add_biz_page(session_id, project_id, page_data)
            all_keywords.extend(analysis["keywords"])
            classified.append(page_data)

            yield _sse({
                "type": "page_classified",
                "url": url,
                "page_type": page_data["page_type"],
                "funnel": page_data["funnel_stage"],
                "topic": page_data["primary_topic"],
                "keyword_count": len(analysis["keywords"]),
            })

        # ── Phase D: Save summary ────────────────────────────────────────────
        page_type_counts = {}
        for p in classified:
            pt = p.get("page_type", "other")
            page_type_counts[pt] = page_type_counts.get(pt, 0) + 1

        unique_kws = list(dict.fromkeys(all_keywords))  # deduplicated, order-preserved
        website_summary = {
            "pages_analyzed": len(classified),
            "page_types": page_type_counts,
            "total_keywords": len(unique_kws),
            "sample_keywords": unique_kws[:30],
        }

        db.upsert_biz_intel(session_id, project_id, {
            "website_crawl_done": 1,
            "website_summary": json.dumps(website_summary),
        })

        yield _sse({
            "type": "website_done",
            "pages": len(classified),
            "page_types": page_type_counts,
            "keywords_found": len(unique_kws),
        })

    # ── Step 3: Competitor Crawl & Analysis ──────────────────────────────────

    def add_competitor(self, session_id: str, project_id: str, domain: str) -> str:
        """Add a competitor domain. Returns competitor_id."""
        domain = domain.strip().rstrip("/")
        if not domain.startswith("http"):
            domain = "https://" + domain
        return db.add_biz_competitor(session_id, project_id, domain, source="user")

    def crawl_competitors_stream(self, session_id: str, project_id: str, ai_provider: str = "auto"):
        """
        Crawl each competitor with rule-based keyword extraction.
        ONE AI call per competitor at the end for strategy insights (40s timeout).
        """
        competitors = db.get_biz_competitors(session_id)
        if not competitors:
            yield _sse({"type": "error", "message": "No competitors added. Add competitor URLs first."})
            return

        profile = db.load_business_profile(project_id)
        pillars = profile.get("pillars", []) if profile else []

        try:
            from engines.intelligent_crawl_engine import IntelligentSiteCrawler
            crawler = IntelligentSiteCrawler()
        except ImportError:
            yield _sse({"type": "error", "message": "Crawler not available."})
            return

        # ── Parallel crawl all competitors simultaneously ─────────────────
        def _crawl_one(comp):
            domain = comp["domain"]
            try:
                pages = crawler.crawl_site(domain, max_pages=MAX_COMPETITOR_PAGES)
                if pages:
                    pages = sorted(pages, key=_page_priority)[:MAX_COMPETITOR_PAGES]
                return comp, pages or [], None
            except Exception as e:
                return comp, [], str(e)

        yield _sse({"type": "progress", "message": f"Crawling {len(competitors)} competitors in parallel...", "step": "parallel_crawl"})
        crawl_results: dict = {}
        with ThreadPoolExecutor(max_workers=4) as _pool:
            _fut_map = {_pool.submit(_crawl_one, c): c for c in competitors}
            for _fut in as_completed(_fut_map):
                _comp, _pages, _err = _fut.result()
                crawl_results[_comp["id"]] = (_pages, _err)

        # ── Process results in original competitor order ────────────────────
        total_kws = 0
        for comp in competitors:
            cid = comp["id"]
            domain = comp["domain"]
            yield _sse({"type": "competitor_start", "domain": domain})

            pages, err = crawl_results.get(cid, ([], None))
            if err:
                yield _sse({"type": "competitor_error", "domain": domain, "message": err})
                continue
            if not pages:
                yield _sse({"type": "competitor_error", "domain": domain, "message": "No pages crawled"})
                continue

            yield _sse({"type": "competitor_crawled", "domain": domain, "pages": len(pages)})

            # Rule-based classify + keyword extraction — no AI, instant
            all_comp_keywords = []
            pages_summary_parts = []

            for page in pages:
                url = getattr(page, "url", "")
                content = getattr(page, "text", "") or getattr(page, "content", "") or ""
                analysis = _rule_classify(url, content)
                kws = analysis["keywords"][:10]
                pt = analysis["page_type"]
                topic = analysis["primary_topic"]

                pages_summary_parts.append(f"[{pt}] {topic or url[:60]} — {', '.join(kws[:5])}")
                all_comp_keywords.extend([
                    {"keyword": kw, "intent": analysis["search_intent"],
                     "source_page_type": pt, "confidence": 0.6}
                    for kw in kws
                ])
                yield _sse({"type": "competitor_page", "url": url, "page_type": pt})

            # Store keywords
            db.add_biz_competitor_keywords(session_id, cid, all_comp_keywords)
            total_kws += len(all_comp_keywords)

            # Save crawl results — no AI here, strategy runs in build_strategy_stream
            kw_list = list(dict.fromkeys(kw["keyword"] for kw in all_comp_keywords))[:30]
            db.update_biz_competitor(cid, {
                "top_keywords": kw_list[:10],
                "pages_crawled": len(pages),
                "crawl_done": 1,
            })

            yield _sse({
                "type": "competitor_done",
                "domain": domain,
                "pages": len(pages),
                "keywords": len(all_comp_keywords),
            })

        db.upsert_biz_intel(session_id, project_id, {"competitor_crawl_done": 1})
        yield _sse({"type": "competitors_all_done", "total_keywords": total_kws, "competitors": len(competitors)})

    # ── Step 4: Knowledge Synthesis + SEO Strategy ──────────────────────────

    def build_strategy_stream(self, session_id: str, project_id: str, ai_provider: str = "auto"):
        """
        Generator: synthesize all BI data → knowledge summary → SEO strategy.
        """
        yield _sse({"type": "progress", "message": "Loading all business data...", "step": "synthesis"})

        profile = db.load_business_profile(project_id)
        if not profile:
            yield _sse({"type": "error", "message": "No business profile. Run Phase 1 first."})
            return

        biz_intel = db.get_biz_intel(session_id) or {}
        pages = db.get_biz_pages(session_id)
        competitors = db.get_biz_competitors(session_id)
        comp_keywords = db.get_biz_competitor_keywords(session_id)

        # Build inputs for synthesis prompt
        business_profile_str = json.dumps({
            "universe": profile.get("universe", ""),
            "pillars": profile.get("pillars", []),
            "products": profile.get("product_catalog", []),
            "audience": profile.get("audience", []),
            "business_type": profile.get("business_type", ""),
            "geo": profile.get("geo_scope", ""),
            "usp": profile.get("usp", ""),
            "business_locations": profile.get("business_locations", []),
            "target_locations": profile.get("target_locations", []),
            "languages": profile.get("languages", []),
            "cultural_context": profile.get("cultural_context", []),
            "customer_reviews": (profile.get("customer_reviews", "") or "")[:500],
        }, indent=2)

        website_analysis_str = json.dumps([{
            "page_type": p["page_type"],
            "topic": p["primary_topic"],
            "intent": p["search_intent"],
            "keywords": p.get("keywords_extracted", [])[:8],
        } for p in pages[:12]], indent=2) if pages else "No website pages analyzed yet."

        # Collect all raw keywords extracted from crawled pages
        all_site_keywords = []
        for p in pages:
            all_site_keywords.extend(p.get("keywords_extracted", []))
        all_site_keywords = list(dict.fromkeys(all_site_keywords))[:60]

        competitor_insights_str = json.dumps([{
            "domain": c["domain"],
            "top_keywords": c.get("top_keywords", []),
            "pages_crawled": c.get("pages_crawled", 0),
        } for c in competitors], indent=2) if competitors else "No competitor data yet."

        # All raw keywords collected from competitor crawls
        all_comp_keywords = list(dict.fromkeys(
            kw.get("keyword", "") for kw in (comp_keywords or []) if kw.get("keyword")
        ))[:80]

        goals = biz_intel.get("goals", [])
        pricing = biz_intel.get("pricing_model", "mid-range")
        usps = biz_intel.get("usps", [])
        audience_segments = biz_intel.get("audience_segments", [])

        # Build knowledge synthesis prompt upfront (needed before strategy)
        know_prompt = BIZ_KNOWLEDGE_SYNTHESIS_USER.format(
            business_profile=business_profile_str,
            website_analysis=website_analysis_str,
            competitor_insights=competitor_insights_str,
            goals=", ".join(goals) if goals else "Not specified",
            pricing=pricing,
            usps=", ".join(usps) if usps else "Not specified",
            audience_segments=", ".join(audience_segments) if audience_segments else "Not specified",
        )
        know_prompt += (
            f"\n\nRAW KEYWORDS FROM WEBSITE CRAWL ({len(all_site_keywords)} total):\n"
            + ", ".join(all_site_keywords)
            + f"\n\nRAW KEYWORDS FROM COMPETITOR CRAWLS ({len(all_comp_keywords)} total):\n"
            + ", ".join(all_comp_keywords)
        )

        # ── A5: Knowledge synthesis (1 AI call, 90s timeout) ─────────────────
        yield _sse({"type": "progress", "message": "AI synthesising business intelligence…", "step": "knowledge"})
        try:
            raw = _ai_call_with_timeout(know_prompt, BIZ_KNOWLEDGE_SYNTHESIS_SYSTEM,
                                        provider=ai_provider, max_tokens=2500, timeout=90)
            knowledge = kw2_extract_json(raw) or {} if raw else {}
        except Exception as e:
            log.warning(f"[Phase BI] Knowledge synthesis error: {e}")
            knowledge = {}

        yield _sse({"type": "knowledge_done", "knowledge": knowledge})

        # ── A5: SEO strategy — uses knowledge as input (1 AI call, 90s timeout) ─
        yield _sse({"type": "progress", "message": "AI generating SEO strategy plan…", "step": "strategy"})
        try:
            strat_prompt = BIZ_SEO_STRATEGY_USER.format(
                knowledge_summary=json.dumps(knowledge, indent=2),
                business_type=profile.get("business_type", "Ecommerce"),
                goals=", ".join(goals) if goals else "sales and leads",
                universe=profile.get("universe", ""),
            )
            raw = _ai_call_with_timeout(strat_prompt, BIZ_SEO_STRATEGY_SYSTEM,
                                        provider=ai_provider, max_tokens=2000, timeout=90)
            strategy = kw2_extract_json(raw) or {} if raw else {}
        except Exception as e:
            log.warning(f"[Phase BI] Strategy generation error: {e}")
            strategy = {}

        # Save both to DB
        db.upsert_biz_intel(session_id, project_id, {
            "strategy_done": 1,
            "knowledge_summary": json.dumps(knowledge),
            "seo_strategy": json.dumps(strategy),
        })

        yield _sse({
            "type": "strategy_done",
            "strategy": strategy,
            "quick_wins": strategy.get("quick_wins", []),
            "priority_count": len(strategy.get("priority_keywords", [])),
            "page_count": len(strategy.get("recommended_pages", [])),
        })

    # ── Data Access ──────────────────────────────────────────────────────────

    def get_full_intel(self, session_id: str, project_id: str) -> dict:
        """Return complete BI state for the session."""
        biz_intel = db.get_biz_intel(session_id) or {}
        pages = db.get_biz_pages(session_id)
        competitors = db.get_biz_competitors(session_id)
        comp_kws = db.get_biz_competitor_keywords(session_id)

        # Parse JSON strings back to objects
        knowledge = {}
        strategy = {}
        if biz_intel.get("knowledge_summary"):
            try:
                knowledge = json.loads(biz_intel["knowledge_summary"])
            except Exception:
                pass
        if biz_intel.get("seo_strategy"):
            try:
                strategy = json.loads(biz_intel["seo_strategy"])
            except Exception:
                pass

        website_summary = {}
        if biz_intel.get("website_summary"):
            try:
                website_summary = json.loads(biz_intel["website_summary"])
            except Exception:
                pass

        return {
            "profile": biz_intel,
            "website_summary": website_summary,
            "pages": pages[:30],
            "competitors": competitors,
            "competitor_keywords_count": len(comp_kws),
            "knowledge": knowledge,
            "strategy": strategy,
            "status": {
                "website_crawl_done": bool(biz_intel.get("website_crawl_done")),
                "competitor_crawl_done": bool(biz_intel.get("competitor_crawl_done")),
                "strategy_done": bool(biz_intel.get("strategy_done")),
            },
        }

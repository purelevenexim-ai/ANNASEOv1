"""
kw2 Phase 1 — Business Intelligence Engine.

Orchestrates: crawl → segment → extract entities → competitor insights → AI analysis
→ consistency check → confidence score → persist.
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

from engines.kw2.constants import NEGATIVE_PATTERNS, CRAWL_MAX_PAGES, PROFILE_CACHE_DAYS
from engines.kw2.prompts import BUSINESS_ANALYSIS_SYSTEM, BUSINESS_ANALYSIS_USER
from engines.kw2.ai_caller import kw2_ai_call, kw2_extract_json
from engines.kw2.content_segmenter import segment_content
from engines.kw2.entity_extractor import extract_entities
from engines.kw2.competitor import get_competitor_insights
from engines.kw2.confidence import compute_confidence
from engines.kw2.consistency import check_consistency
from engines.kw2 import db

log = logging.getLogger("kw2.business")


class BusinessIntelligenceEngine:
    """Phase 1: Analyze a business website and produce a structured profile."""

    def analyze(
        self,
        project_id: str,
        url: str | None = None,
        manual_input: dict | None = None,
        competitor_urls: list[str] | None = None,
        ai_provider: str = "auto",
        force: bool = False,
    ) -> dict:
        """
        Full Phase 1 analysis pipeline.

        Returns a business profile dict with confidence score.
        Uses cache if available and not expired (unless force=True).
        """
        # 1. Cache check
        if not force:
            cached = db.load_business_profile(project_id)
            if cached and self._is_fresh(cached):
                log.info(f"[Phase1] Using cached profile for {project_id}")
                cached["cached"] = True
                return cached

        # 2. Crawl customer site
        pages = []
        if url:
            pages = self._crawl(url)
            log.info(f"[Phase1] Crawled {len(pages)} pages from {url}")

        # 3. Segment content
        segmented = segment_content(pages) if pages else {
            "products": "", "categories": "", "about": "", "found_products": []
        }

        # 4. Extract entities
        combined_text = f"{segmented['products']} {segmented['categories']}"
        entities, topics = extract_entities(combined_text)

        # 5. Competitor insights
        comp_text = get_competitor_insights(competitor_urls or [], [])

        # 6. Build AI prompt
        prompt = BUSINESS_ANALYSIS_USER.format(
            products=segmented["products"] or "(no product pages found)",
            categories=segmented["categories"] or "(no category pages found)",
            about=segmented["about"] or "(no about page found)",
            entities=", ".join(entities[:20]) or "(none extracted)",
            topics=", ".join(topics[:20]) or "(none extracted)",
            competitor_data=comp_text or "(no competitor data)",
            manual_input=json.dumps(manual_input) if manual_input else "(none provided)",
        )

        # 7. AI call
        response = kw2_ai_call(prompt, BUSINESS_ANALYSIS_SYSTEM, provider=ai_provider)
        profile = kw2_extract_json(response)

        # 8. Validate
        if profile and isinstance(profile, dict):
            ok, errors = self._validate_profile(profile)
            if not ok:
                log.warning(f"[Phase1] Profile validation failed: {errors}. Retrying.")
                retry_prompt = f"PREVIOUS ATTEMPT HAD ERRORS: {errors}\n\n{prompt}"
                response2 = kw2_ai_call(retry_prompt, BUSINESS_ANALYSIS_SYSTEM, provider=ai_provider)
                profile2 = kw2_extract_json(response2)
                if profile2 and isinstance(profile2, dict):
                    ok2, _ = self._validate_profile(profile2)
                    if ok2:
                        profile = profile2
        else:
            log.warning("[Phase1] AI returned no parseable profile, using rule-based fallback")
            profile = None

        # 9. Rule-based fallback
        if not profile:
            profile = self._rule_based_fallback(pages, segmented, manual_input)

        # 10. Consistency check
        is_consistent = check_consistency(profile, ai_provider)
        if not is_consistent:
            log.warning("[Phase1] Profile flagged as inconsistent (proceeding anyway)")

        # 11. Merge manual overrides
        if manual_input:
            self._merge_manual(profile, manual_input)

        # 12. Confidence score
        profile["confidence_score"] = compute_confidence(profile)

        # 13. Add metadata
        profile["domain"] = urlparse(url).netloc if url else ""
        profile["raw_ai_json"] = profile.copy()
        profile["manual_input"] = manual_input
        profile["cached"] = False
        profile["pages_crawled"] = len(pages)

        # 14. Persist
        db.save_business_profile(project_id, profile)
        log.info(f"[Phase1] Saved profile for {project_id} (confidence={profile['confidence_score']})")

        return profile

    # ── Private helpers ──────────────────────────────────────────────────

    def _crawl(self, url: str) -> list:
        """Crawl site, return CrawledPage objects. Filters to useful page types."""
        try:
            from engines.intelligent_crawl_engine import IntelligentSiteCrawler
            crawler = IntelligentSiteCrawler()
            pages = crawler.crawl_site(url, max_pages=CRAWL_MAX_PAGES)
            # Keep only useful page types
            useful = ["product", "category", "homepage", "about"]
            return [p for p in pages if getattr(p, "page_type", "").lower() in useful]
        except Exception as e:
            log.error(f"[Phase1] Crawl failed for {url}: {e}")
            return []

    def _is_fresh(self, profile: dict) -> bool:
        """Check if cached profile is within PROFILE_CACHE_DAYS."""
        created = profile.get("created_at", "")
        if not created:
            return False
        try:
            dt = datetime.fromisoformat(created)
            return datetime.now(timezone.utc) - dt < timedelta(days=PROFILE_CACHE_DAYS)
        except (ValueError, TypeError):
            return False

    def _validate_profile(self, profile: dict) -> tuple[bool, list[str]]:
        """Validate profile has required fields and quality."""
        errors = []
        pillars = profile.get("pillars", [])
        if not isinstance(pillars, list) or len(pillars) < 1:
            errors.append("pillars must have at least 1 item")

        # Check no pillar contains negative patterns
        for p in (pillars if isinstance(pillars, list) else []):
            pl = str(p).lower()
            for neg in NEGATIVE_PATTERNS[:10]:  # check main negatives
                if neg in pl:
                    errors.append(f"pillar '{p}' contains negative pattern '{neg}'")

        catalog = profile.get("product_catalog", [])
        if not isinstance(catalog, list) or len(catalog) < 1:
            errors.append("product_catalog must have at least 1 item")

        neg_scope = profile.get("negative_scope", [])
        if not isinstance(neg_scope, list):
            errors.append("negative_scope must be a list")

        return (len(errors) == 0, errors)

    def _rule_based_fallback(self, pages: list, segmented: dict, manual_input: dict | None) -> dict:
        """Create a minimal profile from crawled data + manual input when AI fails."""
        products = segmented.get("found_products", [])
        manual_products = []
        if manual_input:
            manual_products = manual_input.get("products", [])
            if isinstance(manual_products, str):
                manual_products = [p.strip() for p in manual_products.split(",") if p.strip()]

        all_products = list(set(products + manual_products))
        pillars = all_products[:10] if all_products else ["general"]

        return {
            "universe": manual_input.get("business_name", "Business") if manual_input else "Business",
            "pillars": pillars,
            "product_catalog": all_products,
            "modifiers": ["wholesale", "bulk", "organic", "premium", "online"],
            "audience": manual_input.get("personas", []) if manual_input else [],
            "intent_signals": ["transactional"],
            "geo_scope": manual_input.get("geographic_focus", "India") if manual_input else "India",
            "business_type": manual_input.get("business_type", "Ecommerce") if manual_input else "Ecommerce",
            "negative_scope": list(NEGATIVE_PATTERNS[:15]),
        }

    def _merge_manual(self, profile: dict, manual_input: dict):
        """Merge user-provided overrides into AI-generated profile."""
        # Add manual products not already in catalog
        manual_products = manual_input.get("products", [])
        if isinstance(manual_products, str):
            manual_products = [p.strip() for p in manual_products.split(",") if p.strip()]

        existing = set(str(p).lower() for p in profile.get("product_catalog", []))
        for p in manual_products:
            if p.lower() not in existing:
                profile.setdefault("product_catalog", []).append(p)

        # Override business_type if provided
        if manual_input.get("business_type"):
            profile["business_type"] = manual_input["business_type"]

        # Override geo_scope if provided
        if manual_input.get("geographic_focus"):
            profile["geo_scope"] = manual_input["geographic_focus"]

        # Add personas to audience
        manual_personas = manual_input.get("personas", [])
        if manual_personas:
            existing_aud = set(str(a).lower() for a in profile.get("audience", []))
            for persona in manual_personas:
                if str(persona).lower() not in existing_aud:
                    profile.setdefault("audience", []).append(persona)

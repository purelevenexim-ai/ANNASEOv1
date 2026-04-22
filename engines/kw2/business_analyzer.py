"""
kw2 Phase 1 — Business Intelligence Engine.

Orchestrates: crawl → segment → extract entities → competitor insights → AI analysis
→ consistency check → confidence score → persist.
"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from engines.kw2.pillar_extractor import PillarExtractor
from engines.kw2.modifier_extractor import ModifierExtractor, DEFAULT_MODIFIERS
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
        progress_cb=None,
        session_id: str | None = None,
    ) -> dict:
        """
        Full Phase 1 analysis pipeline.

        Returns a business profile dict with confidence score.
        Uses cache if available and not expired (unless force=True).

        progress_cb: optional callable(dict) — receives real-time events:
          {"type": "progress", "step": "crawling", "pct": 20, "message": "..."}
          {"type": "provider_selected", "provider": "groq"}
          {"type": "rate_limited", "provider": "groq", "switching_to": "gemini", "message": "..."}
          {"type": "provider_switch", "from": "groq", "to": "gemini", "reason": "..."}
          {"type": "providers_exhausted", "message": "..."}
          {"type": "done", "profile": {...}}
          {"type": "error", "message": "..."}
        """
        def _emit(ev: dict):
            if progress_cb:
                try:
                    progress_cb(ev)
                except Exception:
                    pass

        # 1. Cache check
        if not force:
            cached = db.load_business_profile(project_id)
            if cached and self._is_fresh(cached):
                log.info(f"[Phase1] Using cached profile for {project_id}")
                cached["cached"] = True
                _emit({"type": "progress", "step": "cache_hit", "pct": 100,
                       "message": "✅ Using cached profile (fresh)"})
                return cached

        # 2. Check for cached crawl data (allows skipping re-crawl on provider retry)
        crawl_cache = db.load_phase1_crawl_cache(session_id) if session_id else None
        if crawl_cache:
            log.info(f"[Phase1] Using cached crawl data for session {session_id}")
            _emit({"type": "progress", "step": "crawl_cache", "pct": 35,
                   "message": "⚡ Using cached crawl — skipping re-crawl (fast retry)"})
            pages = []   # not needed, segmented is cached
            segmented = crawl_cache.get("segmented", {"products": "", "categories": "", "about": "", "found_products": []})
            entities = crawl_cache.get("entities", [])
            topics = crawl_cache.get("topics", [])
            comp_text = crawl_cache.get("comp_text", "")
        else:
            # 2 & 5. Crawl customer site + competitor insights in parallel
            _emit({"type": "progress", "step": "crawling", "pct": 10,
                   "message": f"🌐 Crawling {url or 'business'}..."})
            pages = []
            comp_text = ""
            with ThreadPoolExecutor(max_workers=2) as executor:
                crawl_future = executor.submit(self._crawl, url) if url else None
                comp_future = executor.submit(get_competitor_insights, competitor_urls or [], [])
                if crawl_future is not None:
                    try:
                        pages = crawl_future.result()
                        log.info(f"[Phase1] Crawled {len(pages)} pages from {url}")
                        _emit({"type": "progress", "step": "crawl_done", "pct": 20,
                               "message": f"📄 Crawled {len(pages)} pages from site"})
                    except Exception as e:
                        log.error(f"[Phase1] Crawl task failed: {e}")
                        _emit({"type": "progress", "step": "crawl_warn", "pct": 20,
                               "message": f"⚠️ Site crawl failed (proceeding with manual input): {e}"})
                try:
                    comp_text = comp_future.result()
                except Exception as e:
                    log.error(f"[Phase1] Competitor task failed: {e}")

            _emit({"type": "progress", "step": "segmenting", "pct": 28,
                   "message": "🔍 Extracting products, categories, entities..."})

            # 3. Segment content
            try:
                segmented = segment_content(pages) if pages else {
                    "products": "", "categories": "", "about": "", "found_products": []
                }
            except Exception as e:
                log.error(f"[Phase1] segment_content failed: {e}")
                segmented = {"products": "", "categories": "", "about": "", "found_products": []}

            # 4. Extract entities
            combined_text = f"{segmented['products']} {segmented['categories']}"
            try:
                entities, topics = extract_entities(combined_text)
            except Exception as e:
                log.error(f"[Phase1] extract_entities failed: {e}")
                entities, topics = [], []

            # Save crawl data to cache so retry can skip this step
            if session_id:
                try:
                    db.save_phase1_crawl_cache(session_id, {
                        "segmented": segmented,
                        "entities": entities,
                        "topics": topics,
                        "comp_text": comp_text,
                    })
                except Exception as e:
                    log.warning(f"[Phase1] Failed to cache crawl data: {e}")

        _emit({"type": "progress", "step": "ai_analysis", "pct": 40,
               "message": "🤖 Running AI business analysis..."})

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

        # 7. AI call — pass event_cb so provider switches are visible in real time
        response = kw2_ai_call(prompt, BUSINESS_ANALYSIS_SYSTEM, provider=ai_provider,
                               event_cb=_emit)
        profile = kw2_extract_json(response)

        _emit({"type": "progress", "step": "validating", "pct": 75,
               "message": "✔️ Validating profile quality..."})

        # 8a. Auto-clean AI-returned pillars: strip product-name noise → clean search entities
        #     e.g. "Kerala Black Pepper - 200gm" → "black pepper"
        if profile and isinstance(profile, dict) and isinstance(profile.get("pillars"), list):
            profile["pillars"] = PillarExtractor().extract(profile["pillars"])

        # 8b. Validate
        if profile and isinstance(profile, dict):
            ok, errors_list = self._validate_profile(profile)
            if not ok:
                log.warning(f"[Phase1] Profile validation failed: {errors_list}. Retrying.")
                _emit({"type": "progress", "step": "retry", "pct": 78,
                       "message": f"🔄 Profile quality check failed — retrying AI call..."})
                retry_prompt = f"PREVIOUS ATTEMPT HAD ERRORS: {errors_list}\n\n{prompt}"
                response2 = kw2_ai_call(retry_prompt, BUSINESS_ANALYSIS_SYSTEM, provider=ai_provider,
                                        event_cb=_emit)
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
        try:
            is_consistent = check_consistency(profile, ai_provider)
            if not is_consistent:
                log.warning("[Phase1] Profile flagged as inconsistent (proceeding anyway)")
        except Exception as e:
            log.error(f"[Phase1] check_consistency failed: {e} — proceeding without consistency check")

        # 11. Merge manual overrides
        if manual_input:
            self._merge_manual(profile, manual_input)

        # 11b. Fix generic universe — AI sometimes returns "Business", "Company" etc.
        profile["universe"] = self._fix_generic_universe(
            profile.get("universe", ""),
            profile.get("pillars", []),
            profile.get("product_catalog", []),
            manual_input,
        )

        # 12. Confidence score
        profile["confidence_score"] = compute_confidence(profile)

        _emit({"type": "progress", "step": "saving", "pct": 90,
               "message": "💾 Saving profile..."})

        # 13. Add metadata
        profile["domain"] = urlparse(url).netloc if url else ""
        profile["raw_ai_json"] = profile.copy()
        profile["manual_input"] = manual_input
        profile["cached"] = False
        profile["pages_crawled"] = len(pages) if not crawl_cache else crawl_cache.get("pages_crawled", 0)

        # 14. Persist
        db.save_business_profile(project_id, profile)
        log.info(f"[Phase1] Saved profile for {project_id} (confidence={profile['confidence_score']})")

        # Clear crawl cache on success (no longer needed)
        if session_id and crawl_cache is not None:
            try:
                db.save_phase1_crawl_cache(session_id, {})
            except Exception:
                pass

        _emit({"type": "done", "profile": profile})

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
        # Clean product names → search entities (not raw product labels)
        pillars = PillarExtractor().extract(all_products) or ["general"]

        # Check if user provided manual pillars directly — they take highest priority
        manual_pillars = []
        if manual_input:
            mp = manual_input.get("pillars", [])
            if isinstance(mp, str):
                mp = [p.strip() for p in mp.split(",") if p.strip()]
            manual_pillars = [p for p in mp if p]
        if manual_pillars:
            # Manual pillars override derived ones; derived fill any gaps
            existing = set(p.lower() for p in manual_pillars)
            for p in pillars:
                if p.lower() not in existing:
                    manual_pillars.append(p)
            pillars = manual_pillars[:12]

        derived_universe = self._fix_generic_universe(
            manual_input.get("business_name", "") if manual_input else "",
            pillars,
            all_products,
            manual_input,
        )
        return {
            "universe": derived_universe,
            "pillars": pillars,
            "product_catalog": all_products,
            "modifiers": DEFAULT_MODIFIERS,
            "audience": manual_input.get("personas", []) if manual_input else [],
            "intent_signals": ["transactional"],
            "geo_scope": manual_input.get("geographic_focus", "India") if manual_input else "India",
            "business_type": manual_input.get("business_type", "Ecommerce") if manual_input else "Ecommerce",
            "negative_scope": list(NEGATIVE_PATTERNS[:15]),
        }

    # Generic universe names the AI (or fallback) should not produce
    _GENERIC_UNIVERSE: frozenset = frozenset({
        "business", "company", "store", "shop", "ecommerce",
        "website", "online", "brand", "platform", "enterprise",
        "all", "general", "various", "mixed",
    })

    def _fix_generic_universe(self, universe: str, pillars: list, product_catalog: list, manual_input: dict | None) -> str:
        """Return a specific 2-3 word universe name, replacing any generic placeholder."""
        clean = (universe or "").strip()
        words = clean.lower().split()
        # Accept if every word is not just a generic term and universe is ≥2 words
        if len(words) >= 2 and not all(w in self._GENERIC_UNIVERSE for w in words):
            return clean
        # Single-word or all-generic → derive a better name
        # Priority 1: manual business_name that isn't generic
        if manual_input:
            bname = manual_input.get("business_name", "").strip()
            if bname and bname.lower() not in self._GENERIC_UNIVERSE:
                return bname
        # Priority 2: derive from pillars — take the most specific/shortest pillar + category
        if pillars:
            # Find the shortest (most atomic) pillar as the anchor term
            anchor = min(pillars, key=lambda p: len(p.split()))
            anchor_title = anchor.title()
            if len(pillars) > 1:
                return f"{anchor_title} Products"
            return f"{anchor_title} Store"
        # Priority 3: derive from first product catalog item
        if product_catalog:
            return str(product_catalog[0]).title()
        # Last resort: keep original or use a non-generic placeholder
        return clean if clean else "Specialty Products"

    def _derive_pillars_from_catalog(self, product_catalog: list[str]) -> list[str]:
        """Derive clean search-entity pillars from raw product catalog names."""
        return PillarExtractor().extract(product_catalog)

    def _merge_manual(self, profile: dict, manual_input: dict):
        """Merge user-provided overrides into AI-generated profile.

        Priority for pillars:
        1. manual_input["pillars"]  — user explicitly typed (highest trust)
        2. AI-cleaned profile["pillars"] — AI-generated (clean after step 8a)
        3. Derived from product_catalog — entity extraction fallback
        """
        # ── Pillar priority merge ────────────────────────────────────────────
        manual_pillars = manual_input.get("pillars", [])
        if isinstance(manual_pillars, str):
            manual_pillars = [p.strip() for p in manual_pillars.split(",") if p.strip()]
        manual_pillars = [p for p in manual_pillars if p and len(p) > 1]

        if manual_pillars:
            # User-typed pillars are KEPT AS-IS — they represent confirmed user intent.
            # Only AI-generated pillars go through PillarExtractor cleaning.
            cleaned_manual = list(manual_pillars)  # preserve user originals
            # User's pillars take precedence.  AI pillars supplement if there's room.
            existing = set(p.lower() for p in cleaned_manual)
            ai_pillars = profile.get("pillars", [])
            for p in ai_pillars:
                if p.lower() not in existing and len(cleaned_manual) < 12:
                    existing.add(p.lower())
                    cleaned_manual.append(p)
            profile["pillars"] = cleaned_manual[:12]
            log.info(f"[merge_manual] Using manual pillars (cleaned): {cleaned_manual[:5]}")
        elif not profile.get("pillars"):
            # No manual pillars and AI returned nothing → derive from product catalog
            derived = self._derive_pillars_from_catalog(profile.get("product_catalog", []))
            if derived:
                profile["pillars"] = derived
                log.info(f"[merge_manual] Derived pillars from catalog: {derived[:5]}")

        # ── Product catalog merge ────────────────────────────────────────────
        manual_products = manual_input.get("products", [])
        if isinstance(manual_products, str):
            manual_products = [p.strip() for p in manual_products.split(",") if p.strip()]

        existing_prods = set(str(p).lower() for p in profile.get("product_catalog", []))
        for p in manual_products:
            if p.lower() not in existing_prods:
                profile.setdefault("product_catalog", []).append(p)

        # ── Other field overrides ────────────────────────────────────────────
        if manual_input.get("business_type"):
            profile["business_type"] = manual_input["business_type"]

        if manual_input.get("geo_scope") or manual_input.get("geographic_focus"):
            profile["geo_scope"] = manual_input.get("geo_scope") or manual_input["geographic_focus"]

        # Add audience (manual_input uses "audience" key from frontend)
        manual_personas = manual_input.get("audience", []) or manual_input.get("personas", [])
        if manual_personas:
            existing_aud = set(str(a).lower() for a in profile.get("audience", []))
            for persona in manual_personas:
                if str(persona).lower() not in existing_aud:
                    profile.setdefault("audience", []).append(persona)

        # ── Modifiers: user values take priority, AI supplements ─────────────
        manual_modifiers = manual_input.get("modifiers", [])
        if isinstance(manual_modifiers, str):
            manual_modifiers = [m.strip() for m in manual_modifiers.split(",") if m.strip()]
        if manual_modifiers:
            existing_mods = set(m.lower() for m in manual_modifiers)
            ai_modifiers = profile.get("modifiers", [])
            if isinstance(ai_modifiers, list):
                for m in ai_modifiers:
                    if str(m).lower() not in existing_mods:
                        existing_mods.add(str(m).lower())
                        manual_modifiers.append(m)
            profile["modifiers"] = manual_modifiers
            log.info(f"[merge_manual] Merged modifiers: {len(manual_modifiers)} total")

        # ── Negative scope: user values take priority, AI supplements ────────
        manual_neg = manual_input.get("negative_scope", [])
        if isinstance(manual_neg, str):
            manual_neg = [n.strip() for n in manual_neg.split(",") if n.strip()]
        if manual_neg:
            existing_neg = set(n.lower() for n in manual_neg)
            ai_neg = profile.get("negative_scope", [])
            if isinstance(ai_neg, list):
                for n in ai_neg:
                    if str(n).lower() not in existing_neg:
                        existing_neg.add(str(n).lower())
                        manual_neg.append(n)
            profile["negative_scope"] = manual_neg
            log.info(f"[merge_manual] Merged negative_scope: {len(manual_neg)} total")

        # ── Pass-through fields: preserve user inputs in profile ─────────────
        if manual_input.get("usp"):
            profile["usp"] = manual_input["usp"]
        if manual_input.get("business_locations"):
            profile["business_locations"] = manual_input["business_locations"]
        if manual_input.get("target_locations"):
            profile["target_locations"] = manual_input["target_locations"]
        if manual_input.get("languages"):
            profile["languages"] = manual_input["languages"]
        if manual_input.get("cultural_context"):
            profile["cultural_context"] = manual_input["cultural_context"]
        if manual_input.get("customer_reviews"):
            profile["customer_reviews"] = manual_input["customer_reviews"]

        # ── Extract additional pillars from customer reviews ─────────────────
        reviews_text = manual_input.get("customer_reviews", "")
        if reviews_text and isinstance(reviews_text, str) and len(reviews_text.strip()) > 10:
            # Split reviews into candidate terms: sentences → noun-phrase-like chunks
            import re
            # Extract quoted phrases and significant multi-word chunks
            candidates = []
            # Quoted phrases (e.g. "organic turmeric")
            quoted = re.findall(r'"([^"]+)"', reviews_text)
            candidates.extend(quoted)
            # Comma/period/newline-separated fragments
            fragments = re.split(r'[,.\n;!?]+', reviews_text)
            for frag in fragments:
                frag = frag.strip()
                words = frag.split()
                if 1 <= len(words) <= 4 and len(frag) > 3:
                    candidates.append(frag)
            if candidates:
                review_pillars = PillarExtractor().extract(candidates)
                if review_pillars:
                    existing_pillars = set(p.lower() for p in profile.get("pillars", []))
                    added = 0
                    for rp in review_pillars:
                        if rp.lower() not in existing_pillars and len(profile.get("pillars", [])) < 15:
                            existing_pillars.add(rp.lower())
                            profile.setdefault("pillars", []).append(rp)
                            added += 1
                    if added:
                        log.info(f"[merge_manual] Added {added} pillars from customer reviews")

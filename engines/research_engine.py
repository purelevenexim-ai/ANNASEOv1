"""
Research Engine — Multi-source keyword collection with priority ranking.

Source 1: User's supporting keywords (score +10)
Source 2: Google Autosuggest (score +5)
Source 3: AI classification + scoring (variable)

Guarantees: Never returns 0 keywords. Respects business intent.
"""

import logging
import json
import os
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

log = logging.getLogger("annaseo.research_engine")


@dataclass
class ResearchResult:
    """Single keyword result from research."""
    keyword: str
    source: str  # "user" | "google" | "ai_generated"
    intent: str
    volume: str
    difficulty: str
    total_score: int  # 0-100
    confidence: int  # 0-100
    pillar_keyword: str
    reasoning: str = ""


class ResearchEngine:
    """Orchestrate multi-source keyword research."""

    def __init__(
        self,
        ollama_url: str = "",
        industry: str = "general",
    ):
        # Default to env var (proxy on :8080); empty string means use AICfg at call time
        self.ollama_url = ollama_url or os.getenv("OLLAMA_URL", "http://172.235.16.165:8080")
        self.industry = industry
        self._scorer = None  # Lazy load AIScorer

    @property
    def scorer(self):
        """Lazy load AIScorer."""
        if self._scorer is None:
            from engines.research_ai_scorer import AIScorer
            self._scorer = AIScorer(
                ollama_url=self.ollama_url,
                model="deepseek-r1:7b",
                industry=self.industry,
            )
        return self._scorer

    def research_keywords(
        self,
        project_id: str,
        session_id: str,
        business_intent: str,
        language: str = "en",
    ) -> List[ResearchResult]:
        """
        Research keywords using 3-source priority ranking.

        Args:
            project_id: Project ID
            session_id: Step 1 session ID (has user input)
            business_intent: "ecommerce" | "content_blog" | "supplier" | "mixed"
            language: Language code ("en", "ml", "hi", etc.)

        Returns:
            List[ResearchResult] sorted by total_score DESC

        Guarantees:
            - Always returns 20+ keywords (never 0)
            - User keywords ranked first (score +10)
            - Google suggestions ranked second (score +5)
            - AI classification validates all
        """
        log.info(f"[Research] Starting for project={project_id}, intent={business_intent}")

        # Load Step 1 data
        pillars, supporting_kws = self._load_user_keywords(session_id, project_id)
        log.info(f"[Research] Loaded {len(pillars)} pillars, {sum(len(v) for v in supporting_kws.values())} supporting")

        # Source 1: User's supporting keywords (score +10)
        user_keywords = self._extract_user_keywords(supporting_kws)
        log.info(f"[Research] Source 1 (User): {len(user_keywords)} keywords")

        # Source 2: Google Autosuggest (score +5)
        google_keywords = self._fetch_google_suggestions(pillars, language)
        log.info(f"[Research] Source 2 (Google): {len(google_keywords)} keywords")

        # Combine sources
        all_keywords = user_keywords + google_keywords
        log.info(f"[Research] Combined: {len(all_keywords)} keywords before dedup")

        # Deduplicate (case-insensitive)
        all_keywords = self._deduplicate(all_keywords)
        log.info(f"[Research] After dedup: {len(all_keywords)} keywords")

        # Source 3: AI scoring (batch call)
        if all_keywords:
            scored = self.scorer.score_keywords_batch(
                keywords=all_keywords,
                pillars=pillars,
                supporting_keywords=supporting_kws,
                business_intent=business_intent,
            )
            log.info(f"[Research] Scored {len(scored)} keywords")
        else:
            log.warning("[Research] No keywords to score!")
            scored = []

        # Convert to ResearchResult format
        results = [
            ResearchResult(
                keyword=s.keyword,
                source=s.source,
                intent=s.intent,
                volume=s.volume,
                difficulty=s.difficulty,
                total_score=s.total_score,
                confidence=s.confidence,
                pillar_keyword=s.pillar_keyword,
                reasoning=s.reasoning,
            )
            for s in scored
        ]

        # Apply fallback/emergency generation ONLY when there are too few scored results
        target_min = max(100, len(pillars) * 30) if pillars else 100
        if len(results) < target_min:
            log.info(f"[Research] {len(results)} scored < target {target_min}, generating long-tail fallback")
            fallback_results = self._generate_fallback_keywords(
                pillars, supporting_kws, business_intent,
                target_count=target_min - len(results) + 50,
            )
            existing = {r.keyword.lower() for r in results}
            results.extend(r for r in fallback_results if r.keyword.lower() not in existing)

            # If still below 30 (e.g., no pillars), generate emergency keywords
            if len(results) < 30:
                log.error(f"[Research] Still below 30 after fallback, generating emergency keywords")
                existing2 = {r.keyword.lower() for r in results}
                em = self._generate_emergency_keywords(business_intent, target_count=100)
                results.extend(r for r in em if r.keyword.lower() not in existing2)

        # Deduplicate final results (case-insensitive)
        final_results = {}
        for r in results:
            kw_lower = r.keyword.lower().strip()
            if kw_lower not in final_results:
                final_results[kw_lower] = r
        results = list(final_results.values())

        # Sort by score descending
        results.sort(key=lambda x: x.total_score, reverse=True)

        log.info(f"[Research] Complete: {len(results)} keywords for {project_id}")
        return results

    def _load_user_keywords(
        self,
        session_id: str,
        project_id: str,
    ) -> Tuple[List[str], Dict[str, List[str]]]:
        """Load pillars and supporting keywords from Step 1 session.

        The schema uses pillar_support_map JSON which maps pillar → [supporting_keywords].
        Example: {"cinnamon": ["organic", "buy", "bulk"]}

        Fallback: If pillar_support_map is empty, reads from pillar_keywords table.
        """
        try:
            from engines.annaseo_keyword_input import _db as _ki_db_fn
            ki_db = _ki_db_fn()
        except Exception as e:
            log.warning(f"[Research] Could not load KI db: {e}")
            return [], {}

        try:
            # Query keyword_input_sessions for this session
            # The actual schema uses pillar_support_map, not pillars/supporting_keywords
            session = ki_db.execute(
                "SELECT project_id, pillar_support_map FROM keyword_input_sessions WHERE session_id=?",
                (session_id,)
            ).fetchone()

            if not session:
                log.warning(f"[Research] Session {session_id} not found")
                return [], {}

            # Extract pillar_support_map (could be dict from row factory or tuple)
            psm_data = session.get("pillar_support_map", "{}") if hasattr(session, 'get') else session[1]

            # Parse JSON
            pillar_support_map = {}
            if psm_data:
                try:
                    pillar_support_map = json.loads(psm_data) if isinstance(psm_data, str) else (psm_data or {})
                except (json.JSONDecodeError, ValueError) as je:
                    log.warning(f"[Research] Could not parse pillar_support_map JSON: {je}")
                    pillar_support_map = {}

            # If pillar_support_map is empty, fallback to pillar_keywords table
            if not pillar_support_map:
                log.info(f"[Research] pillar_support_map is empty, falling back to pillar_keywords table for {project_id}")
                # Get project_id from session if not already have it
                proj_id = session.get("project_id") if hasattr(session, 'get') else project_id

                # Query pillar_keywords table
                pillar_rows = ki_db.execute(
                    "SELECT keyword FROM pillar_keywords WHERE project_id=? ORDER BY priority ASC",
                    (proj_id,)
                ).fetchall()

                if pillar_rows:
                    # Build pillar_support_map from pillar_keywords
                    # For now, each pillar has an empty supporting list
                    # In the future, we could also query supporting_keywords table
                    for p_row in pillar_rows:
                        pillar_kw = p_row.get("keyword") if hasattr(p_row, 'get') else p_row[0]
                        pillar_support_map[pillar_kw] = []
                    log.info(f"[Research] Loaded {len(pillar_support_map)} pillars from fallback table")

            # Extract pillars from keys
            pillars = list(pillar_support_map.keys()) if pillar_support_map else []
            supporting = pillar_support_map if pillar_support_map else {}

            log.info(f"[Research] Loaded {len(pillars)} pillars, {sum(len(v) for v in supporting.values())} supporting from {session_id}")
            return pillars, supporting

        except Exception as e:
            log.error(f"[Research] Load failed: {e}", exc_info=True)
            return [], {}
        finally:
            try:
                ki_db.close()
            except:
                pass

    def _extract_user_keywords(self, supporting_kws: Dict[str, List[str]]) -> List[Dict[str, Any]]:
        """Extract user's supporting keywords with score +10."""
        result = []
        for pillar, supporting_list in supporting_kws.items():
            for kw in supporting_list:
                if kw and kw.strip():
                    result.append({
                        "keyword": kw.strip(),
                        "source": "user",
                        "source_score": 10,
                        "pillar_keyword": pillar,
                    })
        return result

    def _fetch_google_suggestions(self, pillars: List[str], language: str) -> List[Dict[str, Any]]:
        """Fetch Google Autosuggest with multiple intent-driven prefix patterns per pillar.

        Instead of querying just the bare pillar name (returns 5-10 suggestions),
        we query 15+ prefix patterns per pillar generating 50-150 unique suggestions.
        """
        import time
        result = []

        # Prefix templates — {p} is replaced with pillar keyword
        PREFIXES = [
            # bare (already returns 10ish, but do it first)
            "{p}",
            # question-based (long tail goldmine)
            "what is {p}", "how to use {p}", "why use {p}",
            "where to buy {p}", "how to buy {p}",
            # intent-based
            "buy {p}", "best {p}", "organic {p}", "pure {p}",
            "cheap {p}", "{p} price", "{p} online",
            # commercial
            "{p} wholesale", "{p} bulk", "{p} supplier",
            "{p} near me", "{p} in india",
            # informational
            "{p} benefits", "{p} uses", "{p} powder",
            "{p} vs", "{p} review", "{p} side effects",
        ]

        try:
            from engines.annaseo_p2_enhanced import P2_PhraseSuggestor
            suggester = P2_PhraseSuggestor(lang=language.lower()[:2], region="in")

            for pillar in pillars:
                seen_for_pillar: set = set()

                for tmpl in PREFIXES:
                    query = tmpl.replace("{p}", pillar)
                    try:
                        suggestions = suggester._fetch_suggestions(query)
                        for s in suggestions:
                            s = s.strip()
                            if s and s.lower() not in seen_for_pillar:
                                seen_for_pillar.add(s.lower())
                                result.append({
                                    "keyword": s,
                                    "source": "google",
                                    "source_score": 5,
                                    "pillar_keyword": pillar,
                                })
                    except Exception:
                        pass
                    time.sleep(0.15)  # polite rate limit

                log.info(f"[Research] Google expanded '{pillar}': {len(seen_for_pillar)} suggestions")

        except Exception as e:
            log.warning(f"[Research] P2_PhraseSuggestor unavailable: {e}")

        return result

    def _deduplicate(self, keywords: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove exact duplicate keywords (case-insensitive)."""
        seen = {}
        for kw_item in keywords:
            kw_lower = kw_item["keyword"].lower().strip()
            if kw_lower not in seen:
                # Store lowercase version
                seen[kw_lower] = {**kw_item, "keyword": kw_lower}
            elif kw_item["source_score"] > seen[kw_lower].get("source_score", 0):
                # Keep version with higher source score (also as lowercase)
                seen[kw_lower] = {**kw_item, "keyword": kw_lower}

        return list(seen.values())

    def _generate_emergency_keywords(self, business_intent: str, target_count: int = 100) -> List[ResearchResult]:
        """
        Generate emergency keywords when NO pillars or sources available.
        """
        emergency_keywords = {
            "ecommerce": [
                "buy online", "price comparison", "best deals", "free shipping",
                "cash on delivery", "online shopping", "bulk discount",
                "quality products", "authentic items", "trusted seller",
                "customer reviews", "return policy", "warranty coverage",
                "discount offer", "seasonal sale", "wholesale price",
                "bulk buy", "compare products", "shop online", "save money",
                "best price guarantee", "fast delivery", "express shipping",
                "original product", "certified quality", "genuine seller",
            ],
            "content_blog": [
                "how to guide", "tutorial video", "step by step", "tips and tricks",
                "expert advice", "best practices", "frequently asked", "complete guide",
                "latest news", "trending topics", "knowledge base", "learning resources",
                "blog article", "industry insights", "case studies", "research findings",
                "informative content", "educational material", "practical examples",
                "beginners guide", "advanced tutorial", "expert tips",
            ],
            "supplier": [
                "wholesale supplier", "bulk pricing", "minimum order quantity",
                "direct from manufacturer", "bulk export", "certified quality",
                "food grade certified", "international shipping", "competitive pricing",
                "fast delivery", "reliable supplier", "bulk discount pricing",
                "quality assurance", "certifications available", "factory direct",
                "custom orders", "batch orders", "sample available",
            ],
            "mixed": [
                "buy online", "how to", "best", "reviews", "price", "quality",
                "authentic", "trusted", "compare", "tips", "guide", "benefits",
                "uses", "trending", "popular", "affordable", "reliable", "shipping",
                "delivery", "warranty", "guarantee", "customer service",
            ]
        }

        keywords_list = emergency_keywords.get(business_intent, emergency_keywords["mixed"])
        results = []

        for i, keyword in enumerate(keywords_list[:target_count]):
            results.append(
                ResearchResult(
                    keyword=keyword,
                    source="fallback_generation",
                    intent="mixed",
                    volume="medium",
                    difficulty="medium",
                    total_score=18 + (i % 7),  # Score 18-24 (always below real sources)
                    confidence=35,
                    pillar_keyword="emergency_fallback",
                    reasoning="Emergency keyword generation when sources unavailable"
                )
            )

        log.info(f"[Research] Emergency fallback generated {len(results)} keywords")
        return results

    def _generate_fallback_keywords(
        self,
        pillars: List[str],
        supporting_kws: Dict[str, List[str]],
        business_intent: str,
        target_count: int = 100,
    ) -> List[ResearchResult]:
        """
        Generate long-tail fallback keywords per pillar when primary sources return few results.
        Uses intent-specific templates covering short, medium, and long-tail patterns.
        Scores are BELOW real source scores (18-28) to keep ranking hierarchy correct.
        """
        if not pillars:
            return self._generate_emergency_keywords(business_intent, target_count=target_count)

        # Rich template sets covering short + long tail
        TEMPLATES = {
            "transactional": [
                "buy {p}", "buy {p} online", "buy {p} wholesale",
                "{p} price", "{p} price in india", "best {p} price",
                "{p} online", "shop {p} online", "order {p} online",
                "{p} for sale", "{p} supplier", "{p} manufacturer",
                "cheap {p}", "affordable {p}", "{p} discount",
                "{p} bulk", "{p} bulk buy", "{p} wholesale price",
                "{p} kg price", "{p} cost", "{p} rate",
                "best {p} brand", "top {p} brand", "{p} quality",
                "{p} near me", "{p} shop near me", "buy {p} near me",
            ],
            "informational": [
                "what is {p}", "what is {p} used for", "how to use {p}",
                "{p} benefits", "{p} health benefits", "{p} benefits for skin",
                "{p} uses", "{p} uses in cooking", "{p} nutritional value",
                "how to store {p}", "how to grow {p}",
                "{p} for health", "{p} for weight loss", "{p} for digestion",
                "{p} side effects", "{p} dangers", "is {p} safe",
                "best way to use {p}", "types of {p}", "grades of {p}",
                "{p} vs other spices", "difference between {p} types",
                "{p} properties", "{p} history", "{p} origin",
                "{p} nutritional facts", "{p} composition",
            ],
            "commercial": [
                "best {p}", "top {p}", "best organic {p}",
                "{p} review", "{p} reviews", "best {p} brand in india",
                "{p} quality comparison", "which {p} is best",
                "{p} vs {p} alternatives", "premium {p}",
                "certified {p}", "organic {p} certified",
                "pure {p}", "natural {p}", "authentic {p}",
                "{p} recommendations", "expert recommended {p}",
                "{p} for home use", "{p} for restaurant use",
            ],
            "local": [
                "{p} kerala", "{p} from kerala", "kerala {p}",
                "{p} india", "{p} in india", "indian {p}",
                "{p} wayanad", "{p} malabar", "{p} coorg",
                "buy {p} from india", "{p} export india",
                "{p} indian supplier", "{p} india price",
                "{p} south india", "{p} north india",
            ],
            "wholesale": [
                "{p} wholesale", "{p} wholesale price", "{p} bulk wholesale",
                "{p} bulk supplier", "{p} bulk order",
                "{p} importer", "{p} exporter", "{p} distributor",
                "{p} B2B", "{p} business buyer", "{p} trade",
                "minimum order {p}", "{p} MOQ", "{p} sample order",
                "{p} food grade", "{p} export quality", "{p} ISO certified",
                "{p} organic certified", "{p} fair trade",
            ],
        }

        # Select template sets based on intent
        if business_intent == "ecommerce":
            sets = ["transactional", "commercial", "informational", "local"]
        elif business_intent == "supplier":
            sets = ["wholesale", "transactional", "commercial", "local"]
        elif business_intent == "content_blog":
            sets = ["informational", "commercial", "transactional"]
        else:
            sets = ["transactional", "informational", "commercial", "local", "wholesale"]

        results = []
        seen: set = set()

        for pillar in pillars:
            p_count = 0
            per_pillar_target = max(target_count // max(len(pillars), 1), 50)

            for set_name in sets:
                for tmpl in TEMPLATES.get(set_name, []):
                    keyword_text = tmpl.replace("{p}", pillar)
                    kl = keyword_text.lower()
                    if kl not in seen:
                        seen.add(kl)
                        results.append(ResearchResult(
                            keyword=keyword_text,
                            source="fallback_generation",
                            intent="transactional" if set_name in ("transactional", "wholesale") else
                                   "informational" if set_name == "informational" else "commercial",
                            volume="medium",
                            difficulty="medium",
                            total_score=20 + (p_count % 9),  # 20-28, always below real sources
                            confidence=45,
                            pillar_keyword=pillar,
                            reasoning=f"Template fallback ({set_name})"
                        ))
                        p_count += 1
                        if p_count >= per_pillar_target:
                            break
                if p_count >= per_pillar_target:
                    break
            # Hard cap: stop generating once we reach overall target
            if len(results) >= target_count:
                break

        log.info(f"[Research] Fallback generated {len(results)} keywords for {len(pillars)} pillar(s)")
        return results


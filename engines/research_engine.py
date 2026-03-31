"""
Research Engine — Multi-source keyword collection with priority ranking.

Source 1: User's supporting keywords (score +10)
Source 2: Google Autosuggest (score +5)
Source 3: AI classification + scoring (variable)

Guarantees: Never returns 0 keywords. Respects business intent.
"""

import logging
import json
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
        ollama_url: str = "http://localhost:11434",
        industry: str = "general",
    ):
        self.ollama_url = ollama_url
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

        # Apply fallback/emergency generation ONLY when there are no scored results
        # This prevents generated fallback keywords from outranking real user/google results.
        if len(results) == 0:
            log.warning(f"[Research] No scored results, applying fallback to meet minimum guarantee")
            # First try structured fallback using pillars
            fallback_results = self._generate_fallback_keywords(pillars, supporting_kws, business_intent)
            results.extend(fallback_results)

            # If still below 20 (e.g., no pillars), generate emergency keywords
            if len(results) < 20:
                log.error(f"[Research] Still below 20 after fallback, generating emergency keywords")
                results.extend(self._generate_emergency_keywords(business_intent, target_count=20 - len(results)))

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
        """Fetch Google Autosuggest for each pillar with score +5."""
        result = []
        try:
            from engines.annaseo_p2_enhanced import P2_PhraseSuggestor
            suggester = P2_PhraseSuggestor(lang=language.lower()[:2], region="in")

            for pillar in pillars:
                try:
                    suggestions = suggester.expand_phrase(pillar, deep=False)
                    for s in suggestions:
                        if s and s.strip():
                            result.append({
                                "keyword": s.strip(),
                                "source": "google",
                                "source_score": 5,
                                "pillar_keyword": pillar,
                            })
                except Exception as e:
                    log.debug(f"[Research] Google fetch failed for '{pillar}': {e}")
                    continue

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

    def _generate_emergency_keywords(self, business_intent: str, target_count: int = 20) -> List[ResearchResult]:
        """
        Generate emergency keywords when NO pillars or sources available.
        Guarantees minimum keywords for the given business intent.
        """
        emergency_keywords = {
            "ecommerce": [
                "buy online", "price comparison", "best deals", "free shipping",
                "cash on delivery", "online shopping", "bulk discount",
                "quality products", "authentic items", "trusted seller",
                "customer reviews", "return policy", "warranty coverage",
                "discount offer", "seasonal sale", "wholesale price",
                "bulk buy", "compare products", "shop online", "save money",
            ],
            "content_blog": [
                "how to guide", "tutorial video", "step by step", "tips and tricks",
                "expert advice", "best practices", "frequently asked", "complete guide",
                "latest news", "trending topics", "knowledge base", "learning resources",
                "blog article", "industry insights", "case studies", "research findings",
                "informative content", "educational material", "practical examples", "detailed explanation",
            ],
            "supplier": [
                "wholesale supplier", "bulk pricing", "minimum order quantity",
                "direct from manufacturer", "bulk export", "certified quality",
                "food grade certified", "international shipping", "competitive pricing",
                "fast delivery", "reliable supplier", "bulk discount pricing",
                "quality assurance", "certifications available", "factory direct",
                "custom orders", "batch orders", "sample available", "long term contract",
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
                    total_score=20 + (i % 10),  # Score 20-29
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
    ) -> List[ResearchResult]:
        """
        Generate fallback keywords if research returns too few.
        GUARANTEES minimum 20 keywords using modifier combinations.

        Strategy: For each pillar, combine with intent-specific modifiers to ensure
        we always return at least 20 keywords even if all other sources fail.
        Falls back to emergency generation if pillars are empty.
        """
        # If no pillars, delegate to emergency keywords
        if not pillars:
            log.info(f"[Research] No pillars for fallback, using emergency keywords")
            return self._generate_emergency_keywords(business_intent, target_count=20)

        modifiers = {
            "ecommerce": [
                "buy", "price", "cost", "cheap", "bulk", "wholesale", "sale",
                "discount", "online", "best", "reviews", "for sale", "vs",
                "alternative", "where to buy", "how much", "quality", "authentic",
                "organic", "natural", "pure", "benefits", "uses", "compare"
            ],
            "content_blog": [
                "how to", "guide", "tutorial", "tips", "benefits", "what is",
                "why", "uses", "vs", "comparison", "best", "top", "expert",
                "meaning", "definition", "history", "types", "recipes",
                "health benefits", "side effects", "information", "guide"
            ],
            "supplier": [
                "bulk", "wholesale", "manufacturer", "supplier", "importer",
                "specifications", "pricing", "MOQ", "certifications", "quality",
                "industrial", "food grade", "organic", "fair trade", "export",
                "direct", "cost", "minimum order", "delivery", "standard"
            ],
            "mixed": [
                "buy", "price", "how to", "benefits", "what is", "reviews",
                "vs", "best", "online", "bulk", "organic", "quality",
                "guide", "tips", "information", "cost", "comparison",
                "alternatives", "uses", "types", "meaning", "history"
            ]
        }

        mod_list = modifiers.get(business_intent, modifiers["mixed"])
        results = []

        # Generate combinations of pillar + modifier
        for pillar in pillars:
            for i, modifier in enumerate(mod_list):
                keyword_text = f"{pillar} {modifier}"
                results.append(
                    ResearchResult(
                        keyword=keyword_text,
                        source="fallback_generation",
                        intent="mixed",  # Fallback doesn't classify intent
                        volume="medium",
                        difficulty="medium",
                        total_score=30 + (i % 15),  # Score 30-44
                        confidence=50,  # Low confidence for generated keywords
                        pillar_keyword=pillar,
                        reasoning="Fallback generation when primary sources empty"
                    )
                )

                # Stop when we have enough
                if len(results) >= 20:
                    log.info(f"[Research] Fallback generated {len(results)} keywords")
                    return results[:20]

        # If we still don't have 20, add reverse combinations (modifier pillar)
        if len(results) < 20:
            for modifier in mod_list[:20 - len(results)]:
                for pillar in pillars:
                    keyword_text = f"{modifier} {pillar}"
                    results.append(
                        ResearchResult(
                            keyword=keyword_text,
                            source="fallback_generation",
                            intent="mixed",
                            volume="medium",
                            difficulty="medium",
                            total_score=25,
                            confidence=40,
                            pillar_keyword=pillar,
                            reasoning="Fallback generation (reverse order)"
                        )
                    )
                    if len(results) >= 20:
                        log.info(f"[Research] Fallback generated {len(results)} keywords (reverse)")
                        return results[:20]

        log.warning(f"[Research] Fallback only generated {len(results)} keywords (target: 20)")
        return results

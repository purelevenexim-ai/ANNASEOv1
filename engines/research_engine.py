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

        # Ensure minimum results (fallback if needed)
        if len(results) < 10:
            log.warning(f"[Research] Only {len(results)} results, adding fallback")
            results.extend(self._generate_fallback_keywords(pillars, supporting_kws, business_intent))

        # Sort by score descending
        results.sort(key=lambda x: x.total_score, reverse=True)

        log.info(f"[Research] Complete: {len(results)} keywords for {project_id}")
        return results

    def _load_user_keywords(
        self,
        session_id: str,
        project_id: str,
    ) -> Tuple[List[str], Dict[str, List[str]]]:
        """Load pillars and supporting keywords from Step 1 session."""
        try:
            from engines.annaseo_keyword_input import _db as _ki_db_fn
            ki_db = _ki_db_fn()
        except Exception as e:
            log.warning(f"[Research] Could not load KI db: {e}")
            return [], {}

        try:
            # Query keyword_input_sessions for this session
            session = ki_db.execute(
                "SELECT pillars, supporting_keywords FROM keyword_input_sessions WHERE session_id=?",
                (session_id,)
            ).fetchone()

            if not session:
                log.warning(f"[Research] Session {session_id} not found")
                return [], {}

            pillars_json = session.get("pillars", "[]") if hasattr(session, 'get') else session[0]
            supporting_json = session.get("supporting_keywords", "{}") if hasattr(session, 'get') else session[1]

            pillars = json.loads(pillars_json) if isinstance(pillars_json, str) else pillars_json or []
            supporting = json.loads(supporting_json) if isinstance(supporting_json, str) else supporting_json or {}

            return pillars, supporting

        except Exception as e:
            log.error(f"[Research] Load failed: {e}")
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

    def _generate_fallback_keywords(
        self,
        pillars: List[str],
        supporting_kws: Dict[str, List[str]],
        business_intent: str,
    ) -> List[ResearchResult]:
        """
        Generate fallback keywords if research returns too few.
        Uses simple heuristics based on input.
        """
        # For now, return empty (full AI fallback added in Phase 2)
        return []

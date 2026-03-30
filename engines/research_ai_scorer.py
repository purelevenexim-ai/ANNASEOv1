"""
Research AI Scorer — Batch DeepSeek scoring for keywords.

Single call to Ollama DeepSeek to classify and score multiple keywords.
Respects business intent context.
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

log = logging.getLogger("annaseo.research_ai_scorer")


@dataclass
class KeywordScore:
    """Scored keyword with metadata."""
    keyword: str
    intent: str  # "transactional" | "informational" | "comparison" | "commercial" | "local"
    volume: str  # "very_low" | "low" | "medium" | "high"
    difficulty: str  # "easy" | "medium" | "hard"
    source: str  # "user" | "google" | "ai_generated"
    source_score: int  # 10 (user) or 5 (google) or 0 (ai)
    ai_score: int  # 0-10
    total_score: int  # source_score + ai_score
    confidence: int  # 0-100
    relevant_to_intent: bool
    pillar_keyword: str
    reasoning: str


class AIScorer:
    """Score keywords using Ollama DeepSeek in a single batch call."""

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        model: str = "deepseek-r1:7b",
        industry: str = "general",
    ):
        self.ollama_url = ollama_url
        self.model = model
        self.industry = industry

    def score_keywords_batch(
        self,
        keywords: List[Dict[str, Any]],
        pillars: List[str],
        supporting_keywords: Dict[str, List[str]],
        business_intent: str,
    ) -> List[KeywordScore]:
        """
        Score multiple keywords in a single Ollama call.

        Args:
            keywords: List of {"keyword": str, "source": str, "source_score": int}
            pillars: Primary keywords ["clove", "cardamom"]
            supporting_keywords: {"clove": ["pure powder", ...], ...}
            business_intent: "ecommerce" | "content_blog" | "supplier" | "mixed"

        Returns:
            List[KeywordScore] sorted by total_score descending
        """
        if not keywords:
            return []

        # Build prompt
        prompt = self._build_scoring_prompt(
            keywords, pillars, supporting_keywords, business_intent
        )

        # Call Ollama
        response = self._call_ollama(prompt)

        # Parse response
        scores = self._parse_ollama_response(response, keywords)

        # Sort by total_score
        scores.sort(key=lambda x: x.total_score, reverse=True)

        return scores

    def _build_scoring_prompt(
        self,
        keywords: List[Dict[str, Any]],
        pillars: List[str],
        supporting_keywords: Dict[str, List[str]],
        business_intent: str,
    ) -> str:
        """Build the DeepSeek prompt."""
        # Format supporting keywords nicely
        supporting_str = json.dumps(supporting_keywords, indent=2)

        # Format keywords list
        keywords_list = "\n".join(
            f"  {i+1}. {kw['keyword']} (source: {kw['source']})"
            for i, kw in enumerate(keywords[:50])  # Max 50 for performance
        )

        prompt = f"""You are a keyword intelligence expert for {self.industry} industry.

CONTEXT:
- Primary keywords (pillars): {', '.join(pillars)}
- User-provided supporting keywords:
{supporting_str}
- Business intent: {business_intent}
- Industry: {self.industry}

KEYWORDS TO CLASSIFY:
{keywords_list}

For EACH keyword, determine:
1. Intent type: transactional (buying/selling) | informational (learning) | comparison (vs other) | commercial (premium/brand) | local (geography)
2. Is it relevant to the business intent '{business_intent}'? (true/false)
3. Volume estimate: very_low (0-100/mo) | low (100-1k/mo) | medium (1k-10k/mo) | high (10k+/mo)
4. Difficulty: easy | medium | hard (how competitive)
5. AI Score: 0-10 (0=irrelevant, 10=perfect match for intent)
6. Confidence: 0-100

RESPOND WITH ONLY VALID JSON ARRAY, NO OTHER TEXT:

[
  {{
    "keyword": "...",
    "intent": "...",
    "relevant_to_intent": true/false,
    "volume": "...",
    "difficulty": "...",
    "ai_score": <0-10>,
    "confidence": <0-100>,
    "reasoning": "..."
  }},
  ...
]"""
        return prompt

    def _call_ollama(self, prompt: str) -> str:
        """Call Ollama API."""
        try:
            import requests
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.3,
                },
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except Exception as e:
            log.error(f"[AIScorer] Ollama call failed: {e}")
            raise

    def _parse_ollama_response(
        self,
        response: str,
        keywords: List[Dict[str, Any]],
    ) -> List[KeywordScore]:
        """Parse JSON response from DeepSeek."""
        try:
            # Try to extract JSON from response (may have preamble)
            json_start = response.find("[")
            json_end = response.rfind("]") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                scores_data = json.loads(json_str)
            else:
                log.warning(f"[AIScorer] Could not find JSON in response")
                return []

            # Build lookup of source keywords
            source_lookup = {kw["keyword"]: kw for kw in keywords}

            # Convert to KeywordScore objects
            result = []
            for item in scores_data:
                kw_text = item.get("keyword", "").strip()
                source_kw = source_lookup.get(kw_text)
                if not source_kw:
                    continue

                ai_score = int(item.get("ai_score", 0))
                source_score = source_kw.get("source_score", 0)
                total_score = source_score + ai_score

                score_obj = KeywordScore(
                    keyword=kw_text,
                    intent=item.get("intent", "informational"),
                    volume=item.get("volume", "medium"),
                    difficulty=item.get("difficulty", "medium"),
                    source=source_kw.get("source", "unknown"),
                    source_score=source_score,
                    ai_score=ai_score,
                    total_score=total_score,
                    confidence=int(item.get("confidence", 0)),
                    relevant_to_intent=item.get("relevant_to_intent", False),
                    pillar_keyword=source_kw.get("pillar_keyword", ""),
                    reasoning=item.get("reasoning", ""),
                )
                result.append(score_obj)

            return result

        except json.JSONDecodeError as e:
            log.error(f"[AIScorer] JSON parse failed: {e}\nResponse: {response[:200]}")
            return []
        except Exception as e:
            log.error(f"[AIScorer] Parse failed: {e}")
            return []

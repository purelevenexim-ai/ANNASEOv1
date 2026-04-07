"""
Research AI Scorer — Batch DeepSeek scoring for keywords.

Single call to Ollama DeepSeek to classify and score multiple keywords.
Respects business intent context.
"""

import os
import re
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

    _instances: dict = {}  # keyed by (ollama_url, model)

    @classmethod
    def get_instance(cls, ollama_url: str = "http://172.235.16.165:11434",
                     model: str = "deepseek-r1:7b",
                     industry: str = "general") -> "AIScorer":
        """Singleton per (url, model) pair — avoids re-creating per request."""
        key = (ollama_url, model)
        inst = cls._instances.get(key)
        if inst is None:
            inst = cls(ollama_url=ollama_url, model=model, industry=industry)
            cls._instances[key] = inst
        inst.industry = industry  # update industry per call (lightweight)
        return inst

    def __init__(
        self,
        ollama_url: str = "http://172.235.16.165:11434",
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
        Score multiple keywords in batches via Ollama.

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

        all_scores = []
        batch_size = 5  # Small batches — Ollama on CPU needs short prompts to stay under timeout
        total = len(keywords)

        for batch_start in range(0, total, batch_size):
            batch = keywords[batch_start:batch_start + batch_size]
            try:
                prompt = self._build_scoring_prompt(
                    batch, pillars, supporting_keywords, business_intent
                )
                response = self._call_ollama(prompt)
                scores = self._parse_ollama_response(response, batch)
                all_scores.extend(scores)
            except Exception as e:
                log.warning(f"[AIScorer] Batch {batch_start//batch_size+1} failed: {e}")
                continue  # skip failed batch, continue with next

        all_scores.sort(key=lambda x: x.total_score, reverse=True)
        return all_scores

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
            for i, kw in enumerate(keywords[:5])
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
        """Call Ollama API with retry."""
        import requests
        import time
        last_err = None
        for attempt in range(2):
            try:
                response = requests.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "temperature": 0.3,
                        "options": {"num_ctx": 2048, "num_predict": 1500},
                    },
                    timeout=120,  # Increased from 45s to 120s — batch processing can be slow
                )
                response.raise_for_status()
                data = response.json()
                result = data.get("response", "")
                if not result:
                    log.warning(f"[AIScorer] Empty response from Ollama")
                return result
            except Exception as e:
                last_err = e
                log.warning(f"[AIScorer] Ollama attempt {attempt+1} failed: {str(e)[:100]}")
                if attempt == 0:
                    time.sleep(2)
        log.error(f"[AIScorer] Ollama failed after 2 attempts: {last_err}")
        raise last_err

    def _parse_ollama_response(
        self,
        response: str,
        keywords: List[Dict[str, Any]],
    ) -> List[KeywordScore]:
        """Parse JSON response from Ollama."""
        try:
            # Strip DeepSeek/Qwen reasoning blocks before JSON extraction
            response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
            response = re.sub(r'```json\n?|```', '', response).strip()  # Remove markdown code fences

            # Try to extract JSON from response (may have preamble)
            json_start = response.find("[")
            json_end = response.rfind("]") + 1
            if json_start < 0 or json_end <= json_start:
                log.warning(f"[AIScorer] No JSON array found in response. Response length: {len(response)}")
                log.debug(f"[AIScorer] Response: {response[:300]}")
                return []
                
            json_str = response[json_start:json_end]
            try:
                scores_data = json.loads(json_str)
            except json.JSONDecodeError as je:
                log.error(f"[AIScorer] JSON decode failed at position {je.pos}: {str(je)[:100]}")
                log.debug(f"[AIScorer] JSON string: {json_str[:300]}")
                return []

            if not isinstance(scores_data, list):
                log.warning(f"[AIScorer] Expected JSON array, got {type(scores_data).__name__}")
                return []

            # Build lookup of source keywords
            source_lookup = {kw["keyword"]: kw for kw in keywords}

            # Convert to KeywordScore objects
            result = []
            for idx, item in enumerate(scores_data):
                try:
                    kw_text = item.get("keyword", "").strip()
                    if not kw_text:
                        log.debug(f"[AIScorer] Item {idx} has no keyword")
                        continue
                        
                    source_kw = source_lookup.get(kw_text)
                    if not source_kw:
                        log.debug(f"[AIScorer] Keyword '{kw_text}' not in source batch")
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
                except Exception as item_err:
                    log.debug(f"[AIScorer] Error parsing item {idx}: {item_err}")
                    continue

            log.info(f"[AIScorer] Parsed {len(result)}/{len(scores_data)} items from Ollama response")
            return result

        except Exception as e:
            log.error(f"[AIScorer] Parse failed: {e}")
            return []

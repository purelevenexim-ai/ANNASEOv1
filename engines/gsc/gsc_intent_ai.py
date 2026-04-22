"""
GSC Phase 2 — AI Intent Classifier
LLM-based batch intent classification with caching.

Replaces rule-based signals with AI classification for uncertain keywords.
Rule-based shortcuts kept for obvious cases (cost saving).

Uses existing AIRouter (Groq → Ollama → Gemini fallback chain).
"""
import json
import re
import logging
from typing import Optional

from core.ai_config import AIRouter
from . import gsc_db
from .gsc_processor import classify_intent as rule_classify, _PURCHASE, _WHOLESALE

log = logging.getLogger(__name__)

# Keywords that are obvious — skip LLM
_OBVIOUS_PURCHASE = _PURCHASE | _WHOLESALE
_OBVIOUS_INFO = {"benefits", "uses", "how to", "what is", "guide", "recipe", "history"}

INTENT_CATEGORIES = ["informational", "commercial", "transactional", "navigational"]


def _is_obvious(keyword: str) -> Optional[str]:
    """Return intent if keyword is obvious, else None (needs LLM)."""
    kw = keyword.lower()
    words = set(re.findall(r"\b\w+\b", kw))
    if _OBVIOUS_PURCHASE & words:
        return "transactional"
    if _OBVIOUS_INFO & words:
        return "informational"
    return None


def _batch_classify_llm(keywords: list[str]) -> list[dict]:
    """
    Classify a batch of keywords via LLM.
    Returns list of {keyword, intent, confidence}.
    """
    kw_list = "\n".join(f"- {kw}" for kw in keywords)
    prompt = f"""Classify the search intent for each keyword below.

Categories:
- informational (learning, how-to, benefits)
- commercial (comparing, reviewing, best options)
- transactional (buying, ordering, pricing)
- navigational (finding a specific site/page)

Keywords:
{kw_list}

Return ONLY a JSON array, no explanation:
[{{"keyword": "...", "intent": "...", "confidence": 0.0-1.0}}]"""

    text = AIRouter.call(prompt, system="You are an expert SEO intent classifier. Respond only with valid JSON.", temperature=0.1)
    if not text:
        return [{"keyword": kw, "intent": "informational", "confidence": 0.3} for kw in keywords]

    try:
        # Strip markdown fences
        cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`")
        data = json.loads(cleaned)
        if isinstance(data, list):
            # Validate and normalize
            result = []
            kw_set = set(keywords)
            used = set()
            for item in data:
                kw = item.get("keyword", "")
                intent = item.get("intent", "informational").lower().strip()
                conf = float(item.get("confidence", 0.5))
                if intent not in INTENT_CATEGORIES:
                    intent = "informational"
                conf = max(0.0, min(1.0, conf))
                if kw in kw_set and kw not in used:
                    result.append({"keyword": kw, "intent": intent, "confidence": conf})
                    used.add(kw)
            # Fill missing
            for kw in keywords:
                if kw not in used:
                    result.append({"keyword": kw, "intent": "informational", "confidence": 0.3})
            return result
        return [{"keyword": kw, "intent": "informational", "confidence": 0.3} for kw in keywords]
    except (json.JSONDecodeError, ValueError) as e:
        log.warning(f"[GSC Intent] LLM parse failed: {e}")
        return [{"keyword": kw, "intent": "informational", "confidence": 0.3} for kw in keywords]


def classify_intents_batch(project_id: str, batch_size: int = 50) -> dict:
    """
    Classify intents for all processed keywords using LLM.
    Obvious keywords are pre-filtered (skip LLM).
    Results stored in intent_confidence column.

    Returns: {classified: N, obvious: N, llm_batches: N}
    """
    processed = gsc_db.get_processed_keywords(project_id)
    if not processed:
        return {"classified": 0, "obvious": 0, "llm_batches": 0}

    obvious_results = []
    uncertain = []

    for kw in processed:
        keyword = kw["keyword"]
        obvious_intent = _is_obvious(keyword)
        if obvious_intent:
            obvious_results.append({
                "keyword": keyword,
                "intent": obvious_intent if obvious_intent == "transactional" else kw.get("intent", "informational"),
                "confidence": 0.95,
            })
        else:
            uncertain.append(keyword)

    log.info(f"[GSC Intent] {len(obvious_results)} obvious, {len(uncertain)} need LLM")

    # LLM batch classification
    llm_results = []
    llm_batches = 0
    for i in range(0, len(uncertain), batch_size):
        batch = uncertain[i:i + batch_size]
        batch_result = _batch_classify_llm(batch)
        llm_results.extend(batch_result)
        llm_batches += 1

    # Merge and update DB
    all_results = obvious_results + llm_results
    updates = []
    for r in all_results:
        # Map transactional → purchase for our internal system
        internal_intent = r["intent"]
        if internal_intent == "transactional":
            internal_intent = "purchase"
        updates.append({
            "keyword": r["keyword"],
            "intent_confidence": r["confidence"],
        })

    if updates:
        gsc_db.update_processed_keywords_phase2(project_id, updates)

    log.info(f"[GSC Intent] Classified {len(all_results)} keywords ({llm_batches} LLM batches)")
    return {
        "classified": len(all_results),
        "obvious": len(obvious_results),
        "llm_batches": llm_batches,
    }

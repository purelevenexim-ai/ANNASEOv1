"""
================================================================================
BUSINESS POTENTIAL SCORER
================================================================================
Implements Ahrefs' Business Potential scoring framework (0-3 scale) combined
with the P7++ scoring engine for comprehensive keyword prioritization.

Ahrefs Scale:
  3 = "Your product is an irreplaceable solution for the problem"
  2 = "Your product helps quite a bit, but it's not essential"
  1 = "Your product can only be tangentially mentioned"
  0 = "There's no way to mention your product"

Extended scoring (P7++ integration):
  final_score = (
    BusinessFit       * 0.25 +
    IntentValue       * 0.20 +
    RankingFeasibility * 0.20 +
    TrafficPotential  * 0.15 +
    CompetitorGap     * 0.10 +
    ContentEase       * 0.10
  )

Reference: Ahrefs "Business Potential" framework
           Strategy Intelligence P7++ scoring engine
================================================================================
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger("annaseo.business_potential_scorer")


# ─────────────────────────────────────────────────────────────────────────────
# BUSINESS POTENTIAL SCORE (Ahrefs 0-3)
# ─────────────────────────────────────────────────────────────────────────────

def score_business_potential(
    keyword: str,
    products: List[str],
    topics: List[str],
    business_type: str = "",
    usp: str = "",
) -> Dict[str, Any]:
    """
    Score keyword business potential on Ahrefs' 0-3 scale.

    3: Product is irreplaceable solution → "best [your product]", "[your product] vs X"
    2: Product helps but not essential → "how to [topic your product helps with]"
    1: Product mentioned tangentially → broad industry topics
    0: No way to mention product → completely unrelated
    """
    kw = keyword.lower()
    score = 0.0
    signals = []

    # Direct product mention check
    product_match = False
    for product in products:
        p = product.lower()
        if p in kw or kw in p:
            product_match = True
            signals.append(f"direct_product_match:{product}")
            break
        # Check product words
        product_words = set(p.split())
        kw_words = set(kw.split())
        overlap = product_words & kw_words
        if len(overlap) >= 2 or (len(overlap) == 1 and len(product_words) <= 2):
            product_match = True
            signals.append(f"product_word_overlap:{product}")
            break

    # Topic alignment check
    topic_match = False
    for topic in topics:
        t = topic.lower()
        if t in kw or kw in t:
            topic_match = True
            signals.append(f"topic_match:{topic}")
            break
        topic_words = set(t.split())
        kw_words = set(kw.split())
        if topic_words & kw_words:
            topic_match = True
            signals.append(f"topic_word_match:{topic}")
            break

    # Intent signals
    buying_signals = ["buy", "price", "cost", "purchase", "order", "discount", "deal", "shop"]
    comparison_signals = ["best", "top", "vs", "versus", "review", "alternative", "compare"]
    problem_signals = ["how to", "fix", "solve", "help", "improve", "solution"]

    has_buying = any(s in kw for s in buying_signals)
    has_comparison = any(s in kw for s in comparison_signals)
    has_problem = any(s in kw for s in problem_signals)

    if has_buying:
        signals.append("buying_intent")
    if has_comparison:
        signals.append("comparison_intent")
    if has_problem:
        signals.append("problem_seeking")

    # Scoring logic (Ahrefs scale)
    if product_match and (has_buying or has_comparison):
        score = 3.0  # Irreplaceable solution
    elif product_match and has_problem:
        score = 2.5
    elif product_match:
        score = 2.0  # Product helps
    elif topic_match and (has_buying or has_comparison):
        score = 2.0
    elif topic_match and has_problem:
        score = 1.5
    elif topic_match:
        score = 1.0  # Tangential mention
    elif has_buying or has_comparison:
        score = 0.5  # Might be able to mention
    else:
        score = 0.0  # No connection

    label = _potential_label(score)

    return {
        "score": score,
        "label": label,
        "signals": signals,
        "recommendation": _get_recommendation(score),
    }


def _potential_label(score: float) -> str:
    if score >= 2.5:
        return "irreplaceable_solution"
    elif score >= 1.5:
        return "product_helps"
    elif score >= 0.5:
        return "tangential_mention"
    else:
        return "no_connection"


def _get_recommendation(score: float) -> str:
    if score >= 2.5:
        return "HIGH PRIORITY: Create dedicated content. Product is the natural solution."
    elif score >= 1.5:
        return "MEDIUM PRIORITY: Include product naturally within helpful content."
    elif score >= 0.5:
        return "LOW PRIORITY: Brief product mention possible. Focus on brand awareness."
    else:
        return "SKIP: No natural product connection. Consider for brand awareness only."


# ─────────────────────────────────────────────────────────────────────────────
# P7++ COMPREHENSIVE KEYWORD SCORER
# ─────────────────────────────────────────────────────────────────────────────

def score_keyword_p7(
    keyword: str,
    business_context: Dict[str, Any],
    serp_data: Dict[str, Any] = None,
    competitor_data: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    P7++ scoring: comprehensive keyword prioritization.

    Formula:
      final_score = (
        BusinessFit       * 0.25 +
        IntentValue       * 0.20 +
        RankingFeasibility * 0.20 +
        TrafficPotential  * 0.15 +
        CompetitorGap     * 0.10 +
        ContentEase       * 0.10
      )
    """
    serp_data = serp_data or {}
    competitor_data = competitor_data or {}

    # 1. Business Fit (0-1)
    bp = score_business_potential(
        keyword,
        business_context.get("products", []),
        business_context.get("topics", []),
        business_context.get("business_type", ""),
        business_context.get("usp", ""),
    )
    business_fit = bp["score"] / 3.0  # Normalize 0-3 → 0-1

    # 2. Intent Value (0-1)
    intent_value = _score_intent_value(keyword)

    # 3. Ranking Feasibility (0-1)
    feasibility = serp_data.get("feasibility", 0.5)

    # 4. Traffic Potential (0-1)
    traffic_potential = _estimate_traffic_potential(keyword, serp_data)

    # 5. Competitor Gap (0-1)
    competitor_gap = _score_competitor_gap(keyword, competitor_data)

    # 6. Content Ease (0-1)
    content_ease = _score_content_ease(keyword)

    # Weighted final score
    final_score = round(
        business_fit * 0.25 +
        intent_value * 0.20 +
        feasibility * 0.20 +
        traffic_potential * 0.15 +
        competitor_gap * 0.10 +
        content_ease * 0.10,
        3,
    )

    # Priority classification
    if final_score >= 0.7:
        priority = "critical"
    elif final_score >= 0.5:
        priority = "high"
    elif final_score >= 0.3:
        priority = "medium"
    else:
        priority = "low"

    return {
        "keyword": keyword,
        "score": final_score,
        "priority": priority,
        "business_potential": bp,
        "subscores": {
            "business_fit": round(business_fit, 3),
            "intent_value": round(intent_value, 3),
            "ranking_feasibility": round(feasibility, 3),
            "traffic_potential": round(traffic_potential, 3),
            "competitor_gap": round(competitor_gap, 3),
            "content_ease": round(content_ease, 3),
        },
    }


def _score_intent_value(keyword: str) -> float:
    """Score keyword intent for business value (transactional > commercial > informational)."""
    kw = keyword.lower()
    transactional = ["buy", "order", "purchase", "pricing", "cost", "deal", "discount", "shop", "subscribe"]
    commercial = ["best", "top", "review", "vs", "comparison", "alternative", "recommend"]
    informational = ["how to", "what is", "guide", "tutorial", "learn", "tips"]

    if any(t in kw for t in transactional):
        return 0.95
    elif any(c in kw for c in commercial):
        return 0.75
    elif any(i in kw for i in informational):
        return 0.45
    return 0.5


def _estimate_traffic_potential(keyword: str, serp_data: Dict) -> float:
    """Estimate traffic potential (0-1) from SERP data or keyword length."""
    # If we have SERP feasibility, use it as proxy
    if serp_data.get("search_volume"):
        vol = serp_data["search_volume"]
        if vol > 10000:
            return 0.9
        elif vol > 1000:
            return 0.7
        elif vol > 100:
            return 0.5
        else:
            return 0.3

    # Heuristic: shorter keywords tend to have more volume
    word_count = len(keyword.split())
    if word_count <= 2:
        return 0.7
    elif word_count <= 4:
        return 0.5
    else:
        return 0.35


def _score_competitor_gap(keyword: str, competitor_data: Dict) -> float:
    """Score how much of a gap exists (high = competitors weak here)."""
    gap_keywords = competitor_data.get("gap_keywords", [])
    if keyword.lower() in [g.lower() for g in gap_keywords]:
        return 0.8  # Found in gap analysis = good opportunity
    top_keywords = competitor_data.get("top_keywords", [])
    if keyword.lower() in [t.lower() for t in top_keywords]:
        return 0.3  # Competitors already strong here
    return 0.5  # Unknown


def _score_content_ease(keyword: str) -> float:
    """Estimate how easy it is to create great content for this keyword."""
    kw = keyword.lower()
    # Easier: how-to, tutorials, lists (can leverage existing knowledge)
    easy_signals = ["how to", "guide", "tips", "tutorial", "list", "best"]
    # Harder: topics requiring original data, tools, complex analysis
    hard_signals = ["statistics", "study", "research", "data", "calculator", "tool"]

    if any(s in kw for s in easy_signals):
        return 0.8
    elif any(s in kw for s in hard_signals):
        return 0.3
    return 0.6


# ─────────────────────────────────────────────────────────────────────────────
# BATCH SCORING
# ─────────────────────────────────────────────────────────────────────────────

def score_keywords_batch(
    keywords: List[str],
    business_context: Dict[str, Any],
    serp_cache: Dict[str, Dict] = None,
    competitor_data: Dict[str, Any] = None,
) -> List[Dict[str, Any]]:
    """Score a batch of keywords and return sorted by score."""
    serp_cache = serp_cache or {}
    competitor_data = competitor_data or {}

    scored = []
    for kw in keywords:
        serp_data = serp_cache.get(kw, {})
        result = score_keyword_p7(kw, business_context, serp_data, competitor_data)
        scored.append(result)

    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored

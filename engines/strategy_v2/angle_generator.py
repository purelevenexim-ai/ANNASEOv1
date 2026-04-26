"""
Strategy V2 — Angle Generator.
Uses AI to produce 5-8 differentiated angles per keyword.
"""
import logging
from typing import Optional

from .prompts import (
    SYSTEM_ROLE, BANNED_TERMS,
    build_angle_prompt, build_angle_prompt_gemini,
)
from .ai_caller import call_ai_json

log = logging.getLogger("strategy_v2.angle_generator")


def _is_valid_angle(angle_text: str) -> bool:
    """Reject angles containing banned template patterns."""
    lower = angle_text.lower()
    return not any(banned in lower for banned in BANNED_TERMS)


def generate_angles(keyword: str, intent: str,
                    kw2_context: Optional[dict] = None) -> list:
    """
    Generate 5-8 differentiated angles for a keyword.

    Returns list of dicts: [{angle, type, perspective, why_it_ranks, target_reader}]
    Falls back to deterministic angles if AI fails.
    """
    user_prompt = build_angle_prompt(keyword, intent, kw2_context)
    gemini_prompt = build_angle_prompt_gemini(keyword, intent, kw2_context)

    try:
        result = call_ai_json(SYSTEM_ROLE, user_prompt, gemini_prompt, temperature=0.5)
    except Exception as e:
        log.error(f"[angle_generator] AI call failed for '{keyword}': {e}")
        return _fallback_angles(keyword, intent)

    # Normalise: result may be a list directly or dict with nested list
    angles = result if isinstance(result, list) else result.get("angles", [])

    # Filter banned patterns
    clean = [a for a in angles if _is_valid_angle(a.get("angle", ""))]

    if len(clean) < 3:
        log.warning(f"[angle_generator] Only {len(clean)} valid angles — using fallback")
        return _fallback_angles(keyword, intent)

    # Enforce max 8
    return clean[:8]


def _fallback_angles(keyword: str, intent: str) -> list:
    """Deterministic fallback angles when AI is unavailable."""
    kw = keyword.lower()
    return [
        {
            "angle": f"Why Most People Choose the Wrong {keyword.title()} (And How to Avoid It)",
            "type": "mistake",
            "perspective": f"Common selection errors with {kw}",
            "why_it_ranks": "Answers pre-purchase anxiety missing in current SERPs",
            "target_reader": "First-time buyers researching options",
        },
        {
            "angle": f"The Hidden Factors That Affect {keyword.title()} Quality (That Nobody Talks About)",
            "type": "hidden_truth",
            "perspective": f"Industry insider knowledge about {kw}",
            "why_it_ranks": "Gaps in transparency-focused content",
            "target_reader": "Discerning buyers wanting real information",
        },
        {
            "angle": f"How to Actually Evaluate {keyword.title()} — A Decision Framework",
            "type": "decision_framework",
            "perspective": f"Structured criteria for choosing {kw}",
            "why_it_ranks": "Decision-support content typically outranks passive info pieces",
            "target_reader": "Research-stage buyers comparing options",
        },
        {
            "angle": f"What Sellers Don't Tell You About {keyword.title()}",
            "type": "hidden_truth",
            "perspective": f"Unfiltered truth about {kw} market",
            "why_it_ranks": "Consumer skepticism creates demand for candid content",
            "target_reader": "Educated buyers who research before buying",
        },
        {
            "angle": f"The Real Difference Between Premium and Budget {keyword.title()}",
            "type": "comparison",
            "perspective": f"Objective breakdown of {kw} price tiers",
            "why_it_ranks": "Price-quality comparison content captures commercial intent",
            "target_reader": "Value-conscious buyers evaluating spend",
        },
    ]

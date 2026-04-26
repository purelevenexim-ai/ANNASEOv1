"""
Strategy V2 — Blueprint Generator.
Converts a single angle into a full structured content blueprint.
"""
import logging
from typing import Optional

from .prompts import (
    SYSTEM_ROLE, BANNED_TERMS,
    build_blueprint_prompt, build_blueprint_prompt_gemini,
)
from .ai_caller import call_ai_json

log = logging.getLogger("strategy_v2.blueprint_generator")


def generate_blueprint(keyword: str, angle_obj: dict, intent: str,
                       kw2_context: Optional[dict] = None) -> dict:
    """
    Generate a full content blueprint for one angle.

    Returns blueprint dict or raises ValueError on irrecoverable failure.
    """
    user_prompt = build_blueprint_prompt(keyword, angle_obj, intent, kw2_context)
    gemini_prompt = build_blueprint_prompt_gemini(keyword, angle_obj, intent, kw2_context)

    try:
        bp = call_ai_json(SYSTEM_ROLE, user_prompt, gemini_prompt, temperature=0.4)
    except Exception as e:
        log.error(f"[blueprint_generator] AI failed for angle '{angle_obj.get('angle','?')}': {e}")
        return _fallback_blueprint(keyword, angle_obj)

    # Ensure required fields exist
    bp.setdefault("keyword", keyword)
    bp.setdefault("angle_type", angle_obj.get("type", "informational"))
    if not isinstance(bp.get("sections"), list):
        bp["sections"] = []
    if not bp.get("hook"):
        bp["hook"] = {"text": f"Most people don't know the full truth about {keyword}.", "goal": "curiosity"}
    if not bp.get("story"):
        bp["story"] = {"placement": "after_S2", "scenario": "", "instruction": "short relatable scenario"}
    if not bp.get("cta"):
        bp["cta"] = {"type": "soft", "text": "Make an informed decision.", "goal": "guide_decision"}

    return bp


def _fallback_blueprint(keyword: str, angle_obj: dict) -> dict:
    """Deterministic fallback when all AI providers fail."""
    angle = angle_obj.get("angle", keyword)
    angle_type = angle_obj.get("type", "informational")
    return {
        "keyword": keyword,
        "title": angle,
        "angle_type": angle_type,
        "hook": {
            "text": f"Most people assume {keyword} is straightforward — it's not.",
            "goal": "challenge_belief",
        },
        "sections": [
            {"id": "S1", "heading": "The Common Misconception", "purpose": "engage",
             "instruction": "State what most people believe and why it's incomplete",
             "must_include": ["specific belief"], "avoid": ["vague generalities"]},
            {"id": "S2", "heading": "What Actually Matters", "purpose": "educate",
             "instruction": "Explain the real factors most guides skip",
             "must_include": ["fact", "example"], "avoid": ["repetition of S1"]},
            {"id": "S3", "heading": "Breaking It Down — A Side-by-Side Look", "purpose": "compare",
             "instruction": "Compare the main options or approaches clearly",
             "must_include": ["comparison table or list"], "avoid": ["vague 'it depends'"]},
            {"id": "S4", "heading": "Common Mistakes and How to Avoid Them", "purpose": "trust",
             "instruction": "List 3-4 mistakes buyers/users make with actionable fixes",
             "must_include": ["mistake → fix format"], "avoid": ["obvious tips"]},
            {"id": "S5", "heading": "How to Make the Right Decision", "purpose": "decision",
             "instruction": "Give a simple framework or checklist for choosing correctly",
             "must_include": ["decision criteria"], "avoid": ["promotional language"]},
        ],
        "story": {
            "placement": "after_S2",
            "scenario": f"A buyer spent weeks researching {keyword} only to discover the most important factor wasn't in any guide they'd read.",
            "instruction": "Keep it vivid and relatable",
        },
        "cta": {
            "type": "soft",
            "text": "Armed with this framework, you're now better equipped to choose confidently.",
            "goal": "guide_decision",
        },
    }

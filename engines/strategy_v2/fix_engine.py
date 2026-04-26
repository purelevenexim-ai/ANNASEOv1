"""
Strategy V2 — Fix Engine.
Targeted blueprint repair when QA score < 75.
Max 1 repair attempt per blueprint to avoid infinite loops.
"""
import logging

from .prompts import SYSTEM_ROLE, build_fix_prompt, build_blueprint_prompt_gemini
from .ai_caller import call_ai_json
from .blueprint_normalizer import normalize_blueprint

log = logging.getLogger("strategy_v2.fix_engine")


def fix_blueprint(bp: dict, qa_report: dict) -> dict:
    """
    Attempt a targeted repair of a low-scoring blueprint.

    - Only called once per blueprint (pipeline.py enforces this)
    - Returns the improved blueprint (or original if fix fails)
    """
    gaps = qa_report.get("gaps", [])
    if not gaps:
        return bp

    user_prompt = build_fix_prompt(bp, gaps)
    # Gemini fallback reuses the same prompt (no system separation needed for fix)
    gemini_prompt = SYSTEM_ROLE + "\n\n" + user_prompt

    try:
        fixed = call_ai_json(SYSTEM_ROLE, user_prompt, gemini_prompt, temperature=0.3)
    except Exception as e:
        log.warning(f"[fix_engine] Fix AI call failed: {e}. Returning original.")
        return bp

    if not isinstance(fixed, dict) or not fixed.get("title"):
        log.warning("[fix_engine] Fix returned invalid structure. Returning original.")
        return bp

    # Preserve original keyword + angle_type if AI dropped them
    fixed.setdefault("keyword", bp.get("keyword", ""))
    fixed.setdefault("angle_type", bp.get("angle_type", ""))

    return normalize_blueprint(fixed)

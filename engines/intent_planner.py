"""
Phase D: Structured Intent Planner.

Wraps the existing `services.seo_brief_generator.classify_intent` and
`detect_content_format` helpers to produce a richer "intent plan" that the
draft prompt can use as hard constraints (angle, must-include sections,
forbidden phrases). This stops the LLM from drifting into generic
informational openers when the keyword is clearly transactional, etc.

The output is intentionally a flat dict so it can be JSON-embedded directly
into prompts without further processing. Failures are silent (caller falls
back to the legacy behaviour).
"""
from __future__ import annotations

import logging
from typing import Dict, List

log = logging.getLogger("annaseo.intent_planner")


# ─────────────────────────────────────────────────────────────────────────────
# Article-type playbook: per-intent required sections, voice, and CTAs.
# Hardcoded by design — these are editorial decisions, not LLM guesses.
# ─────────────────────────────────────────────────────────────────────────────

_PLAYBOOK = {
    "transactional": {
        "article_type": "buyer_guide",
        "voice": "decision-oriented, comparison-driven",
        "must_include": [
            "comparison table or checklist of options",
            "how-to-choose criteria with measurable thresholds",
            "soft CTA after the buying-criteria section",
            "clear FAQ block targeting purchase objections",
        ],
        "cta_strategy": "early soft CTA after intro; strong CTA after buying guide; final urgent CTA",
        "intro_hook_pattern": "open with a buyer pain point or quality risk, NOT a generic definition",
    },
    "commercial": {
        "article_type": "comparison_review",
        "voice": "analytical, opinionated but evidence-backed",
        "must_include": [
            "side-by-side comparison of 2+ options",
            "pros and cons per option",
            "explicit verdict / recommendation per use case",
            "FAQ targeting differentiation questions",
        ],
        "cta_strategy": "implicit CTA via verdict; final CTA only",
        "intro_hook_pattern": "open with the decision the reader is actually trying to make",
    },
    "informational": {
        "article_type": "educational_guide",
        "voice": "explanatory, beginner-friendly progressing to expert",
        "must_include": [
            "definition within first 150 words",
            "what / why / how angles each given a section",
            "concrete example or scenario per major concept",
            "FAQ targeting clarification questions",
        ],
        "cta_strategy": "no hard CTAs; soft 'learn more' links only",
        "intro_hook_pattern": "open with a concrete scenario or counterintuitive fact",
    },
    "navigational": {
        "article_type": "brand_or_resource_page",
        "voice": "direct, factual, brand-led",
        "must_include": [
            "clear identification of brand/resource being sought",
            "key facts box near the top",
            "links to canonical resources",
        ],
        "cta_strategy": "direct CTA to the canonical destination",
        "intro_hook_pattern": "lead with the canonical answer in the first sentence",
    },
}


# Phrases that ANY intent should avoid — kept short because the draft prompt
# already has a comprehensive forbidden list. This is the per-intent overlay.
_AVOID_BY_INTENT = {
    "transactional": [
        "Are you looking to",
        "In today's world",
        "Turmeric is widely used",  # generic informational opener masquerading as buyer intent
        "Let us explore",
    ],
    "commercial": [
        "Both options have their merits",
        "It ultimately depends on you",
        "There is no one-size-fits-all answer",
    ],
    "informational": [
        "In this article we will explore",
        "Without further ado",
        "Let us dive into",
    ],
    "navigational": [
        "Discover the world of",
        "Welcome to our complete guide",
    ],
}


def build_intent_plan(
    keyword: str,
    primary_intent: str = "",
    research_themes: List[str] | None = None,
    content_format: str = "",
) -> Dict:
    """Return a structured intent plan for use as a draft-prompt constraint.

    All inputs are optional — sane defaults apply. Always returns a dict.
    """
    intent = (primary_intent or "informational").lower().strip()
    if intent not in _PLAYBOOK:
        intent = "informational"
    play = _PLAYBOOK[intent]

    # Derive an article angle from the strongest research theme + intent.
    themes = [t for t in (research_themes or []) if t][:3]
    if themes:
        angle = (
            f"{play['voice']} {play['article_type'].replace('_', ' ')} for '{keyword}', "
            f"anchored on: {', '.join(themes)}"
        )
    else:
        angle = (
            f"{play['voice']} {play['article_type'].replace('_', ' ')} for '{keyword}'"
        )

    plan = {
        "primary_intent": intent,
        "article_type": play["article_type"],
        "voice": play["voice"],
        "angle": angle,
        "must_include": list(play["must_include"]),
        "avoid_phrases": list(_AVOID_BY_INTENT.get(intent, [])),
        "cta_strategy": play["cta_strategy"],
        "intro_hook_pattern": play["intro_hook_pattern"],
    }
    if content_format:
        plan["content_format"] = content_format
    return plan


def render_intent_block(plan: Dict) -> str:
    """Render a compact prompt block from the intent plan for inclusion in
    draft / intro prompts. Empty string if the plan is missing or invalid.
    """
    if not plan or not isinstance(plan, dict):
        return ""
    must = plan.get("must_include") or []
    avoid = plan.get("avoid_phrases") or []
    parts = [
        "── INTENT PLAN (HARD CONSTRAINTS) ──",
        f"Article type: {plan.get('article_type', 'guide')} | Voice: {plan.get('voice', '')}",
        f"Angle: {plan.get('angle', '')}",
        f"Intro hook: {plan.get('intro_hook_pattern', '')}",
        f"CTA strategy: {plan.get('cta_strategy', '')}",
    ]
    if must:
        parts.append("MUST include in this article:")
        for item in must:
            parts.append(f"  - {item}")
    if avoid:
        parts.append("AVOID these openers/phrases (intent-specific):")
        for item in avoid:
            parts.append(f"  - {item}")
    return "\n".join(parts)

"""
audit/validators/consistency.py
================================
Logical consistency checks across AI outputs.

Detects:
- Conflicting signals (luxury vs cheap, bulk vs retail-only)
- Pillars appearing in negative_scope
- Commercial keywords scored as informational
- Strategy referencing non-existent pillars
"""
from __future__ import annotations
import re
from typing import Any


# Pairs of conflicting positioning terms that should never co-occur in the same
# strategy/profile output. Format: (term_a, term_b, description)
_CONFLICT_PAIRS = [
    ("luxury", "cheap", "luxury vs cheap positioning"),
    ("premium", "budget", "premium vs budget conflict"),
    ("wholesale", "retail only", "channel conflict"),
    ("b2b", "consumer only", "audience conflict"),
    ("farm direct", "imported", "sourcing conflict"),
    ("organic certified", "chemical", "quality claim conflict"),
]


def check_positioning_conflicts(text: str) -> list[str]:
    """
    Scan a text blob for contradictory positioning signals.
    Returns list of identified conflicts.
    """
    text_lower = text.lower()
    issues: list[str] = []
    for a, b, desc in _CONFLICT_PAIRS:
        if a in text_lower and b in text_lower:
            issues.append(f"Positioning conflict detected: {desc} ('{a}' + '{b}')")
    return issues


def check_pillar_negative_scope_conflict(pillars: list[str], negative_scope: list[str]) -> list[str]:
    """
    A pillar must never appear in negative_scope — that would filter all its keywords.
    """
    issues: list[str] = []
    neg_lower = {n.lower() for n in negative_scope}
    for pillar in pillars:
        if pillar.lower() in neg_lower:
            issues.append(f"Pillar '{pillar}' appears in negative_scope — will zero out all its keywords")
    return issues


def check_keyword_intent_score_alignment(keywords: list[dict]) -> list[str]:
    """
    High buyer_readiness (> 0.7) keywords should not be classified as purely informational.
    Low relevance (< 0.3) keywords should not be tagged as 'purchase'.
    """
    issues: list[str] = []
    for kw in keywords:
        word = kw.get("keyword", "?")
        intent = kw.get("intent", "")
        br = float(kw.get("buyer_readiness", 0))
        rel = float(kw.get("ai_relevance", 0))

        if intent == "informational" and br > 0.7:
            issues.append(
                f"'{word}': classified informational but buyer_readiness={br:.2f} — likely mis-labelled"
            )
        if intent == "purchase" and rel < 0.3:
            issues.append(
                f"'{word}': classified purchase but ai_relevance={rel:.2f} — likely noise"
            )
    return issues[:20]  # cap output


def check_strategy_pillar_references(strategy: dict, pillars: list[str]) -> list[str]:
    """
    Every focus_pillar in the weekly_plan must be one of the known pillars.
    """
    issues: list[str] = []
    pillar_set = {p.lower() for p in pillars}
    for week in strategy.get("weekly_plan", []):
        fp = week.get("focus_pillar", "")
        if fp and fp.lower() not in pillar_set:
            issues.append(f"Week {week.get('week','?')}: focus_pillar '{fp}' not in pillars {pillars}")
    return issues


def check_entity_hallucination(entities: list[str], source_text: str) -> list[str]:
    """
    Each extracted entity must have SOME overlap with the source text.
    Entities that share no tokens with source_text are likely hallucinated.
    """
    issues: list[str] = []
    words = set(re.findall(r"\w+", source_text.lower()))
    for entity in entities:
        entity_words = set(re.findall(r"\w+", entity.lower()))
        if not entity_words & words:
            issues.append(f"Possible hallucination: entity '{entity}' has no overlap with source text")
    return issues[:10]


def run_all_consistency_checks(
    profile: dict,
    keywords: list[dict],
    strategy: dict,
    source_text: str = "",
) -> dict[str, Any]:
    """
    Run ALL consistency checks and return a consolidated report.
    """
    # Defensive: tolerate non-dict profile/strategy (garbage input chaos tests)
    if not isinstance(profile, dict):
        profile = {}
    if not isinstance(strategy, dict):
        strategy = {}
    if not isinstance(keywords, list):
        keywords = []

    profile_text = str(profile) + " " + str(strategy)
    pillars = profile.get("pillars", [])
    negative_scope = profile.get("negative_scope", [])

    position_issues = check_positioning_conflicts(profile_text)
    pillar_neg_issues = check_pillar_negative_scope_conflict(pillars, negative_scope)
    intent_issues = check_keyword_intent_score_alignment(keywords)
    strategy_issues = check_strategy_pillar_references(strategy, pillars)

    hallucination_issues: list[str] = []
    if source_text:
        entities = profile.get("product_catalog", []) + pillars
        hallucination_issues = check_entity_hallucination(entities, source_text)

    all_issues = (
        position_issues + pillar_neg_issues + intent_issues
        + strategy_issues + hallucination_issues
    )

    return {
        "valid": len(all_issues) == 0,
        "positioning_conflicts": position_issues,
        "pillar_negative_scope_conflicts": pillar_neg_issues,
        "intent_score_mismatches": intent_issues,
        "strategy_pillar_reference_errors": strategy_issues,
        "hallucination_candidates": hallucination_issues,
        "total_issues": len(all_issues),
    }

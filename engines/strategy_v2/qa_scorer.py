"""
Strategy V2 — QA Scoring Engine.

4 signal families (no AI — pure rule-based):
  SEO Strategy (30%)    — structural + keyword signals
  AEO (20%)             — AI search / snippet signals
  Conversion (30%)      — funnel + buyer-psychology signals
  Depth (20%)           — differentiation + uniqueness signals

Overall threshold: 75 = pass, <75 = trigger fix_engine.
"""
from .prompts import BANNED_TERMS

# ── Weights ────────────────────────────────────────────────────────────────
WEIGHTS = {"seo": 0.30, "aeo": 0.20, "conversion": 0.30, "depth": 0.20}

# ── Decision-framework signal words ───────────────────────────────────────
_DECISION_WORDS = [
    "how to choose", "decision", "framework", "evaluate", "criteria",
    "checklist", "steps to", "what to look for", "guide your",
]
_FAQ_WORDS = ["faq", "frequently asked", "question", "q:", "q&a"]
_STORY_WORDS = ["story", "scenario", "imagine", "picture this", "real life", "for example"]
_COMPARISON_WORDS = ["vs", "versus", "compare", "difference", "side by side", "alternative"]
_BUYER_WORDS = [
    "buyer", "purchase", "buy", "choose", "select", "invest", "worth",
    "mistake", "avoid", "overpay", "regret",
]


def _contains_any(text: str, words: list) -> bool:
    lower = text.lower()
    return any(w in lower for w in words)


def _all_sections_text(bp: dict) -> str:
    sections = bp.get("sections", [])
    parts = [bp.get("title", ""), bp.get("hook", {}).get("text", "")]
    for s in sections:
        parts.append(s.get("heading", ""))
        parts.append(s.get("instruction", ""))
        parts.extend(s.get("must_include", []))
    story = bp.get("story", {})
    if isinstance(story, dict):
        parts.append(story.get("scenario", ""))
    cta = bp.get("cta", {})
    if isinstance(cta, dict):
        parts.append(cta.get("text", ""))
    return " ".join(parts)


def score_blueprint(bp: dict) -> dict:
    """
    Score a content blueprint across 4 signal families.

    Returns:
      {
        "seo": int, "aeo": int, "conversion": int, "depth": int,
        "overall": int,
        "gaps": list[str],
        "fixes": list[str],
        "signals": dict,
      }
    """
    title = bp.get("title", "")
    sections = bp.get("sections", [])
    hook = bp.get("hook", {})
    story = bp.get("story", {})
    cta = bp.get("cta", {})
    angle_type = bp.get("angle_type", "")
    all_text = _all_sections_text(bp)
    section_headings = [s.get("heading", "") for s in sections]
    section_purposes = [s.get("purpose", "") for s in sections]

    signals = {}
    gaps = []
    fixes = []

    # ── SEO Signals ────────────────────────────────────────────────────────
    signals["title_present"] = bool(title and len(title.split()) >= 6)
    signals["title_not_generic"] = not any(b in title.lower() for b in BANNED_TERMS)
    signals["sections_count_ok"] = 4 <= len(sections) <= 8
    signals["no_duplicate_sections"] = (
        len(set(h.lower() for h in section_headings)) == len(section_headings)
    )
    signals["has_keyword_context"] = bool(bp.get("keyword", ""))
    signals["intent_aligned"] = bool(angle_type)

    seo_count = sum(signals[k] for k in ["title_present", "title_not_generic",
                                          "sections_count_ok", "no_duplicate_sections",
                                          "has_keyword_context", "intent_aligned"])
    seo_score = round(seo_count / 6 * 100)

    if not signals["title_not_generic"]:
        gaps.append("Title uses a banned template pattern")
        fixes.append("Revise title to reflect a specific angle or insight")
    if not signals["sections_count_ok"]:
        gaps.append(f"Section count ({len(sections)}) is outside 4–8 range")
        fixes.append("Add or merge sections to reach 5–7 distinct sections")

    # ── AEO Signals ────────────────────────────────────────────────────────
    signals["has_hook"] = bool(hook and (hook.get("text") or hook.get("goal")))
    signals["faq_present"] = (
        _contains_any(" ".join(section_headings), _FAQ_WORDS) or
        any(p in ("engage", "educate") for p in section_purposes) and len(sections) >= 5
    )
    signals["definition_or_quick_answer"] = any(
        p in ("educate", "engage") for p in section_purposes
    )
    signals["snippet_extractable"] = (
        signals["has_hook"] and signals["sections_count_ok"]
    )
    signals["entity_richness"] = len(sections) >= 5  # proxy for coverage depth

    aeo_count = sum(signals[k] for k in ["has_hook", "faq_present",
                                          "definition_or_quick_answer",
                                          "snippet_extractable", "entity_richness"])
    aeo_score = round(aeo_count / 5 * 100)

    if not signals["has_hook"]:
        gaps.append("No compelling hook defined")
        fixes.append("Add a hook that challenges a belief or reveals a gap")

    # ── Conversion Signals ─────────────────────────────────────────────────
    signals["has_cta"] = bool(cta and (cta.get("text") or cta.get("goal")))
    signals["has_decision_section"] = _contains_any(
        " ".join(section_headings), _DECISION_WORDS
    )
    signals["buyer_psychology_present"] = _contains_any(all_text, _BUYER_WORDS)
    signals["comparison_layer"] = (
        angle_type in ("comparison", "decision_framework") or
        _contains_any(all_text, _COMPARISON_WORDS)
    )
    signals["cta_soft"] = (
        isinstance(cta, dict) and cta.get("type") == "soft"
    )

    conv_count = sum(signals[k] for k in ["has_cta", "has_decision_section",
                                           "buyer_psychology_present",
                                           "comparison_layer", "cta_soft"])
    conversion_score = round(conv_count / 5 * 100)

    if not signals["has_cta"]:
        gaps.append("Missing CTA")
        fixes.append("Add a soft trust-based CTA guiding the reader to a decision")
    if not signals["has_decision_section"]:
        gaps.append("No decision framework section")
        fixes.append("Add a section like 'How to Choose' or 'Decision Checklist'")

    # ── Depth Signals ──────────────────────────────────────────────────────
    signals["has_story"] = bool(
        isinstance(story, dict) and story.get("scenario") or
        _contains_any(all_text, _STORY_WORDS)
    )
    signals["unique_angle"] = angle_type in (
        "contrarian", "hidden_truth", "mistake", "comparison", "decision_framework"
    )
    signals["non_template_structure"] = signals["title_not_generic"]
    signals["avoids_generic_sections"] = not _contains_any(
        " ".join(section_headings),
        ["introduction", "conclusion", "overview", "summary", "about"],
    )

    depth_count = sum(signals[k] for k in ["has_story", "unique_angle",
                                             "non_template_structure",
                                             "avoids_generic_sections"])
    depth_score = round(depth_count / 4 * 100)

    if not signals["has_story"]:
        gaps.append("Missing story/scenario element")
        fixes.append("Add a short relatable real-world scenario early in the blueprint")
    if not signals["avoids_generic_sections"]:
        gaps.append("Section headings include generic labels (Introduction/Conclusion/Overview)")
        fixes.append("Replace generic headings with specific, purpose-driven titles")

    # ── Overall ────────────────────────────────────────────────────────────
    overall = round(
        seo_score * WEIGHTS["seo"] +
        aeo_score * WEIGHTS["aeo"] +
        conversion_score * WEIGHTS["conversion"] +
        depth_score * WEIGHTS["depth"]
    )

    return {
        "seo": seo_score,
        "aeo": aeo_score,
        "conversion": conversion_score,
        "depth": depth_score,
        "overall": overall,
        "gaps": gaps,
        "fixes": fixes,
        "signals": signals,
    }

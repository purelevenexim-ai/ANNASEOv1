"""
Content Blueprint Planner — Rule-aware pre-generation content plan.

Generates an SEO blueprint that embeds all 53 quality rules as requirements
BEFORE content generation starts. The user reviews and approves the plan,
then the pipeline follows it exactly.
"""

import json
import logging
import re
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# RULE-DERIVED REQUIREMENTS
# ─────────────────────────────────────────────────────────────────────────────

def _build_seo_checklist(page_type: str = "article", word_count: int = 2000) -> Dict:
    """Build SEO element targets derived from the 53 quality rules."""
    # Base targets for articles
    checklist = {
        "keyword_density_min": 1.5,
        "keyword_density_max": 2.5,
        "keyword_in_first_sentence": True,       # G1
        "first_person_phrases_min": 3,            # G2, AI.2
        "entities_per_1000_words": 6,             # G3
        "unique_data_points_min": 5,              # G4
        "lsi_keywords_min": 3,                    # G7
        "question_headings_min": 3,               # G8
        "forbidden_words": [
            "delve", "crucial", "multifaceted", "landscape", "tapestry",
            "nuanced", "robust", "myriad", "paradigm", "foster",
            "holistic", "pivotal", "streamline", "cutting-edge", "plethora",
        ],                                        # G9, P4.33
        "max_ai_transitions": 2,                  # G9
        "intent_signal": True,                    # P1.1
        "title_has_power_word": True,             # P1.4
        "zero_click_elements": True,              # P1.5 (TL;DR, definition, list)
        "pyramid_structure": True,                # P1.6
        "reading_level_target": "8th-10th",       # P1.7
        "cta_required": True,                     # P1.9
        "internal_links_min": 4,                  # P1.10, P9.83
        "external_authority_links_min": 2,        # P2.12
        "wikipedia_links_min": 1,                 # AI.5
        "date_stamps_min": 2,                     # P2.14
        "case_study_min": 1,                      # P2.17
        "h1_count": 1,                            # P3.21
        "h2_min": 6,                              # P3.22
        "h3_min_per_h2": 2,                       # P3.22
        "max_sentences_per_paragraph": 3,         # P3.23
        "ul_lists_min": 2,                        # P3.24
        "ol_lists_min": 1,                        # P3.24
        "toc_required": word_count >= 1000,       # P3.25
        "bold_terms_min": 5,                      # P3.26
        "meta_desc_length": "150-160 chars",      # P3.29
        "sentence_length_variety": True,           # P4.32
        "active_voice_pct_min": 85,               # P4.34
        "no_redundant_phrases": True,             # P4.37
        "comparison_table_min": 1,                # P5.44
        "data_visualization": True,               # P6.56 (table or chart)
        "limitations_acknowledged": True,          # P6.60
        "hook_opening": True,                      # P7.61
        "objections_addressed": True,              # P7.65
        "personal_pronouns": True,                 # P7.66
        "storytelling_elements": True,             # P7.68
        "descriptive_anchor_text": True,           # P8.80
        "long_tail_keywords_min": 2,              # P9.88
        "no_formulaic_headings": True,             # AI.3
        "original_intro": True,                    # AI.6
        "original_conclusion": True,               # AI.7
        "faq_count": 6,
    }

    # Adjust for page type
    if page_type == "homepage":
        checklist.update({
            "h2_min": 4, "h3_min_per_h2": 1, "question_headings_min": 1,
            "faq_count": 4, "case_study_min": 0, "first_person_phrases_min": 2,
            "comparison_table_min": 0, "limitations_acknowledged": False,
        })
    elif page_type == "product":
        checklist.update({
            "h2_min": 5, "question_headings_min": 2, "faq_count": 5,
            "comparison_table_min": 1, "case_study_min": 0,
        })
    elif page_type == "about":
        checklist.update({
            "h2_min": 4, "h3_min_per_h2": 1, "question_headings_min": 0,
            "faq_count": 0, "comparison_table_min": 0, "limitations_acknowledged": False,
            "case_study_min": 0, "external_authority_links_min": 1,
        })
    elif page_type == "landing":
        checklist.update({
            "h2_min": 4, "question_headings_min": 1, "faq_count": 4,
            "cta_required": True, "comparison_table_min": 0,
        })
    elif page_type == "service":
        checklist.update({
            "h2_min": 5, "question_headings_min": 2, "faq_count": 5,
        })

    return checklist


# ─────────────────────────────────────────────────────────────────────────────
# SECTION ELEMENT PLANNER
# ─────────────────────────────────────────────────────────────────────────────

def _plan_section_elements(sections: List[Dict], checklist: Dict) -> List[Dict]:
    """Distribute required elements across sections so nothing is missed."""
    n = len(sections)
    if n == 0:
        return sections

    # Elements to distribute
    tables_remaining = checklist.get("comparison_table_min", 1)
    ul_remaining = checklist.get("ul_lists_min", 2)
    ol_remaining = checklist.get("ol_lists_min", 1)
    int_links_remaining = checklist.get("internal_links_min", 4)
    ext_links_remaining = checklist.get("external_authority_links_min", 2)
    bold_remaining = checklist.get("bold_terms_min", 5)
    case_remaining = checklist.get("case_study_min", 1)
    entity_remaining = checklist.get("entities_per_1000_words", 6)
    first_person_remaining = checklist.get("first_person_phrases_min", 3)
    data_remaining = checklist.get("unique_data_points_min", 5)

    for i, sec in enumerate(sections):
        elements = []

        # Spread elements roughly evenly
        if tables_remaining > 0 and i == n // 2:
            elements.append("comparison_table")
            tables_remaining -= 1

        if ul_remaining > 0 and i % max(1, n // 3) == 0:
            elements.append("bullet_list")
            ul_remaining -= 1

        if ol_remaining > 0 and i == n // 3:
            elements.append("numbered_list")
            ol_remaining -= 1

        if int_links_remaining > 0:
            elements.append("internal_link")
            int_links_remaining -= 1

        if ext_links_remaining > 0 and i in (1, n - 2):
            elements.append("external_authority_link")
            ext_links_remaining -= 1

        if bold_remaining > 0:
            elements.append("bold_key_term")
            bold_remaining -= 1

        if case_remaining > 0 and i == n // 2 + 1:
            elements.append("case_study_example")
            case_remaining -= 1

        if first_person_remaining > 0 and i in (0, n // 2, n - 1):
            elements.append("first_person_experience")
            first_person_remaining -= 1

        if data_remaining > 0:
            elements.append("data_point_or_statistic")
            data_remaining -= 1

        if entity_remaining > 0:
            elements.append("named_entity")
            entity_remaining -= 1

        sec["must_include"] = elements

    return sections


# ─────────────────────────────────────────────────────────────────────────────
# BLUEPRINT GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def generate_blueprint(
    keyword: str,
    page_type: str = "article",
    intent: str = "informational",
    word_count: int = 2000,
    page_inputs: Dict = None,
    supporting_keywords: List[str] = None,
    target_audience: str = "",
    content_type: str = "blog",
    project_name: str = "",
    ai_structure: Dict = None,
) -> Dict:
    """
    Generate a content blueprint with rule-derived requirements.

    If ai_structure is provided (from Step 2), it's enriched with rule requirements.
    Otherwise generates a default structure.

    Returns a blueprint dict the user can review before generation.
    """
    page_inputs = page_inputs or {}
    supporting_keywords = supporting_keywords or []
    checklist = _build_seo_checklist(page_type, word_count)

    # Use AI-generated structure if provided, otherwise build defaults
    if ai_structure and ai_structure.get("h2_sections"):
        sections = ai_structure["h2_sections"]
        h1 = ai_structure.get("h1", keyword.title())
        meta_title = ai_structure.get("meta_title", keyword[:60])
        meta_desc = ai_structure.get("meta_description", "")
        faqs = ai_structure.get("faqs", [])
        intro_plan = ai_structure.get("intro_plan", "")
        conclusion_plan = ai_structure.get("conclusion_plan", "")
    else:
        # Build sensible defaults based on page type
        h1, sections, faqs, meta_title, meta_desc, intro_plan, conclusion_plan = \
            _default_blueprint_structure(keyword, page_type, intent, word_count, page_inputs)

    # Enrich sections with element distribution
    sections = _plan_section_elements(sections, checklist)

    # Calculate total planned words
    total_planned = sum(s.get("word_target", 300) for s in sections)
    intro_words = 100
    faq_words = len(faqs) * 80
    conclusion_words = 100
    total_planned += intro_words + faq_words + conclusion_words

    blueprint = {
        "keyword": keyword,
        "page_type": page_type,
        "intent": intent,
        "target_word_count": word_count,
        "planned_word_count": total_planned,
        "project_name": project_name,
        "target_audience": target_audience,
        "supporting_keywords": supporting_keywords,

        # Structure
        "h1": h1,
        "meta_title": meta_title,
        "meta_description": meta_desc,
        "intro_plan": intro_plan,
        "sections": sections,
        "faqs": faqs,
        "conclusion_plan": conclusion_plan,

        # SEO checklist derived from rules
        "seo_checklist": checklist,

        # Pre-generation quality elements
        "required_elements": {
            "toc": checklist.get("toc_required", True),
            "key_takeaways": True,
            "comparison_table": checklist.get("comparison_table_min", 1) > 0,
            "faq_section": len(faqs) > 0,
            "hook_opening": True,
            "cta_conclusion": checklist.get("cta_required", True),
            "first_person_count": checklist.get("first_person_phrases_min", 3),
            "internal_links": checklist.get("internal_links_min", 4),
            "external_links": checklist.get("external_authority_links_min", 2),
            "tables": checklist.get("comparison_table_min", 1),
            "bullet_lists": checklist.get("ul_lists_min", 2),
            "numbered_lists": checklist.get("ol_lists_min", 1),
            "bold_terms": checklist.get("bold_terms_min", 5),
            "data_points": checklist.get("unique_data_points_min", 5),
            "case_study": checklist.get("case_study_min", 1) > 0,
            "limitations": checklist.get("limitations_acknowledged", True),
            "objections": checklist.get("objections_addressed", True),
            "storytelling": checklist.get("storytelling_elements", True),
        },

        # Formatting rules summary
        "formatting_rules": {
            "max_sentences_per_paragraph": 3,
            "sentence_variety": "Mix short (6-10 words) and long (20-25 words)",
            "active_voice_min_pct": 85,
            "forbidden_words": checklist["forbidden_words"],
            "max_ai_transitions": 2,
            "heading_rules": "No 'Understanding X', 'Benefits of X', 'Overview of X'",
        },
    }

    return blueprint


def _default_blueprint_structure(
    keyword: str,
    page_type: str,
    intent: str,
    word_count: int,
    page_inputs: Dict,
):
    """Generate default sections for blueprint when no AI structure is available."""
    kw = keyword.title()
    kw_l = keyword.lower()
    pi = page_inputs

    if page_type == "homepage":
        biz = pi.get("business_name", kw)
        h1 = f"{biz} — Your Trusted Source for {kw}"
        sections = [
            {"h2": f"Why Choose {biz} for {kw}?", "h3s": ["Our Expertise", "What Sets Us Apart"], "word_target": 200, "content_angle": "Hero + value prop"},
            {"h2": f"Our {kw} Services", "h3s": ["Service 1", "Service 2", "Service 3"], "word_target": 250, "content_angle": "Services overview"},
            {"h2": f"How Does {biz} Work?", "h3s": ["Step 1", "Step 2", "Step 3"], "word_target": 200, "content_angle": "Process"},
            {"h2": f"What Our Customers Say About {kw}", "h3s": ["Testimonial 1", "Results"], "word_target": 200, "content_angle": "Social proof"},
            {"h2": f"Get Started with {kw} Today", "h3s": ["Contact Us", "Free Consultation"], "word_target": 150, "content_angle": "CTA"},
        ]
        faqs = [
            {"q": f"What does {biz} offer?", "a_plan": "Services overview"},
            {"q": f"Why choose {biz} for {kw_l}?", "a_plan": "Differentiators"},
            {"q": f"How do I get started with {kw_l}?", "a_plan": "Next steps"},
            {"q": f"Where is {biz} located?", "a_plan": "Location/coverage"},
        ]
    elif page_type == "product":
        prod = pi.get("product_name", kw)
        h1 = f"{prod} — Features, Benefits & Pricing"
        sections = [
            {"h2": f"What Is {prod}?", "h3s": ["Overview", "Who It's For"], "word_target": 250, "content_angle": "Product intro"},
            {"h2": f"Key Features of {prod}", "h3s": ["Feature 1", "Feature 2", "Feature 3"], "word_target": 300, "content_angle": "Features detail"},
            {"h2": f"{prod} Specifications & Details", "h3s": ["Technical Specs", "Dimensions"], "word_target": 200, "content_angle": "Specs table"},
            {"h2": f"How Does {prod} Compare to Alternatives?", "h3s": ["Comparison", "Our Advantage"], "word_target": 250, "content_angle": "Comparison table"},
            {"h2": f"How to Use {prod} (Step-by-Step)", "h3s": ["Setup", "Best Practices"], "word_target": 200, "content_angle": "Usage guide"},
            {"h2": f"Buy {prod} — Pricing & Availability", "h3s": ["Plans", "Where to Buy"], "word_target": 200, "content_angle": "CTA"},
        ]
        faqs = [
            {"q": f"What is {prod}?", "a_plan": "Definition"},
            {"q": f"How much does {prod} cost?", "a_plan": "Pricing"},
            {"q": f"What are the key features of {prod}?", "a_plan": "Top features"},
            {"q": f"How do I use {prod}?", "a_plan": "Usage steps"},
            {"q": f"Is {prod} worth the price?", "a_plan": "Value assessment"},
        ]
    else:
        # Default article structure
        h1 = f"{kw}: The Complete Guide ({_current_year()})"
        sections = [
            {"h2": f"What Is {kw}? A Complete Overview", "h3s": ["Definition", "Why It Matters", "Key Facts"], "word_target": 350, "content_angle": "Intro + definition"},
            {"h2": f"How Does {kw} Work? (Step-by-Step)", "h3s": ["Step 1", "Step 2", "Step 3"], "word_target": 400, "content_angle": "Process guide"},
            {"h2": f"5 Proven Benefits of {kw}", "h3s": ["Benefit 1", "Benefit 2", "Research Evidence"], "word_target": 400, "content_angle": "Benefits with data"},
            {"h2": f"Which {kw} Type Is Right for You?", "h3s": ["Types Comparison", "How to Choose"], "word_target": 300, "content_angle": "Comparison table"},
            {"h2": f"{kw} vs Alternatives: What Experts Recommend", "h3s": ["Head-to-Head", "Expert Opinion"], "word_target": 300, "content_angle": "Comparison"},
            {"h2": f"How to Buy {kw}: Our Tested Buying Guide", "h3s": ["What to Look For", "Where to Buy", "Red Flags"], "word_target": 350, "content_angle": "Purchase guide"},
            {"h2": f"Expert Tips for {kw} (From Experience)", "h3s": ["Pro Tips", "Common Mistakes", "Advanced Techniques"], "word_target": 300, "content_angle": "Expert insights"},
        ]
        faqs = [
            {"q": f"What is {kw_l}?", "a_plan": "Concise definition"},
            {"q": f"How is {kw_l} used?", "a_plan": "Common uses"},
            {"q": f"What are the benefits of {kw_l}?", "a_plan": "Top benefits"},
            {"q": f"Where can I buy {kw_l}?", "a_plan": "Purchase options"},
            {"q": f"How do I choose the best {kw_l}?", "a_plan": "Selection criteria"},
            {"q": f"Is {kw_l} worth it?", "a_plan": "Value assessment"},
        ]

    meta_title = f"{h1[:55]}"
    meta_desc = f"Discover {kw_l}: expert guide with benefits, comparison, buying tips. Updated {_current_year()}."
    if len(meta_desc) < 150:
        meta_desc += f" Everything you need to know about {kw_l}."
    meta_desc = meta_desc[:160]
    intro_plan = f"Hook with a surprising fact/stat about {kw_l}. State what reader will learn. Include keyword in first sentence."
    conclusion_plan = f"Summarize key points. Include specific CTA. Mention {kw_l} one final time."

    return h1, sections, faqs, meta_title, meta_desc, intro_plan, conclusion_plan


def _current_year() -> str:
    from datetime import datetime
    return str(datetime.now().year)


# ─────────────────────────────────────────────────────────────────────────────
# BLUEPRINT → PROMPT INJECTION
# ─────────────────────────────────────────────────────────────────────────────

def blueprint_to_prompt_block(blueprint: Dict) -> str:
    """Convert a blueprint into a prompt instruction block for the content engine."""
    req = blueprint.get("required_elements", {})
    checklist = blueprint.get("seo_checklist", {})
    sections = blueprint.get("sections", [])
    fmt = blueprint.get("formatting_rules", {})

    lines = [
        "━━━ CONTENT BLUEPRINT (PRE-APPROVED) ━━━",
        f"Follow this blueprint EXACTLY. Every element is required for quality scoring.",
        "",
        f"H1: {blueprint.get('h1', '')}",
        f"Meta Title: {blueprint.get('meta_title', '')}",
        f"Meta Description: {blueprint.get('meta_description', '')}",
        "",
        f"INTRO: {blueprint.get('intro_plan', '')}",
        "  → Start with hook (question, stat, or bold claim)",
        "  → Include keyword in first sentence",
        "  → Add Key Takeaways / TL;DR box",
        "",
        "━━━ SECTIONS ━━━",
    ]

    for i, sec in enumerate(sections, 1):
        elements = sec.get("must_include", [])
        elem_str = ", ".join(elements) if elements else "none"
        h3s = " / ".join(sec.get("h3s", []))
        lines.append(
            f"{i}. H2: {sec['h2']} (~{sec.get('word_target', 300)}w)"
            f"\n   H3s: {h3s}"
            f"\n   Angle: {sec.get('content_angle', '')}"
            f"\n   MUST INCLUDE: {elem_str}"
        )

    faqs = blueprint.get("faqs", [])
    if faqs:
        lines.append("")
        lines.append("━━━ FAQ SECTION ━━━")
        for f in faqs:
            lines.append(f"Q: {f['q']}  →  Answer plan: {f.get('a_plan', '')}")

    lines.append("")
    lines.append(f"CONCLUSION: {blueprint.get('conclusion_plan', '')}")
    lines.append("")

    lines.append("━━━ MANDATORY ELEMENTS CHECKLIST ━━━")
    lines.append(f"☐ TOC: {'Yes' if req.get('toc') else 'No'}")
    lines.append(f"☐ Key Takeaways: Yes")
    lines.append(f"☐ Comparison Table: {req.get('tables', 1)} table(s)")
    lines.append(f"☐ Bullet Lists: {req.get('bullet_lists', 2)} <ul>")
    lines.append(f"☐ Numbered Lists: {req.get('numbered_lists', 1)} <ol>")
    lines.append(f"☐ Bold Terms: {req.get('bold_terms', 5)}+ <strong>")
    lines.append(f"☐ Internal Links: {req.get('internal_links', 4)}+ <a href='/...'>")
    lines.append(f"☐ External Links: {req.get('external_links', 2)}+ authoritative sources")
    lines.append(f"☐ First-Person: {req.get('first_person_count', 3)}+ ('I tested', 'We found', 'In our experience')")
    lines.append(f"☐ Data Points: {req.get('data_points', 5)}+ specific numbers/stats")
    lines.append(f"☐ Case Study: {'Yes' if req.get('case_study') else 'No'}")
    lines.append(f"☐ Limitations: {'Yes' if req.get('limitations') else 'No'}")
    lines.append(f"☐ Objections: {'Yes' if req.get('objections') else 'No'}")
    lines.append(f"☐ Storytelling: {'Yes' if req.get('storytelling') else 'No'}")
    lines.append(f"☐ Hook Opening: Yes")
    lines.append(f"☐ CTA in Conclusion: {'Yes' if req.get('cta_conclusion') else 'No'}")
    lines.append("")
    lines.append("━━━ FORMATTING RULES ━━━")
    lines.append(f"• Max {fmt.get('max_sentences_per_paragraph', 3)} sentences per paragraph")
    lines.append(f"• {fmt.get('sentence_variety', 'Mix short and long sentences')}")
    lines.append(f"• Active voice ≥ {fmt.get('active_voice_min_pct', 85)}%")
    lines.append(f"• FORBIDDEN words: {', '.join(fmt.get('forbidden_words', [])[:10])}")
    lines.append(f"• Max {fmt.get('max_ai_transitions', 2)} transitions (furthermore/moreover)")
    lines.append(f"• {fmt.get('heading_rules', 'No generic headings')}")

    return "\n".join(lines)

"""
================================================================================
SEO BRIEF GENERATOR
================================================================================
Phase 3 — Analyze search intent and create content briefs (Backlinko Step 3).

From Backlinko: "Your content is more likely to fail if you're guessing what
users want instead of analyzing what actually works."

Implements:
- Search intent decoding (content format, depth, SERP features)
- Competitive edge analysis (gaps, freshness, UX, proof)
- SEO brief creation per target keyword
- Content format detection & recommendation

Reference: Backlinko "Analyze Search Intent and Competition"
           Ahrefs "Check search intent"
           Semrush "Create a Content Plan"
================================================================================
"""

from __future__ import annotations
import json
import logging
import re
import sqlite3
from typing import Any, Dict, List, Optional

import requests

log = logging.getLogger("annaseo.seo_brief_generator")


# ─────────────────────────────────────────────────────────────────────────────
# SEARCH INTENT CLASSIFICATION
# ─────────────────────────────────────────────────────────────────────────────

INTENT_SIGNALS = {
    "informational": {
        "prefixes": ["how to", "what is", "why", "guide", "tutorial", "learn", "tips", "ways to"],
        "suffixes": ["explanation", "meaning", "definition", "examples"],
    },
    "commercial": {
        "prefixes": ["best", "top", "review", "comparison", "vs", "cheapest", "affordable"],
        "suffixes": ["reviews", "alternatives", "comparison", "vs"],
    },
    "transactional": {
        "prefixes": ["buy", "order", "purchase", "discount", "deal", "coupon", "price"],
        "suffixes": ["for sale", "buy online", "free shipping", "pricing"],
    },
    "navigational": {
        "prefixes": ["login", "sign in", "official"],
        "suffixes": ["website", "login", "app", "contact"],
    },
}


def classify_intent(keyword: str) -> str:
    """Classify search intent based on keyword signals."""
    kw = keyword.lower().strip()
    scores = {"informational": 0, "commercial": 0, "transactional": 0, "navigational": 0}

    for intent, signals in INTENT_SIGNALS.items():
        for prefix in signals.get("prefixes", []):
            if kw.startswith(prefix):
                scores[intent] += 2
        for suffix in signals.get("suffixes", []):
            if kw.endswith(suffix):
                scores[intent] += 2
        for prefix in signals.get("prefixes", []):
            if prefix in kw:
                scores[intent] += 1

    max_score = max(scores.values())
    if max_score == 0:
        # Default: if short keyword → likely commercial/informational mix
        return "informational" if len(kw.split()) <= 2 else "informational"

    return max(scores, key=scores.get)


# ─────────────────────────────────────────────────────────────────────────────
# CONTENT FORMAT DETECTION
# ─────────────────────────────────────────────────────────────────────────────
# From Backlinko: "Look for content format dominance: Count how many results are
# guides vs listicles vs tools vs videos."

CONTENT_FORMATS = {
    "listicle": ["best", "top", "list of", "ways to", "tips", "ideas", "examples"],
    "how_to_guide": ["how to", "guide", "tutorial", "step by step", "walkthrough"],
    "comparison": ["vs", "versus", "compared", "comparison", "alternative"],
    "product_page": ["buy", "price", "shop", "order", "product"],
    "category_page": ["collection", "category", "types of"],
    "tool": ["calculator", "generator", "checker", "tool", "template"],
    "review": ["review", "honest", "tested", "hands on"],
    "case_study": ["case study", "success story", "results", "how we"],
    "deep_dive": ["complete guide", "ultimate guide", "definitive", "everything about"],
}


def detect_content_format(keyword: str) -> str:
    """Detect the best content format for a keyword."""
    kw = keyword.lower()
    scores = {}

    for format_type, signals in CONTENT_FORMATS.items():
        score = sum(1 for s in signals if s in kw)
        if score > 0:
            scores[format_type] = score

    if scores:
        return max(scores, key=scores.get)

    # Default based on intent
    intent = classify_intent(keyword)
    defaults = {
        "informational": "how_to_guide",
        "commercial": "listicle",
        "transactional": "product_page",
        "navigational": "deep_dive",
    }
    return defaults.get(intent, "how_to_guide")


# ─────────────────────────────────────────────────────────────────────────────
# CONTENT DEPTH ESTIMATOR
# ─────────────────────────────────────────────────────────────────────────────

def estimate_content_depth(keyword: str, format_type: str) -> Dict[str, Any]:
    """
    Estimate required content depth based on keyword and format.
    From Backlinko: "Are these 800-word quick answers or 3,000-word deep dives?"
    """
    depth_map = {
        "listicle": {"min_words": 1500, "max_words": 3000, "sections": "8-15 items", "depth": "medium"},
        "how_to_guide": {"min_words": 2000, "max_words": 4000, "sections": "5-10 steps", "depth": "deep"},
        "comparison": {"min_words": 1500, "max_words": 2500, "sections": "feature comparison table + analysis", "depth": "medium"},
        "product_page": {"min_words": 300, "max_words": 800, "sections": "features, specs, benefits", "depth": "concise"},
        "category_page": {"min_words": 500, "max_words": 1500, "sections": "category overview + product grid", "depth": "concise"},
        "tool": {"min_words": 200, "max_words": 500, "sections": "tool interface + usage guide", "depth": "minimal"},
        "review": {"min_words": 1500, "max_words": 3000, "sections": "pros, cons, verdict, alternatives", "depth": "deep"},
        "case_study": {"min_words": 1500, "max_words": 3000, "sections": "challenge, solution, results", "depth": "deep"},
        "deep_dive": {"min_words": 3000, "max_words": 6000, "sections": "10+ chapters", "depth": "comprehensive"},
    }

    return depth_map.get(format_type, depth_map["how_to_guide"])


# ─────────────────────────────────────────────────────────────────────────────
# SEO BRIEF GENERATOR (AI-enhanced)
# ─────────────────────────────────────────────────────────────────────────────

def generate_seo_brief(
    keyword: str,
    business_context: Dict[str, Any] = None,
    serp_data: Dict[str, Any] = None,
    competitor_data: Dict[str, Any] = None,
    ollama_url: str = "http://172.235.16.165:11434",
) -> Dict[str, Any]:
    """
    Generate a comprehensive SEO content brief for a keyword.

    From Backlinko: "Create a simple brief for each target keyword that captures:
    - Target keyword + intent
    - Winning format
    - Required depth
    - Content gaps (specific opportunities to do better)
    - Business fit"
    """
    business_context = business_context or {}
    serp_data = serp_data or {}

    intent = classify_intent(keyword)
    format_type = detect_content_format(keyword)
    depth = estimate_content_depth(keyword, format_type)

    brief = {
        "keyword": keyword,
        "intent": intent,
        "format": format_type,
        "depth": depth,
        "business_fit": _assess_business_fit(keyword, business_context),
        "title_suggestions": _generate_title_suggestions(keyword, format_type),
        "required_sections": _get_required_sections(keyword, format_type),
        "content_gaps": [],
        "competitive_edge": [],
        "hook_ideas": [],
        "internal_link_targets": [],
        "eeat_requirements": _get_eeat_requirements(format_type),
        "status": "draft",
    }

    # Try AI-enhanced brief generation
    try:
        ai_brief = _ai_enhance_brief(keyword, format_type, business_context, ollama_url)
        if ai_brief:
            brief["content_gaps"] = ai_brief.get("content_gaps", [])
            brief["competitive_edge"] = ai_brief.get("competitive_edge", [])
            brief["hook_ideas"] = ai_brief.get("hook_ideas", [])
            if ai_brief.get("additional_sections"):
                brief["required_sections"].extend(ai_brief["additional_sections"])
    except Exception as e:
        log.warning("[Brief] AI enhancement failed for '%s': %s", keyword, e)

    return brief


def _assess_business_fit(keyword: str, business_context: Dict) -> Dict[str, Any]:
    """
    Assess how well a keyword fits the business.
    Uses Ahrefs' Business Potential scoring (0-3 scale).
    """
    products = business_context.get("products", [])
    topics = business_context.get("topics", [])
    usp = business_context.get("usp", "").lower()
    kw = keyword.lower()

    score = 0
    reasons = []

    # Check product mention
    for product in products:
        if product.lower() in kw:
            score += 1
            reasons.append(f"Mentions product: {product}")
            break

    # Check topic relevance
    for topic in topics:
        if topic.lower() in kw:
            score += 0.5
            reasons.append(f"Matches topic: {topic}")
            break

    # Intent-based business value
    intent = classify_intent(keyword)
    if intent == "transactional":
        score += 1
        reasons.append("Transactional intent (high conversion potential)")
    elif intent == "commercial":
        score += 0.5
        reasons.append("Commercial intent (comparison/evaluation)")

    # USP alignment
    if usp and any(word in kw for word in usp.split() if len(word) > 3):
        score += 0.5
        reasons.append("Aligns with USP")

    score = min(3, round(score, 1))

    return {
        "score": score,
        "label": _business_potential_label(score),
        "reasons": reasons,
    }


def _business_potential_label(score: float) -> str:
    """Ahrefs Business Potential scale."""
    if score >= 2.5:
        return "Your product is an irreplaceable solution"
    elif score >= 1.5:
        return "Your product helps, but is not essential"
    elif score >= 0.5:
        return "Your product can be tangentially mentioned"
    else:
        return "No connection to your product"


def _generate_title_suggestions(keyword: str, format_type: str) -> List[str]:
    """Generate title suggestions based on format type."""
    kw_title = keyword.title()
    templates = {
        "listicle": [
            f"10 Best {kw_title} ({_current_year()})",
            f"Top {kw_title}: Expert Picks & Reviews",
            f"{kw_title}: {_current_year()} Guide + Examples",
        ],
        "how_to_guide": [
            f"How to {kw_title}: Complete Guide ({_current_year()})",
            f"{kw_title}: Step-by-Step Tutorial",
            f"The Definitive Guide to {kw_title}",
        ],
        "comparison": [
            f"{kw_title}: Detailed Comparison & Verdict",
            f"{kw_title} — Which Is Better? (Tested)",
        ],
        "review": [
            f"{kw_title} Review: Honest Assessment ({_current_year()})",
            f"We Tested {kw_title} — Here's What Happened",
        ],
        "deep_dive": [
            f"{kw_title}: Everything You Need to Know",
            f"The Complete {kw_title} Guide ({_current_year()})",
        ],
    }
    return templates.get(format_type, [f"{kw_title}: Complete Guide ({_current_year()})"])


def _get_required_sections(keyword: str, format_type: str) -> List[Dict[str, str]]:
    """Define required content sections based on format type."""
    base_sections = {
        "listicle": [
            {"heading": "Introduction", "type": "intro", "note": "Hook + what readers will learn"},
            {"heading": "Methodology", "type": "trust", "note": "How you evaluated/selected items"},
            {"heading": "[Items 1-N]", "type": "main", "note": "Each item: summary, screenshot, use case"},
            {"heading": "How to Choose", "type": "guide", "note": "Decision framework for readers"},
            {"heading": "FAQ", "type": "seo", "note": "Address People Also Ask questions"},
        ],
        "how_to_guide": [
            {"heading": "Introduction", "type": "intro", "note": "Problem statement + what you'll learn"},
            {"heading": "Prerequisites", "type": "setup", "note": "What readers need before starting"},
            {"heading": "Step-by-Step Process", "type": "main", "note": "Numbered steps with screenshots"},
            {"heading": "Common Mistakes", "type": "value_add", "note": "Pitfalls to avoid"},
            {"heading": "Results & Examples", "type": "proof", "note": "Show real outcomes"},
            {"heading": "FAQ", "type": "seo", "note": "Address related questions"},
        ],
        "comparison": [
            {"heading": "Quick Verdict", "type": "intro", "note": "TL;DR for scanners"},
            {"heading": "Feature Comparison Table", "type": "main", "note": "Side-by-side comparison"},
            {"heading": "Detailed Analysis", "type": "main", "note": "In-depth per feature"},
            {"heading": "Who Should Choose What", "type": "guide", "note": "Use-case recommendations"},
            {"heading": "Final Verdict", "type": "conclusion", "note": "Clear recommendation"},
        ],
        "deep_dive": [
            {"heading": "Introduction", "type": "intro", "note": "Topic overview + learning objectives"},
            {"heading": "Key Concepts", "type": "foundation", "note": "Define terms and fundamentals"},
            {"heading": "Detailed Guide", "type": "main", "note": "Multi-section comprehensive coverage"},
            {"heading": "Advanced Strategies", "type": "value_add", "note": "Beyond basics"},
            {"heading": "Case Studies / Examples", "type": "proof", "note": "Real-world applications"},
            {"heading": "Key Takeaways", "type": "conclusion", "note": "Summary + next steps"},
        ],
    }
    return base_sections.get(format_type, base_sections["how_to_guide"])


def _get_eeat_requirements(format_type: str) -> Dict[str, List[str]]:
    """
    E-E-A-T requirements based on content format.
    From Backlinko: "Google's quality rater guidelines emphasize Experience,
    Expertise, Authoritativeness, and Trustworthiness."
    """
    base = {
        "experience": [
            "Include personal experience or hands-on testing",
            "Add original screenshots (not stock photos)",
            "Share specific results or outcomes",
        ],
        "expertise": [
            "Include author bio with relevant credentials",
            "Reference methodology and data sources",
            "Demonstrate subject matter depth",
        ],
        "authoritativeness": [
            "Link to authoritative sources",
            "Include original data or research where possible",
            "Get expert quotes or reviews",
        ],
        "trustworthiness": [
            "Clearly label sponsored/affiliate content",
            "Include dates and keep content current",
            "Provide balanced viewpoints",
        ],
    }

    # Format-specific additions
    if format_type in ("review", "comparison"):
        base["experience"].append("Show proof of actual product testing")
        base["trustworthiness"].append("Disclose any affiliate relationships")
    elif format_type in ("how_to_guide", "deep_dive"):
        base["expertise"].append("Include step-by-step proof with real examples")

    return base


def _ai_enhance_brief(
    keyword: str, format_type: str, business_context: Dict, ollama_url: str,
) -> Optional[Dict]:
    """Use AI to enhance the brief with gaps, edges, and hooks."""
    products = ", ".join(business_context.get("products", [])[:5])
    prompt = f"""Analyze the keyword "{keyword}" for an SEO content brief. Content format: {format_type}. Business products: {products}.

Return JSON with:
1. "content_gaps": 3-5 specific topics/subtopics competitors likely miss
2. "competitive_edge": 2-3 ways to make this content stand out
3. "hook_ideas": 2-3 linkable hooks (stats, charts, frameworks people would reference)
4. "additional_sections": 2-3 extra section suggestions with heading and note

Return ONLY valid JSON, no other text."""

    try:
        resp = requests.post(
            f"{ollama_url}/api/generate",
            json={"model": "deepseek-r1:8b", "prompt": prompt, "stream": False,
                  "options": {"num_ctx": 2048}},
            timeout=60,
        )
        if resp.ok:
            text = resp.json().get("response", "")
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group())
    except Exception as e:
        log.debug("[Brief] AI enhancement error: %s", e)
    return None


def _current_year() -> str:
    from datetime import datetime
    return str(datetime.utcnow().year)


# ─────────────────────────────────────────────────────────────────────────────
# BATCH BRIEF GENERATION
# ─────────────────────────────────────────────────────────────────────────────

def generate_briefs_batch(
    keywords: List[str],
    business_context: Dict = None,
    use_ai: bool = True,
    ollama_url: str = "http://172.235.16.165:11434",
) -> List[Dict[str, Any]]:
    """Generate SEO briefs for a batch of keywords."""
    briefs = []
    for kw in keywords:
        brief = generate_seo_brief(
            keyword=kw,
            business_context=business_context,
            ollama_url=ollama_url if use_ai else None,
        )
        briefs.append(brief)
    return briefs

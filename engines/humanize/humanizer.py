"""
Core humanizer — transforms AI-generated content section-by-section
to read naturally while preserving SEO structure.

Uses AIRouter for LLM calls with the standard Groq → Ollama → Gemini chain.
"""
import re
import json
import logging
from typing import Dict, List, Optional

log = logging.getLogger("annaseo.humanize")


# ── Tone/style prompt fragments ──────────────────────────────────────────────
TONE_PROMPTS = {
    "natural": "Write in a natural, approachable tone as if explaining to a knowledgeable friend.",
    "conversational": "Write in a warm, conversational tone. Use contractions, short asides. Vary rhythm.",
    "expert": "Write in an authoritative expert tone. Use precise terminology but explain complex concepts clearly.",
    "narrative": "Write in a narrative, storytelling style. Use anecdotes, examples, vivid descriptions.",
    "direct": "Write in a direct, no-nonsense tone. Short sentences. Get to the point fast.",
}

STYLE_PROMPTS = {
    "conversational": "Mix 5-word punches with 25-word flowing sentences. Occasionally start sentences with 'And' or 'But'. Use fragments for emphasis.",
    "academic": "Use well-structured argumentation with evidence. Maintain formality without being stiff.",
    "journalistic": "Lead with the most important information. Use active voice. Keep paragraphs short (2-3 sentences).",
    "casual": "Write like a blog post from someone who genuinely cares about the topic. Include personal observations.",
}

# ── Master rewrite prompt (production-grade) ──────────────────────────────────
_MASTER_REWRITE_PROMPT = """You are a senior human editor at a top publication. Rewrite this section so it reads like a real human expert wrote it — NOT like AI content, NOT like SEO filler.

KEYWORD: {keyword}
TONE: {tone_instruction}
STYLE: {style_instruction}{persona_text}

ARTICLE OUTLINE (other sections — do NOT repeat their ideas):
{outline_text}

━━━ CRITICAL RULES ━━━

KEYWORD DENSITY GUARD:
- Maintain the keyword "{keyword}" naturally — use the exact phrase only where it genuinely reads well
- Short sections (<150 words): 0-1 exact mentions is fine
- Medium sections (150-300 words): usually 1 exact mention is enough
- Long sections (300+ words): cap exact mentions at 2 unless absolutely necessary
- Use natural variations, partial matches, and pronouns for the remaining references
- Do NOT force at least one exact mention into every section
- If the same exact phrase repeats in one section, replace extras with natural alternatives

HUMAN VOICE (most important):
- Write like a real person with opinions, not a content writer following a template
- Use contractions (don't, it's, won't, that's)
- Start some sentences with "And", "But", "So", "Look,"
- Include slight opinion: "honestly", "the real issue is", "what most people miss"
- Use specific details: real prices, real place names, real numbers — not vague claims
- Short sentences for punch. Long sentences for flow. Never 3 same-length sentences in a row.
- Every paragraph MUST differ in length (1-4 sentences, varied)

BANNED (instant fail):
- "delve/crucial/multifaceted/tapestry/nuanced/paradigm/holistic/pivotal/leverage/foster/encompass/embark/unleash/realm"
- "furthermore/moreover/additionally" as sentence starters
- "in conclusion/it is worth noting/in today's world/dive into/let's explore/game-changer"
- "research shows/data indicates/studies suggest/evidence suggests" (unless citing a SPECIFIC named source — keep phrases like "FDA research shows" or "a 2024 Stanford study suggests")
- "according to recent research" (vague — name the source or remove)
- Any phrase that sounds like a template filler

KEEP THESE (they score for E-E-A-T):
- "we tested/we found/in our experience/our team discovered" — KEEP these if they describe a specific observation or result
- Authority phrases with named sources (e.g., "according to the USDA", "NIH research shows")
- Experience signals paired with specific details

STRUCTURE:
- Keep ALL HTML tags, headings, and links exactly as-is
- Do NOT add new headings or restructure
- Conclusion sentences must add a NEW specific detail — not restate the heading

{signal_text}{link_text}

SECTION TO REWRITE:
{section_trimmed}

Return ONLY the rewritten HTML. No commentary, no fences."""

# ── Targeted fix prompt (used after LLM judge identifies issues) ──────────────
_TARGETED_FIX_PROMPT = """You are editing a section of a published article based on editor feedback.

KEYWORD: {keyword}
TONE: {tone_instruction}

EDITOR ISSUES TO FIX (fix ONLY these — do not rewrite unnecessarily):
{issues_text}

RULES:
- Keep ALL HTML tags, headings, and links
- Only change what the editor flagged
- Preserve good writing — do not degrade parts that work
- No clichés or AI patterns
- Use the keyword naturally — do NOT stuff it
- Remove any fake authority claims ("we tested", "research shows") unless citing a real source

SECTION TO IMPROVE:
{section_trimmed}

Return ONLY the improved HTML. No commentary."""


def build_humanize_prompt(
    section_html: str,
    keyword: str,
    tone: str = "natural",
    style: str = "conversational",
    persona: str = "",
    ai_signals: List[str] = None,
    links_to_preserve: List[Dict] = None,
    outline: List[str] = None,
) -> str:
    """Build the master rewrite prompt for humanizing a single section."""

    tone_instruction = TONE_PROMPTS.get(tone, TONE_PROMPTS["natural"])
    style_instruction = STYLE_PROMPTS.get(style, STYLE_PROMPTS["conversational"])

    signal_text = ""
    if ai_signals:
        signal_text = "\nFIX THESE AI SIGNALS: " + "; ".join(ai_signals[:4])

    link_text = ""
    if links_to_preserve:
        link_text = "\nPRESERVE THESE LINKS: " + ", ".join(
            f'<a href="{l["href"]}">{l["text"]}</a>' for l in links_to_preserve[:5]
        )

    persona_text = ""
    if persona:
        persona_text = f"\nWRITE AS: {persona}"

    outline_text = "(No outline available)"
    if outline:
        outline_text = "\n".join(f"- {h}" for h in outline[:20])

    section_trimmed = section_html[:4000]

    return _MASTER_REWRITE_PROMPT.format(
        keyword=keyword,
        tone_instruction=tone_instruction,
        style_instruction=style_instruction,
        persona_text=persona_text,
        outline_text=outline_text,
        signal_text=signal_text,
        link_text=link_text,
        section_trimmed=section_trimmed,
    )


def build_targeted_fix_prompt(
    section_html: str,
    keyword: str,
    issues: List[str],
    tone: str = "natural",
) -> str:
    """Build a targeted fix prompt using judge-identified issues."""
    tone_instruction = TONE_PROMPTS.get(tone, TONE_PROMPTS["natural"])
    issues_text = "\n".join(f"- {issue}" for issue in issues) if issues else "- Improve clarity and specificity"
    section_trimmed = section_html[:4000]
    return _TARGETED_FIX_PROMPT.format(
        keyword=keyword,
        tone_instruction=tone_instruction,
        issues_text=issues_text,
        section_trimmed=section_trimmed,
    )


def humanize_section(
    section_html: str,
    keyword: str,
    tone: str = "natural",
    style: str = "conversational",
    persona: str = "",
    ai_signals: List[str] = None,
    links: List[Dict] = None,
    outline: List[str] = None,
    ai_router=None,
) -> Dict:
    """Humanize a single HTML section using the AI router.

    Args:
        outline: List of all section headings in the article (for global context)

    Returns: {success, html, provider, tokens, error}
    """
    if not section_html.strip():
        return {"success": True, "html": section_html, "provider": "none", "tokens": 0}

    prompt = build_humanize_prompt(
        section_html, keyword, tone, style, persona, ai_signals, links, outline
    )

    try:
        if ai_router is None:
            from core.ai_config import AIRouter
            ai_router = AIRouter

        text = ""
        tokens = 0
        # Retry with backoff when all providers fail (Groq rate-limited, Ollama down, Gemini exhausted)
        for _attempt in range(2):
            text, tokens = ai_router.call_with_tokens(
                prompt,
                system="You are a content humanization specialist. Return only HTML.",
                temperature=0.6,  # higher creativity for natural writing
            )
            if text.strip():
                break
            # Brief wait before retry — provider may recover
            import time as _time
            wait = 1 * (_attempt + 1)  # 1s, 2s
            log.info(f"[humanizer] All providers returned empty (attempt {_attempt+1}/2) — waiting {wait}s for retry")
            _time.sleep(wait)

        if not text.strip():
            return {"success": False, "html": section_html, "provider": "none", "tokens": 0, "error": "All AI providers failed after 2 attempts"}

        # Clean up any markdown fences
        text = re.sub(r'^```(?:html)?\s*', '', text.strip())
        text = re.sub(r'\s*```\s*$', '', text.strip())

        return {"success": True, "html": text.strip(), "provider": "ai_router", "tokens": tokens}

    except Exception as e:
        log.error(f"Humanize section failed: {e}")
        return {"success": False, "html": section_html, "provider": "none", "tokens": 0, "error": str(e)}


def humanize_targeted(
    section_html: str,
    keyword: str,
    issues: List[str],
    tone: str = "natural",
    ai_router=None,
) -> Dict:
    """Apply targeted fixes to a section based on judge-identified issues.

    Unlike humanize_section(), this does NOT do a full rewrite — it only
    addresses the specific problems the judge flagged.

    Returns: {success, html, provider, tokens, error}
    """
    if not section_html.strip():
        return {"success": True, "html": section_html, "provider": "none", "tokens": 0}

    prompt = build_targeted_fix_prompt(section_html, keyword, issues, tone)

    try:
        if ai_router is None:
            from core.ai_config import AIRouter
            ai_router = AIRouter

        text, tokens = ai_router.call_with_tokens(
            prompt,
            system="You are a professional content editor. Return only improved HTML.",
            temperature=0.4,  # lower temp for targeted fixes — more conservative
        )

        if not text.strip():
            return {"success": False, "html": section_html, "provider": "none", "tokens": 0,
                    "error": "Empty AI response in targeted fix"}

        text = re.sub(r'^```(?:html)?\s*', '', text.strip())
        text = re.sub(r'\s*```\s*$', '', text.strip())

        return {"success": True, "html": text.strip(), "provider": "ai_router", "tokens": tokens}

    except Exception as e:
        log.error(f"Targeted fix failed: {e}")
        return {"success": False, "html": section_html, "provider": "none", "tokens": 0, "error": str(e)}

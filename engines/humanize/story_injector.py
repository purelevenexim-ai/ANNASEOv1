"""Micro-story injector — 1 LLM call per article, skipped if narrative already present."""
import re
import logging

log = logging.getLogger("annaseo.humanize.story_injector")

_STORY_PROMPT = """Write a 4-sentence micro-story for an article about: {keyword}

FORMAT: Character encounters/uses {keyword} → unexpected discovery → concrete result

RULES:
- Sentence 1: specific character + real context (who, where, doing what)
- Sentence 2: what they noticed first — visual or sensory detail, be specific
- Sentence 3: the unexpected thing — a surprise, catch, or twist
- Sentence 4: what changed — specific outcome, not "they loved it"
- Total: 60\u201375 words. No hype endings.
- Output ONLY the 4 sentences. No heading, labels, or commentary."""

# If the article already contains 3+ of these narrative markers, skip injection
_STORY_MARKERS = [
    "ordered", "bought", "noticed", "realized", "realised",
    "switched", "tried", "discovered", "expected",
]


def inject_micro_story(html: str, keyword: str, ai_router=None) -> str:
    """Inject a short narrative micro-story after the second H2 heading.

    Skipped automatically if the article already has strong narrative content.
    Non-fatal — returns original html unchanged on any error.

    Args:
        html: Article HTML
        keyword: Target SEO keyword
        ai_router: AIRouter instance (imported from core.ai_config if None)

    Returns:
        HTML with micro-story injected, or original HTML if skipped/failed.
    """
    text_lower = re.sub(r"<[^>]+>", " ", html).lower()
    if sum(1 for m in _STORY_MARKERS if m in text_lower) >= 3:
        log.debug("Story injection skipped \u2014 article already has narrative content")
        return html

    try:
        if ai_router is None:
            from core.ai_config import AIRouter
            ai_router = AIRouter

        story_text, _ = ai_router.call_with_tokens(
            _STORY_PROMPT.format(keyword=keyword),
            system="You are a creative writing specialist. Output only the story sentences, no labels.",
            temperature=0.85,
        )

        if not story_text or len(story_text.strip()) < 30:
            log.warning("Story injector: empty or too-short response, skipping")
            return html

        # Strip any label prefixes like "Sentence 1: ..."
        story_text = re.sub(r"Sentence\s*\d+:\s*", "", story_text.strip())
        story_html = f"\n<p>{story_text}</p>\n"

        # Insert after the second H2, or first H2, or first paragraph
        h2_matches = list(re.finditer(r"</h2>", html, re.IGNORECASE))
        if len(h2_matches) >= 2:
            insert_pos = h2_matches[1].end()
        elif h2_matches:
            insert_pos = h2_matches[0].end()
        else:
            p_m = re.search(r"</p>", html, re.IGNORECASE)
            insert_pos = p_m.end() if p_m else len(html)

        html = html[:insert_pos] + story_html + html[insert_pos:]
        log.info("Micro-story injected (%d chars)", len(story_text))
        return html

    except Exception as e:
        log.warning("Story injection failed (non-fatal): %s", e)
        return html

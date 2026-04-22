"""
Section fixer — calls AI to regenerate a single failing section.

This module is intentionally thin — the actual AI call is delegated
to the pipeline engine's existing `_call_ai_raw_with_chain()` method
via a callable passed in from the engine.
"""
import re
import logging
from typing import Callable, Optional

log = logging.getLogger(__name__)


async def fix_section(
    prompt: str,
    ai_call: Callable,
    original_html: str,
    *,
    max_tokens: int = 3000,
    temperature: float = 0.4,
) -> Optional[str]:
    """Call AI to fix a single section. Validates output before returning.

    Args:
        prompt: The recovery prompt built by strategy.build_recovery_prompt()
        ai_call: Async callable(prompt, temperature, max_tokens) -> str
        original_html: The original section HTML (for comparison)
        max_tokens: Token limit for AI call
        temperature: Temperature for AI call

    Returns:
        Fixed HTML string, or None if fix was invalid/empty
    """
    try:
        result = await ai_call(prompt, temperature, max_tokens)
    except Exception as e:
        log.warning(f"Recovery AI call failed: {e}")
        return None

    if not result or len(result.strip()) < 50:
        log.warning("Recovery: AI returned empty or too-short output")
        return None

    # Clean code fences if present
    result = re.sub(r"```html\n?", "", result)
    result = re.sub(r"```\n?", "", result).strip()

    # Validate: output shouldn't be drastically shorter than input
    orig_wc = len(re.sub(r"<[^>]+>", " ", original_html).split())
    new_wc = len(re.sub(r"<[^>]+>", " ", result).split())
    if new_wc < orig_wc * 0.6 and orig_wc > 30:
        log.warning(f"Recovery: output too short ({new_wc}w vs {orig_wc}w original) — rejecting")
        return None

    # Validate: output should contain HTML tags
    if not re.search(r"<(?:p|h[2-4]|ul|ol|table|div)", result, re.I):
        log.warning("Recovery: output has no HTML structure — rejecting")
        return None

    # Validate: links should be preserved
    orig_links = len(re.findall(r"<a\s", original_html, re.I))
    new_links = len(re.findall(r"<a\s", result, re.I))
    if orig_links > 2 and new_links < orig_links * 0.5:
        log.warning(f"Recovery: links lost ({orig_links}→{new_links}) — rejecting")
        return None

    return result

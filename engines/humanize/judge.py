"""
LLM-as-Judge scoring engine for humanized content.

Uses the AI router to evaluate fully-assembled articles on 5 dimensions:
- Structure quality (logical flow, no fragmentation)
- Repetition (no duplicate ideas or sections)
- Human tone (no AI clichés, natural rhythm)
- Insight depth (specific, non-obvious, adds value)
- Vocabulary diversity (varied sentence structure)

Returns a numeric score + plain-language issue list + worst section list.
This runs AFTER the full article is assembled, before any targeted fix pass.
"""
import json
import logging
import re
from typing import Dict, List

log = logging.getLogger("annaseo.humanize.judge")

# ── Max article sample size to avoid token overflow ────────────────────────────
_MAX_CHARS = 12000

JUDGE_PROMPT = """You are a senior content editor evaluating an article for publication quality.

ARTICLE KEYWORD: {keyword}

ARTICLE TEXT:
{article_text}

---

Evaluate this article on 5 dimensions. Be realistic and harsh — do not inflate scores.
A 90+ score means a real human expert wrote this. A 60 is typical AI output. A 40 is clear AI spam.

SCORING RULES:
- "structure": Logical progression, no fragmentation, clear narrative arc (0-100)
- "repetition": Penalize heavily for repeated ideas/concepts across sections (0-100; 100 = no repetition)
- "tone": Natural human writing — no clichés, no hype phrases, no robotic rhythm (0-100)
- "depth": Content adds specific, non-obvious insights — not just definitions (0-100)
- "vocab": Varied sentence lengths, structures, vocabulary — not templated (0-100)

ISSUES: List specific, actionable problems you detected (max 8 items). Be concrete.
Examples of valid issues:
- "Introduction uses 'Let's face it' — generic filler opener"
- "Sections 3 and 7 cover the same idea about garam masala"
- "All paragraphs are 3-4 sentences — no variation"
- "No specific place names, quantities, or real examples — too vague"

WORST_SECTIONS: List heading text of the 3-5 worst sections (most AI-like or most repetitive).

Return ONLY valid JSON in this exact format — no commentary:
{{
  "total": <weighted_average_int>,
  "breakdown": {{
    "structure": <int>,
    "repetition": <int>,
    "tone": <int>,
    "depth": <int>,
    "vocab": <int>
  }},
  "issues": [<string>, ...],
  "worst_sections": [<heading_string>, ...]
}}"""


def _strip_html(html: str) -> str:
    """Strip HTML tags for plain-text analysis."""
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _extract_headings(html: str) -> List[str]:
    """Extract h1-h3 heading texts as ordered list."""
    headings = []
    for m in re.finditer(r'<h[1-3][^>]*>(.*?)</h[1-3]>', html, re.I | re.S):
        text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if text:
            headings.append(text)
    return headings


def llm_judge(html: str, keyword: str, ai_router=None) -> Dict:
    """
    Run LLM-as-Judge scoring on a fully assembled article.

    Args:
        html: Full article HTML
        keyword: Target SEO keyword
        ai_router: Optional AI router adapter (uses AIRouter if not provided)

    Returns:
        {
          total: int (0-100),
          breakdown: {structure, repetition, tone, depth, vocab},
          issues: [str],
          worst_sections: [str],
          error: str  (only if judge call failed)
        }
    """
    if ai_router is None:
        try:
            from core.ai_config import AIRouter
            ai_router = AIRouter
        except ImportError:
            log.error("[judge] Cannot import AIRouter")
            return _fallback_result("Cannot import AIRouter")

    # Strip HTML and cap size
    article_text = _strip_html(html)
    if len(article_text) > _MAX_CHARS:
        # Keep beginning + end to catch both intro and conclusion quality
        half = _MAX_CHARS // 2
        article_text = article_text[:half] + "\n\n[...article continues...]\n\n" + article_text[-half:]

    prompt = JUDGE_PROMPT.format(keyword=keyword, article_text=article_text)

    try:
        raw, tokens = ai_router.call_with_tokens(
            prompt,
            system="You are a strict content quality evaluator. Return ONLY valid JSON. No markdown fences.",
            temperature=0.1,  # Low temperature for consistent judging
        )
    except Exception as e:
        log.error(f"[judge] AI call failed: {e}")
        return _fallback_result(str(e))

    if not raw.strip():
        log.warning("[judge] Empty AI response from judge")
        return _fallback_result("Empty AI response")

    # Parse JSON — strip any accidental markdown fences
    raw = raw.strip()
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```\s*$', '', raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Attempt to extract JSON from response that may have surrounding text
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError as e:
                log.warning(f"[judge] JSON parse failed: {e} — raw: {raw[:200]}")
                return _fallback_result(f"JSON parse error: {e}")
        else:
            log.warning(f"[judge] No JSON found in response: {raw[:200]}")
            return _fallback_result("No JSON in response")

    # Validate and normalise
    breakdown = data.get("breakdown", {})
    total = data.get("total", 0)

    # Recompute total as weighted average if missing or suspicious
    if not total or total > 100:
        scores = [breakdown.get(k, 0) for k in ("structure", "repetition", "tone", "depth", "vocab")]
        weights = [0.20, 0.25, 0.20, 0.20, 0.15]  # repetition weighted highest
        valid = [(s, w) for s, w in zip(scores, weights) if isinstance(s, (int, float)) and 0 <= s <= 100]
        if valid:
            total = int(sum(s * w for s, w in valid) / sum(w for _, w in valid))

    result = {
        "total": int(total),
        "breakdown": {
            "structure":  int(breakdown.get("structure",  0)),
            "repetition": int(breakdown.get("repetition", 0)),
            "tone":       int(breakdown.get("tone",       0)),
            "depth":      int(breakdown.get("depth",      0)),
            "vocab":      int(breakdown.get("vocab",      0)),
        },
        "issues": [str(i) for i in data.get("issues", [])[:8]],
        "worst_sections": [str(s) for s in data.get("worst_sections", [])[:5]],
    }

    log.info(f"[judge] Score {result['total']}/100 — {len(result['issues'])} issues, "
             f"{len(result['worst_sections'])} worst sections (tokens={tokens})")

    return result


def _fallback_result(error: str) -> Dict:
    """Return a placeholder result when the judge call fails."""
    return {
        "total": 0,
        "breakdown": {"structure": 0, "repetition": 0, "tone": 0, "depth": 0, "vocab": 0},
        "issues": [],
        "worst_sections": [],
        "error": error,
    }

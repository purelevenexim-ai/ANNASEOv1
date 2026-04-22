"""
Structural deduplicator for over-segmented AI articles.

When an article has been split into >20 sections (common with AI-generated
long-form content), many sections cover the same idea under different headings.
This module:
  1. Sends only the heading list to the LLM (no full content — avoids token overflow)
  2. Gets back a JSON merge plan
  3. Executes the merge plan programmatically (string concatenation)
  4. Returns a collapsed, deduplicated section list

SEO safety: all content is preserved during merge — only headings change.
Target output: 6–15 sections regardless of input size.
"""
import json
import logging
import re
from typing import Dict, List, Optional

log = logging.getLogger("annaseo.humanize.restructurer")

# ── Only activate when article has more sections than this threshold ───────────
RESTRUCTURE_THRESHOLD = 20

# ── LLM merge-plan prompt (headings only — no content) ────────────────────────
MERGE_PLAN_PROMPT = """You are restructuring an article outline.

TARGET KEYWORD: {keyword}

CURRENT HEADINGS (indexed from 0):
{headings_list}

TASK:
This article has too many sections. Many cover the same concept. Create a merge plan.

TARGET: 6–12 sections maximum.

RULES:
1. Sections covering the same core idea → merge them (keep the clearest heading, or write a better one)
2. Very short or vague sections → merge into nearest related section
3. Preserve sections that cover unique, distinct topics
4. Every original section index must appear in exactly one action
5. Output headings must be natural, specific, non-formulaic (no "Exploring...", "Understanding...", "Overview of...")

RETURN ONLY valid JSON in this exact format:
{{
  "actions": [
    {{"keep": <index>, "new_heading": "<improved heading text>"}},
    {{"merge": [<index1>, <index2>, ...], "new_heading": "<merged heading text>", "reason": "<brief reason>"}},
    {{"keep": <index>}}
  ]
}}

Note: Each action can be either "keep" (single section) or "merge" (multiple sections combined).
A "keep" action without "new_heading" keeps the original heading.
Every index 0..{max_index} must appear in exactly one action."""


def deduplicate_and_collapse(
    sections: List[Dict],
    keyword: str,
    threshold: int = RESTRUCTURE_THRESHOLD,
    ai_router=None,
) -> List[Dict]:
    """
    Collapse over-segmented sections by merging duplicates.

    Args:
        sections: List of section dicts from splitter.split_into_sections()
        keyword: Target SEO keyword
        threshold: Only activate if len(sections) > threshold
        ai_router: Optional AIRouter override (for testing)

    Returns:
        New sections list — collapsed if over threshold, original if not.
        Original section indices are remapped to sequential order.
    """
    if len(sections) <= threshold:
        log.info(f"[restructurer] {len(sections)} sections ≤ threshold ({threshold}) — skipping")
        return sections

    log.info(f"[restructurer] {len(sections)} sections — requesting merge plan from LLM")

    if ai_router is None:
        try:
            from core.ai_config import AIRouter
            ai_router = AIRouter
        except ImportError:
            log.error("[restructurer] Cannot import AIRouter — returning original sections")
            return sections

    # Build numbered heading list for LLM
    headings_list = "\n".join(
        f"{i}. {s.get('heading') or '(no heading)'}"
        for i, s in enumerate(sections)
    )

    prompt = MERGE_PLAN_PROMPT.format(
        keyword=keyword,
        headings_list=headings_list,
        max_index=len(sections) - 1,
    )

    try:
        raw, _ = ai_router.call_with_tokens(
            prompt,
            system="You are a content structure optimizer. Return ONLY valid JSON. No markdown fences.",
            temperature=0.1,
        )
    except Exception as e:
        log.error(f"[restructurer] AI call failed: {e} — returning original sections")
        return sections

    if not raw.strip():
        log.warning("[restructurer] Empty LLM response — returning original sections")
        return sections

    # Parse JSON
    raw = raw.strip()
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```\s*$', '', raw)

    try:
        plan = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                plan = json.loads(match.group(0))
            except json.JSONDecodeError as e:
                log.warning(f"[restructurer] JSON parse failed: {e} — returning original sections")
                return sections
        else:
            log.warning("[restructurer] No JSON found — returning original sections")
            return sections

    actions = plan.get("actions", [])
    if not actions:
        log.warning("[restructurer] Empty action list — returning original sections")
        return sections

    # Validate all indices are accounted for
    all_covered = set()
    for action in actions:
        if "merge" in action:
            all_covered.update(action["merge"])
        elif "keep" in action:
            all_covered.add(action["keep"])

    missing = set(range(len(sections))) - all_covered
    if missing:
        log.warning(f"[restructurer] Missing indices in plan: {missing} — appending as keeps")
        for idx in sorted(missing):
            actions.append({"keep": idx})

    # Execute merge plan
    new_sections = []
    for action in actions:
        if "merge" in action:
            indices = action["merge"]
            new_heading = action.get("new_heading", "")

            # Concatenate content of all merged sections
            merged_content_parts = []
            for idx in sorted(indices):
                if 0 <= idx < len(sections):
                    sec = sections[idx]
                    content = sec["content"]
                    # Replace the original heading with the new one (only for first section)
                    merged_content_parts.append(content)

            if not merged_content_parts:
                continue

            # Use first section's full content, append body of others (strip their headings)
            combined = merged_content_parts[0]
            for extra in merged_content_parts[1:]:
                # Strip leading heading tag so we don't get duplicate headings
                body = re.sub(r'^<h[1-3][^>]*>.*?</h[1-3]>\s*', '', extra, count=1, flags=re.I | re.S)
                if body.strip():
                    combined = combined.rstrip() + "\n" + body

            # Replace heading in first section with new heading if specified
            if new_heading:
                # Find the tag of the first section
                first_idx = min(indices)
                first_sec = sections[first_idx] if 0 <= first_idx < len(sections) else None
                tag = first_sec.get("tag", "h2") if first_sec else "h2"
                combined = re.sub(
                    r'<h[1-3][^>]*>.*?</h[1-3]>',
                    f'<{tag}>{_escape_html(new_heading)}</{tag}>',
                    combined, count=1, flags=re.I | re.S
                )

            word_count = len(re.sub(r'<[^>]+>', '', combined).split())
            new_sections.append({
                "index": len(new_sections),
                "heading": new_heading or sections[sorted(indices)[0]].get("heading", ""),
                "tag": sections[sorted(indices)[0]].get("tag", "h2"),
                "content": combined.strip(),
                "word_count": word_count,
                "_merged_from": indices,
            })

        elif "keep" in action:
            idx = action["keep"]
            if 0 <= idx < len(sections):
                sec = dict(sections[idx])  # copy
                new_heading = action.get("new_heading", "")
                if new_heading and new_heading != sec.get("heading", ""):
                    # Replace heading text in content
                    tag = sec.get("tag", "h2")
                    sec["content"] = re.sub(
                        r'<h[1-3][^>]*>.*?</h[1-3]>',
                        f'<{tag}>{_escape_html(new_heading)}</{tag}>',
                        sec["content"], count=1, flags=re.I | re.S
                    )
                    sec["heading"] = new_heading
                sec["index"] = len(new_sections)
                new_sections.append(sec)

    if not new_sections:
        log.warning("[restructurer] Merge plan produced empty result — returning original sections")
        return sections

    log.info(f"[restructurer] Collapsed {len(sections)} → {len(new_sections)} sections")
    return new_sections


def _escape_html(text: str) -> str:
    """Minimal HTML escaping for heading text."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

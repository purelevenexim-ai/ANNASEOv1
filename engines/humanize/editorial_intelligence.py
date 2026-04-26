import re
from typing import Dict, List
from core.routing_schema import ContentState

_STRIP_TAGS = re.compile(r"<[^>]+>")


def _plain(html: str) -> str:
    """Return visible text by stripping HTML tags."""
    return _STRIP_TAGS.sub(" ", html)


class EditorialIntelligenceEngine:
    """
    An intelligence layer that operates between content drafting and humanization.
    It detects repeated anecdotes, over-stuffed keywords, and intent-delivery
    failures — then produces actionable fix instructions for the recovery step.
    """

    def __init__(self, title: str, keyword: str, intent: str, content_state: ContentState):
        self.title = title
        self.keyword = keyword
        self.intent = intent
        self.state = content_state

    # ── Repetition detection ──────────────────────────────────────────────

    def check_for_repetition(self, section_html: str, section_title: str) -> List[str]:
        """
        Scans plain text of a section for anecdote/example clue phrases,
        hashes each found sentence, and flags it as a duplicate if the same
        snippet was seen in a prior section.
        """
        instructions = []
        plain = _plain(section_html)
        clues = [
            "For example, ",
            "Consider the story of ",
            "From a buyer perspective, ",
            "In practice, ",
            "Research shows that ",
            "A case study",
            "Consider a ",
            "Here's an example",
        ]
        for clue in clues:
            idx = plain.find(clue)
            while idx != -1:
                end = plain.find(".", idx)
                if end == -1:
                    break
                snippet = plain[idx: end + 1].strip()
                if len(snippet) > 20:
                    is_duplicate = self.state.check_and_add_anecdote(snippet)
                    if is_duplicate:
                        instructions.append(
                            f"DUPLICATE ANECDOTE in section '{section_title}': "
                            f"'{snippet[:60]}...' was already used earlier. "
                            f"Replace it with a fresh, distinct example."
                        )
                # Look for further occurrences in same section
                idx = plain.find(clue, end + 1)
        return instructions

    def scan_all_sections_for_repetition(self, full_html: str) -> List[str]:
        """
        Splits the full draft on <h2> tags and runs check_for_repetition on
        each section individually, returning all flagged duplicates.
        """
        instructions = []
        # Split on opening h2 tags (keeps the tag with the section)
        chunks = re.split(r"(?=<h2[\s>])", full_html, flags=re.IGNORECASE)
        for chunk in chunks:
            if not chunk.strip():
                continue
            # Extract h2 title for context
            m = re.search(r"<h2[^>]*>(.*?)</h2>", chunk, re.IGNORECASE | re.DOTALL)
            section_title = _plain(m.group(1)).strip() if m else "(intro)"
            instructions.extend(self.check_for_repetition(chunk, section_title))
        return instructions

    # ── Keyword density ───────────────────────────────────────────────────

    def global_keyword_density_check(self, full_html: str) -> List[str]:
        """
        Checks exact-phrase keyword density on visible text only (HTML stripped).
        Flags both over-density (>2%) and heading stuffing.
        """
        instructions = []
        plain = _plain(full_html)
        words = re.findall(r"\b\w+\b", plain)
        word_count = len(words)
        if word_count == 0:
            return instructions

        kw = self.keyword
        kw_lower = kw.lower()
        kw_count = len(re.findall(rf"\b{re.escape(kw_lower)}\b", plain.lower()))
        density = kw_count / word_count

        if density > 0.02:
            instructions.append(
                f"KEYWORD STUFFING: The exact phrase '{kw}' appears {kw_count} times "
                f"({density:.1%} density — limit is 2%). Replace many instances with "
                f"natural synonyms: 'these options', 'this spice', 'the product', or "
                f"simply restructure sentences to avoid repeating the phrase."
            )

        # Check for the keyword phrase appearing verbatim inside heading tags
        headings_with_kw = re.findall(
            rf"<h[2-4][^>]*>[^<]*{re.escape(kw_lower)}[^<]*</h[2-4]>",
            full_html.lower()
        )
        if len(headings_with_kw) > 1:
            instructions.append(
                f"HEADING STUFFING: '{kw}' appears verbatim in {len(headings_with_kw)} headings. "
                f"Keep it in at most one H2. Replace the rest with descriptive, natural headings."
            )

        return instructions

    # ── Intent fulfilment ─────────────────────────────────────────────────

    def intent_delivery_check(self, sections: List[Dict]) -> List[str]:
        """
        Checks whether the article structure actually delivers on the search intent:
        - 'best / top' keywords require a listicle with named items (≥3 H3s)
        - 'buy / supplier' B2B keywords must NOT repeat the full kw phrase in headings
        """
        instructions = []
        kw_lower = self.keyword.lower()

        # --- Review/listicle intent ---
        if "best" in kw_lower or "top" in kw_lower:
            has_named_list = False
            for sec in sections:
                h2 = (sec.get("h2") or "").lower()
                h3s = sec.get("h3s", [])
                if ("top" in h2 or "best" in h2) and len(h3s) >= 3:
                    has_named_list = True
                    break
            if not has_named_list:
                instructions.append(
                    "UNMET INTENT: The title promises a review of the 'best' or 'top' items, "
                    "but no section lists ≥3 specific named options. Add a dedicated "
                    "'Top X [Keyword]' section whose H3s are actual brand/product names "
                    "with brief reviews (50-80 words each)."
                )

        # --- B2B / transactional intent: check for unnatural keyword-as-heading ---
        if "buy" in kw_lower or "supplier" in kw_lower or "wholesale" in kw_lower:
            verbatim_h2s = [
                sec.get("h2", "") for sec in sections
                if kw_lower in (sec.get("h2") or "").lower()
            ]
            if verbatim_h2s:
                instructions.append(
                    f"B2B HEADING STUFFING: {len(verbatim_h2s)} section heading(s) repeat the "
                    f"exact keyword phrase '{self.keyword}' verbatim (e.g. '{verbatim_h2s[0]}'). "
                    f"Rewrite these headings to be descriptive and user-focused, e.g. "
                    f"'How to Choose a Reliable Clove Supplier' instead of repeating the keyword."
                )

        return instructions

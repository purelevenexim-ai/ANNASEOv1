"""
Per-section quality scorer for the content generation pipeline.

This is the foundation for targeted section regeneration (Phase C of the
quality engine upgrade plan). Unlike `quality.content_rules.check_all_rules`
which scores the entire article (density, FAQ presence, word count, etc.),
this module scores a SINGLE H2 section in isolation across five dimensions
that genuinely make sense at the section level:

    trust         — fake first-person authority, fabricated testing claims
    clarity       — sentence length, paragraph density, opener variety
    integrity     — mid-word splices, word fusion, duplicate words
    conversion    — CTA presence, decision/imperative language
    uniqueness    — recognised SEO template phrases

Scores are 0-10 per dimension. A weighted threshold determines whether a
section warrants regeneration (Phase C). This module is read-only / scoring
only — no rewriting happens here.

The scorer is intentionally lightweight (pure regex + counting) so it can
run on every section of every article without measurable cost.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Tuple

log = logging.getLogger("annaseo.quality.section_scorer")


# ─────────────────────────────────────────────────────────────────────────────
# Pattern catalogues (kept in sync with engines.content_generation_engine
# _FORBIDDEN_REPLACEMENTS where overlap exists; this list is detection-only).
# ─────────────────────────────────────────────────────────────────────────────

# Patterns whose presence indicates fabricated authority. Each detection
# subtracts one trust point (capped at the dimension max).
_TRUST_VIOLATIONS = (
    r"\b(?:in our|after our|based on our)\s+(?:testing|tests|evaluation|review|reviews|experience|hands-on)\b",
    r"\bwe\s+(?:tested|evaluated|reviewed|put\s+(?:this|these|it|them)\s+to\s+the\s+test)\b",
    r"\bour\s+team\s+(?:tested|evaluated|reviewed|analysed|analyzed|found)\b",
    r"\bhands-on\s+(?:testing|review|evaluation)\b",
    r"\bafter\s+putting\s+(?:this|these|it|them)\s+to\s+the\s+test\b",
    r"\bour\s+experience\s+shows\s+that\b",
    r"\bour\s+perspective\s+is\s+that\b",
    r"\bwe\s+found\s+(?:it|that)\b",
    r"\bwhen\s+we\s+analyzed\b",
    r"\bwe\s+observed\s+that\b",
    r"\bwe\s+discovered\b",
    r"\bin\s+our\s+kitchen\b",
    r"\bwe\s+actually\s+sent\b",
)

# Recognised SEO template patterns that destroy uniqueness. Mirror of the
# negative examples block in the draft prompt.
_TEMPLATE_PATTERNS = (
    r"\bthis\s+(?:factor\s+)?directly\s+(?:influences|impacts|affects)\b",
    r"\bbuyers\s+evaluating\b.{0,80}\bweigh\s+this\s+carefully\b",
    r"\bfor\s+\S+,?\s+this\s+distinction\s+matters\s+more\s+than\s+most\b",
    r"\bin\s+practice,?\s+\S+\s+outcomes\s+depend\s+heavily\s+on\b",
    r"\bwithout\s+addressing\s+this,?\b.{0,80}\bresults\s+will\s+be\s+inconsistent\b",
    r"\bthis\s+is\s+where\s+\S+\s+quality\s+becomes\s+measurable\b",
    r"\bconsistently\s+scores\s+well\s+on\s+this\b",
    r"\bexperienced\s+\S+\s+buyers\s+check\s+this\b",
    r"\bthis\s+guide\s+is\s+ideal\s+for\b.{0,120}\bbut\s+not\s+suited\s+for\b",
)

# Integrity corruption patterns. These should never reach a finished section.
_INTEGRITY_PATTERNS = (
    # Word fusion: "reviewsct", "supportsm", etc.
    (r"\b\w*(?:sct|wsct|esct|rsct|nsct|tsct)\b", "word_fusion"),
    # Mid-word capital injection inside a 3-word sequence (e.g., "th That said").
    (r"\b[a-z]{1,3}\s+[A-Z][a-z]{3,}\s+[a-z]{2,}\b", "mid_word_capital"),
    # Excessive double-spaces (5+ in one section is suspicious).
    (r"  +", "double_space"),
    # Duplicate adjacent words ("support support").
    (r"\b(\w{3,})\s+\1\b", "duplicate_word"),
)

# Words that begin imperative / decision-oriented sentences.
_CONVERSION_VERBS = {
    "discover", "explore", "shop", "browse", "buy", "order", "find", "choose",
    "select", "consider", "compare", "check", "view", "see", "learn", "try",
    "start", "get", "request", "contact", "book", "schedule", "download",
}

# Common safe sentence starters used to measure opener variety.
_TRACKED_OPENERS = {"the", "a", "an", "this", "these", "it", "they"}

# Mid-word capital allow-list (Phase A integrity scan parity).
_COMMON_MID_WORD_OK = {
    "the", "to", "a", "an", "in", "on", "at", "for", "with", "by", "from",
    "of", "or", "and", "as", "is", "be", "it", "no", "so", "if", "do", "we",
    "us", "my", "me", "he", "up", "go",
}


# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SectionScore:
    """Score for a single H2 section across five dimensions (0-10 each)."""

    h2: str = ""
    word_count: int = 0
    trust: float = 10.0
    clarity: float = 10.0
    integrity: float = 10.0
    conversion: float = 10.0
    uniqueness: float = 10.0
    issues: List[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        """Unweighted sum of the five dimensions (0-50)."""
        return self.trust + self.clarity + self.integrity + self.conversion + self.uniqueness

    @property
    def weighted_total(self) -> float:
        """Weighted score (0-100). Trust + integrity dominate because those are
        the dimensions that destroy E-E-A-T and reader confidence."""
        weights = {"trust": 1.5, "clarity": 1.0, "integrity": 1.7, "conversion": 1.2, "uniqueness": 1.1}
        weighted = (
            self.trust * weights["trust"]
            + self.clarity * weights["clarity"]
            + self.integrity * weights["integrity"]
            + self.conversion * weights["conversion"]
            + self.uniqueness * weights["uniqueness"]
        )
        # Max weighted = 10 * sum(weights) = 10 * 6.5 = 65 → normalise to 100.
        return round(weighted / 65.0 * 100, 1)

    def needs_regeneration(self) -> bool:
        """Conservative trigger for Phase C targeted regeneration.

        Kept deliberately strict — false positives here waste LLM calls.
        Tune from production data after 10+ articles."""
        return (
            self.integrity < 7.0
            or self.trust < 6.0
            or self.uniqueness < 6.0
            or self.weighted_total < 60.0
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["weighted_total"] = self.weighted_total
        d["total"] = self.total
        d["needs_regeneration"] = self.needs_regeneration()
        return d


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def split_sections(html: str) -> List[Tuple[str, str]]:
    """Split an article HTML into (h2_title, section_html) pairs.

    Anything before the first <h2> is returned with h2_title="__intro__".
    Sections without a clear H2 boundary are skipped.
    """
    if not html:
        return []
    # Find every H2 with its range up to the next H2 or end-of-document.
    matches = list(re.finditer(r"<h2[^>]*>(.*?)</h2>", html, re.I | re.DOTALL))
    sections: List[Tuple[str, str]] = []
    if not matches:
        return [("__intro__", html)]
    # Intro = everything before the first H2.
    intro = html[: matches[0].start()].strip()
    if intro:
        sections.append(("__intro__", intro))
    for idx, m in enumerate(matches):
        h2_title = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        start = m.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(html)
        sections.append((h2_title, html[start:end]))
    return sections


def score_section(html: str, h2_title: str = "") -> SectionScore:
    """Score a single section's HTML across the five quality dimensions."""
    score = SectionScore(h2=h2_title)
    if not html:
        return score

    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return score
    score.word_count = len(text.split())

    _score_trust(text, score)
    _score_clarity(text, score)
    _score_integrity(text, score)
    _score_conversion(text, score)
    _score_uniqueness(text, score)

    return score


def score_all_sections(html: str) -> List[SectionScore]:
    """Score every H2 section in an article. Returns one SectionScore per section."""
    return [score_section(section_html, h2) for h2, section_html in split_sections(html)]


def summarise_scores(scores: List[SectionScore]) -> Dict:
    """Aggregate per-section scores into an article-level summary."""
    if not scores:
        return {"section_count": 0, "average_weighted": 0.0, "weak_sections": []}
    avg = sum(s.weighted_total for s in scores) / len(scores)
    weak = [
        {"h2": s.h2, "weighted_total": s.weighted_total, "issues": s.issues}
        for s in scores
        if s.needs_regeneration()
    ]
    return {
        "section_count": len(scores),
        "average_weighted": round(avg, 1),
        "weak_sections": weak,
        "sections": [s.to_dict() for s in scores],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Per-dimension scorers (mutate score in-place)
# ─────────────────────────────────────────────────────────────────────────────

def _score_trust(text: str, score: SectionScore) -> None:
    """Each fake-authority match deducts 2 points (capped at 0)."""
    deductions = 0
    found: List[str] = []
    for pattern in _TRUST_VIOLATIONS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            deductions += len(matches) * 2
            # Record up to 3 distinct examples for debugging.
            found.extend(m if isinstance(m, str) else " ".join(m) for m in matches[:3])
    score.trust = max(0.0, 10.0 - deductions)
    if found:
        score.issues.append(f"trust: fake-authority phrases ({len(found)}): {found[:3]}")


def _score_clarity(text: str, score: SectionScore) -> None:
    """Penalise long sentences, low opener variety, and one-word paragraphs."""
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if len(s.strip()) > 5]
    if not sentences:
        score.clarity = 5.0
        score.issues.append("clarity: section has no parseable sentences")
        return

    avg_len = sum(len(s.split()) for s in sentences) / len(sentences)
    long_sents = sum(1 for s in sentences if len(s.split()) > 30)
    long_ratio = long_sents / len(sentences)

    # Opener variety: penalise if any single tracked opener is >40% of sentences.
    openers = [s.split()[0].lower() for s in sentences if s.split()]
    over_used = ""
    for opener in _TRACKED_OPENERS:
        if openers.count(opener) / len(openers) > 0.4:
            over_used = opener
            break

    deductions = 0.0
    if avg_len > 25:
        deductions += 2.0
        score.issues.append(f"clarity: avg sentence length {avg_len:.0f}w (target 15-20w)")
    elif avg_len < 8:
        deductions += 1.0
    if long_ratio > 0.2:
        deductions += 1.5
        score.issues.append(f"clarity: {long_sents}/{len(sentences)} sentences exceed 30 words")
    if over_used:
        deductions += 1.5
        score.issues.append(f"clarity: opener '{over_used}' overused (>40% of sentences)")
    score.clarity = max(0.0, 10.0 - deductions)


def _score_integrity(text: str, score: SectionScore) -> None:
    """Hard penalty for any corruption signature. Integrity below 7 triggers regen."""
    deductions = 0.0
    for pattern, kind in _INTEGRITY_PATTERNS:
        matches = re.findall(pattern, text)
        if not matches:
            continue
        if kind == "mid_word_capital":
            # Filter common-word allow-list to avoid false positives.
            real = [m for m in matches if (m if isinstance(m, str) else m[0]).split()[0].lower() not in _COMMON_MID_WORD_OK]
            if not real:
                continue
            count = len(real)
        elif kind == "double_space":
            # Some double-spaces are tolerable; only count if 5+ in a section.
            count = max(0, len(matches) - 4)
        else:
            count = len(matches)
        if count > 0:
            # Word fusion + mid-word capital are catastrophic (3 pts each).
            severity = 3.0 if kind in ("word_fusion", "mid_word_capital") else 1.5
            deductions += min(10.0, count * severity)
            score.issues.append(f"integrity: {kind} x{count}")
    score.integrity = max(0.0, 10.0 - deductions)


def _score_conversion(text: str, score: SectionScore) -> None:
    """Reward presence of decision/imperative language and CTAs."""
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if len(s.strip()) > 5]
    if not sentences:
        score.conversion = 5.0
        return
    imperatives = sum(
        1 for s in sentences
        if s.split() and s.split()[0].lower().rstrip(",") in _CONVERSION_VERBS
    )
    has_recommend = bool(re.search(r"\brecommended for\b|\bideal for\b|\bbest for\b|\bnot recommended\b", text, re.I))
    has_question = "?" in text

    base = 4.0
    if imperatives >= 1:
        base += 2.0
    if imperatives >= 3:
        base += 1.0
    if has_recommend:
        base += 2.0
    if has_question:
        base += 1.0
    score.conversion = min(10.0, base)
    if score.conversion < 5.0:
        score.issues.append("conversion: no imperatives, no recommendations, no questions")


def _score_uniqueness(text: str, score: SectionScore) -> None:
    """Each recognised SEO template pattern deducts 2.5 points."""
    deductions = 0.0
    found: List[str] = []
    for pattern in _TEMPLATE_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            deductions += len(matches) * 2.5
            found.extend(m if isinstance(m, str) else " ".join(m) for m in matches[:2])
    score.uniqueness = max(0.0, 10.0 - deductions)
    if found:
        score.issues.append(f"uniqueness: SEO template phrases ({len(found)}): {found[:2]}")

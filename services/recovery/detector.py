"""
Section-level issue detector.

Analyzes individual HTML sections against quality_rules and
generation_rules to detect problems that need recovery.
"""
import re
import math
from typing import Dict, List


def detect_section_issues(
    section_html: str,
    keyword: str,
    quality_rules: Dict,
    generation_rules: Dict,
    other_sections_text: str = "",
) -> List[Dict]:
    """Detect issues in a single section.

    Returns a list of issue dicts: [{"type": str, "severity": str, "detail": str}]
    """
    text = re.sub(r"<[^>]+>", " ", section_html).strip()
    text_lower = text.lower()
    words = text.split()
    word_count = len(words)
    issues: List[Dict] = []

    sl = quality_rules.get("section_level", {})

    # ── 1. Low depth ────────────────────────────────────────────────────
    min_words = sl.get("min_words", 150)
    if word_count < min_words:
        issues.append({
            "type": "low_depth",
            "severity": "high",
            "detail": f"Section has {word_count} words (min {min_words})",
        })

    # ── 2. Keyword stuffing ─────────────────────────────────────────────
    if word_count > 20 and keyword:
        kw_lower = keyword.lower()
        kw_word_len = len(kw_lower.split())
        kw_count = text_lower.count(kw_lower)
        density = (kw_count * kw_word_len / word_count) * 100 if word_count else 0
        max_density = sl.get("max_keyword_density", 2.5)
        if density > max_density:
            issues.append({
                "type": "keyword_stuffing",
                "severity": "high",
                "detail": f"Keyword density {density:.1f}% exceeds {max_density}% ({kw_count} mentions in {word_count} words)",
            })

    # ── 3. AI tone — forbidden words/phrases ────────────────────────────
    forbidden_words = generation_rules.get("forbidden_words", [])
    forbidden_phrases = generation_rules.get("forbidden_phrases", [])
    ai_signals = []

    for fw in forbidden_words:
        if fw.lower() in text_lower:
            ai_signals.append(fw)
    for fp in forbidden_phrases:
        if fp.lower() in text_lower:
            ai_signals.append(fp)

    max_ai = sl.get("max_ai_signals", 2)
    if len(ai_signals) > max_ai:
        issues.append({
            "type": "ai_tone",
            "severity": "medium",
            "detail": f"Found {len(ai_signals)} AI signals (max {max_ai}): {', '.join(ai_signals[:6])}",
        })

    # ── 4. Monotonous rhythm ────────────────────────────────────────────
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if len(s.split()) > 3]
    if len(sentences) >= 4:
        lengths = [len(s.split()) for s in sentences]
        # Check for 3+ consecutive sentences within ±3 words of each other
        for i in range(len(lengths) - 2):
            window = lengths[i : i + 3]
            if max(window) - min(window) <= 3:
                issues.append({
                    "type": "monotonous_rhythm",
                    "severity": "low",
                    "detail": f"Consecutive sentences have similar lengths ({window})",
                })
                break

    # ── 5. Missing authority ────────────────────────────────────────────
    authority_patterns = [
        r"according to\s+\w+", r"\d{4}\s+\w+\s+study",
        r"published in\b", r"research from\b",
        r"\bfda\b", r"\bwho\b", r"\bepa\b",
        r"\buniversity\b", r"journal of\b",
    ]
    authority_count = sum(1 for p in authority_patterns if re.search(p, text_lower))
    min_authority = sl.get("min_authority_signals", 1)
    if word_count >= min_words and authority_count < min_authority:
        issues.append({
            "type": "missing_authority",
            "severity": "low",
            "detail": f"No named authority sources found (expected >= {min_authority})",
        })

    # ── 6. Weak structure (long sections without subheadings/lists) ─────
    if word_count > 250:
        has_h3 = bool(re.search(r"<h3", section_html, re.I))
        has_list = bool(re.search(r"<[ou]l", section_html, re.I))
        has_table = bool(re.search(r"<table", section_html, re.I))
        if not has_h3 and not has_list and not has_table:
            issues.append({
                "type": "weak_structure",
                "severity": "medium",
                "detail": f"Long section ({word_count}w) with no subheadings, lists, or tables",
            })

    # ── 7. Repetition with other sections ───────────────────────────────
    if other_sections_text and word_count > 50:
        # Use trigram overlap
        def _trigrams(t):
            w = t.lower().split()
            return set(" ".join(w[i : i + 3]) for i in range(len(w) - 2))

        sec_tris = _trigrams(text)
        other_tris = _trigrams(other_sections_text)
        if sec_tris:
            overlap = len(sec_tris & other_tris) / len(sec_tris)
            if overlap > 0.15:
                issues.append({
                    "type": "repetition",
                    "severity": "medium",
                    "detail": f"Trigram overlap {overlap:.0%} with other sections (max 15%)",
                })

    # ── 8. Fake authority ───────────────────────────────────────────────
    fake_authority_patterns = [
        r"research\s+shows\s+that",
        r"studies\s+suggest\b",
        r"data\s+indicates\b",
        r"experts\s+(?:say|agree|recommend)\b",
        r"according\s+to\s+(?:recent\s+)?(?:research|studies|data)\b",
        r"evidence\s+suggests\b",
    ]
    fake_count = sum(1 for p in fake_authority_patterns if re.search(p, text_lower))
    if fake_count >= 2:
        issues.append({
            "type": "fake_authority",
            "severity": "medium",
            "detail": f"Found {fake_count} vague authority claims without named sources",
        })

    return issues


def score_section(issues: List[Dict]) -> int:
    """Score a section 0-100 based on detected issues.

    Starts at 100, deducts for each issue by severity.
    """
    score = 100
    deductions = {
        "high": 20,
        "medium": 10,
        "low": 5,
    }
    for issue in issues:
        score -= deductions.get(issue.get("severity", "low"), 5)
    return max(0, score)

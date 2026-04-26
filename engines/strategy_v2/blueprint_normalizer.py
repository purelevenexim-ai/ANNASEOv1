"""
Strategy V2 — Blueprint Normalizer & Validator.
Post-AI cleanup: dedup sections, validate required fields, enforce limits.
"""
import re
from .prompts import BANNED_TERMS


def normalize_blueprint(bp: dict) -> dict:
    """
    Deduplicate sections (case-insensitive heading match) and enforce section limit.
    Returns cleaned blueprint (mutates in place + returns).
    """
    sections = bp.get("sections", [])
    seen_headings = set()
    unique_sections = []

    for sec in sections:
        heading = sec.get("heading", "").lower().strip()
        # Normalise whitespace
        heading_key = re.sub(r"\s+", " ", heading)
        if heading_key and heading_key not in seen_headings:
            seen_headings.add(heading_key)
            unique_sections.append(sec)

    # Re-number section IDs after dedup
    for i, sec in enumerate(unique_sections):
        sec["id"] = f"S{i + 1}"

    bp["sections"] = unique_sections[:8]  # Hard cap at 8 sections
    return bp


def validate_blueprint(bp: dict) -> tuple:
    """
    Validate a blueprint meets minimum quality requirements.

    Returns (valid: bool, reason: str)
    """
    title = bp.get("title", "").strip()
    sections = bp.get("sections", [])

    if not title:
        return False, "Missing title"

    if len(title.split()) < 6:
        return False, f"Title too short ({len(title.split())} words): '{title}'"

    title_lower = title.lower()
    for banned in BANNED_TERMS:
        if banned in title_lower:
            return False, f"Title contains banned pattern '{banned}': '{title}'"

    if len(sections) < 4:
        return False, f"Too few sections ({len(sections)}, need ≥4)"

    headings = [s.get("heading", "").lower().strip() for s in sections]
    if len(set(headings)) != len(headings):
        return False, "Duplicate section headings after normalisation"

    if not bp.get("hook"):
        return False, "Missing hook"

    return True, "valid"

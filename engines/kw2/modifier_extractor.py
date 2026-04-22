"""
kw2 — ModifierExtractor

Extracts structured intent/quality/geo/audience modifiers from real keyword signals.

Replaces the hardcoded ["wholesale", "bulk", "organic", "premium", "online"] default.

Modifiers come from what's already in the keyword data (Google Suggest results,
competitor headings, SERP titles) — NOT from AI guesses.

Structure:
    {
        "intent":   ["buy", "price", "wholesale", "bulk", "supplier"],
        "quality":  ["organic", "pure", "authentic"],
        "geo":      ["india", "kerala"],
        "audience": ["restaurant", "home", "commercial"]
    }

Usage:
    from engines.kw2.modifier_extractor import ModifierExtractor
    me = ModifierExtractor()
    structured = me.extract(keyword_list)          # → dict
    flat = me.to_flat_list(structured)             # → list[str] for DB storage
    merged = me.merge_with_profile(flat, profile)  # → deduped, capped at 15
"""
import logging
from collections import Counter

log = logging.getLogger("kw2.modifier_extractor")

# ── Modifier signal dictionaries ────────────────────────────────────────────

# Transactional / commercial intent — highest value for buyer keyword generation
INTENT_SIGNALS = {
    "buy": "intent",
    "price": "intent",
    "cost": "intent",
    "rate": "intent",
    "wholesale": "intent",
    "bulk": "intent",
    "supplier": "intent",
    "online": "intent",
    "shop": "intent",
    "order": "intent",
    "purchase": "intent",
    "cheap": "intent",
    "affordable": "intent",
    "best price": "intent",
    "lowest price": "intent",
}

# Quality / trust signals — used in trust-building + filter queries
QUALITY_SIGNALS = {
    "organic": "quality",
    "pure": "quality",
    "natural": "quality",
    "premium": "quality",
    "authentic": "quality",
    "fresh": "quality",
    "certified": "quality",
    "chemical-free": "quality",
    "cold-pressed": "quality",
    "farm-direct": "quality",
    "hand-harvested": "quality",
    "non-gmo": "quality",
    "unprocessed": "quality",
}

# Geo / location signals — used in local + India-targeted keyword expansion
GEO_SIGNALS = {
    "india": "geo",
    "india online": "geo",
    "online india": "geo",
    "kerala": "geo",
    "malabar": "geo",
    "indian": "geo",
}

# Audience / buyer type signals — used for B2B/B2C targeting
AUDIENCE_SIGNALS = {
    "restaurant": "audience",
    "hotels": "audience",
    "hotel": "audience",
    "home": "audience",
    "household": "audience",
    "commercial": "audience",
    "retail": "audience",
    "b2b": "audience",
    "food service": "audience",
    "bakery": "audience",
    "food industry": "audience",
    "manufacturer": "audience",
    "exporter": "audience",
}

# All signals merged for fast lookup
_ALL_SIGNALS: dict[str, str] = {
    **INTENT_SIGNALS,
    **QUALITY_SIGNALS,
    **GEO_SIGNALS,
    **AUDIENCE_SIGNALS,
}

# Multi-word signal phrases (check before single-word to avoid partial matches)
_MULTI_WORD_SIGNALS = {k: v for k, v in _ALL_SIGNALS.items() if " " in k}
_SINGLE_WORD_SIGNALS = {k: v for k, v in _ALL_SIGNALS.items() if " " not in k}


class ModifierExtractor:
    """
    Extract structured modifiers from real keyword data.

    Input: any list of keyword strings (suggest results, competitor headings,
    SERP titles, rule-expanded keywords, etc.)

    Output: structured dict with 4 category buckets.
    """

    def extract(self, keywords: list[str]) -> dict:
        """
        Scan keyword strings for modifier signals and group by category.

        Args:
            keywords: any list of keyword strings

        Returns:
            {
                "intent":   [...],  # transactional/commercial
                "quality":  [...],  # trust/quality signals
                "geo":      [...],  # location signals
                "audience": [...]   # buyer type signals
            }
        """
        if not keywords:
            return {"intent": [], "quality": [], "geo": [], "audience": []}

        found: dict[str, Counter] = {
            "intent": Counter(),
            "quality": Counter(),
            "geo": Counter(),
            "audience": Counter(),
        }

        for kw in keywords:
            kw_lower = kw.lower().strip()
            if not kw_lower:
                continue

            # Check multi-word phrases first
            for phrase, category in _MULTI_WORD_SIGNALS.items():
                if phrase in kw_lower:
                    found[category][phrase] += 1

            # Check single words by token
            tokens = kw_lower.split()
            for tok in tokens:
                if tok in _SINGLE_WORD_SIGNALS:
                    found[_SINGLE_WORD_SIGNALS[tok]][tok] += 1

        result = {
            cat: [term for term, _count in counter.most_common()]
            for cat, counter in found.items()
        }

        log.debug(
            f"[ModifierExtractor] Scanned {len(keywords)} kws → "
            f"intent={len(result['intent'])}, quality={len(result['quality'])}, "
            f"geo={len(result['geo'])}, audience={len(result['audience'])}"
        )
        return result

    def to_flat_list(self, structured: dict) -> list[str]:
        """
        Flatten structured modifiers into a single ordered list for DB storage.

        Priority order: intent (highest value) > quality > geo > audience
        Max per category: intent=5, quality=4, geo=3, audience=3 (total ≤ 15)

        Args:
            structured: output from extract()

        Returns:
            flat deduplicated list of modifier strings
        """
        seen = set()
        flat = []

        quotas = [
            ("intent", 5),
            ("quality", 4),
            ("geo", 3),
            ("audience", 3),
        ]

        for category, max_count in quotas:
            for term in structured.get(category, [])[:max_count]:
                if term not in seen:
                    seen.add(term)
                    flat.append(term)

        return flat

    def merge_with_profile(self, enriched: list[str], existing: list[str]) -> list[str]:
        """
        Merge dynamically extracted modifiers with existing profile modifiers.

        Enriched modifiers (from real keyword data) take priority — they appear
        first. Existing profile modifiers fill in any remaining slots up to 15.

        Args:
            enriched: from to_flat_list() — data-driven modifiers
            existing: from profile["modifiers"] — current stored list

        Returns:
            merged, deduplicated list, max 15
        """
        seen = set()
        merged = []

        for m in enriched + (existing or []):
            m_lower = m.lower().strip()
            if m_lower and m_lower not in seen:
                seen.add(m_lower)
                merged.append(m_lower)
            if len(merged) >= 15:
                break

        return merged


# ── Default fallback modifiers (only used when no keyword data is available) ─────

DEFAULT_MODIFIERS = ["wholesale", "bulk", "organic", "online", "price", "supplier"]

# ── Seed-qualifier filter ─────────────────────────────────────────────────────
#
# Not all modifiers should be used as seed PREFIXES. Intent-only words like
# "online", "price", "buy" produce grammatically wrong seed phrases:
#   ✗ "online cardamom"   ✗ "price black pepper"   ✗ "buy organic"
#
# These intent signals already appear in TRANSACTIONAL_TEMPLATES as fill words.
# Only TRUE QUALIFIER modifiers (describing the product itself) belong in seeds:
#   ✓ "organic cardamom"   ✓ "wholesale black pepper"   ✓ "farm-direct cinnamon"
#
# This is already enforced in keyword_brain._build_seeds() via SEED_INTENT_MODIFIERS_EXCLUDE
# in constants.py, but is also exported here for any direct callers.

def get_seed_qualifiers(modifiers: list[str]) -> list[str]:
    """
    Filter modifiers to only those safe for seed phrase prefix/suffix building.

    Removes intent-only words that produce invalid seeds like 'online cardamom'
    or 'price black pepper'. These words are available in templates instead.

    Args:
        modifiers: raw modifier list from profile or DEFAULT_MODIFIERS

    Returns:
        filtered list of qualifier modifiers suitable for {modifier} {pillar} phrases
    """
    # Import here to avoid circular dependency
    from engines.kw2.constants import SEED_INTENT_MODIFIERS_EXCLUDE
    return [m for m in modifiers if m.lower().strip() not in SEED_INTENT_MODIFIERS_EXCLUDE]
